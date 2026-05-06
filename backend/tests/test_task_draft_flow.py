import pytest

from app.schemas.task_draft_schema import DraftStatus, TaskType
from app.services.ai_extractor import AIExtractor
from app.services.draft_manager import DraftManager
from app.services.intent_router import route_intent
from app.services.proposal_adapter import weighing_draft_to_legacy_dispense_intent
from app.validators.weighing_validator import validate_weighing_draft


def test_router_does_not_guess_ambiguous_chemical_only():
    result = route_intent("我要乙醇")

    assert result.route == "clarify"
    assert result.task_type is None


def test_router_detects_weighing_start():
    result = route_intent("帮我称 5g 氯化钠")

    assert result.route == "start_task"
    assert result.task_type == TaskType.WEIGHING


@pytest.mark.asyncio
async def test_weighing_draft_collects_multiturn_patch_without_guessing():
    manager = DraftManager()
    extractor = AIExtractor()
    session_id = "session_test"

    first_patch = await extractor.extract_patch(
        TaskType.WEIGHING,
        {},
        "帮我称 5g 氯化钠",
    )
    first_draft = manager.apply_patch(session_id, TaskType.WEIGHING, first_patch)

    assert first_draft.current_draft["chemical_name"] == "氯化钠"
    assert first_draft.current_draft["target_mass"] == 5
    assert first_draft.current_draft["mass_unit"] == "g"
    assert first_draft.current_draft["target_vessel"] is None
    assert first_draft.current_draft["purpose"] is None
    assert first_draft.ready_for_review is False
    assert first_draft.missing_slots == ["target_vessel", "purpose"]

    second_patch = await extractor.extract_patch(
        TaskType.WEIGHING,
        first_draft.current_draft,
        "放到 A1，做标准液",
    )
    second_draft = manager.apply_patch(session_id, TaskType.WEIGHING, second_patch)

    assert second_draft.current_draft["target_vessel"] == "A1"
    assert second_draft.current_draft["purpose"] == "标准液"
    assert second_draft.ready_for_review is True
    assert second_draft.missing_slots == []


def test_weighing_validator_owns_completeness():
    result = validate_weighing_draft(
        {
            "task_type": "WEIGHING",
            "chemical_name": "氯化钠",
            "target_mass": 5,
            "mass_unit": "g",
            "target_vessel": "A1",
            "purpose": "标准液",
        }
    )

    assert result.complete is True
    assert result.ready_for_review is True


def test_formal_intent_is_generated_only_after_ready_for_review():
    manager = DraftManager()
    draft = manager.apply_patch(
        "session_test",
        TaskType.WEIGHING,
        {
            "chemical_name": "氯化钠",
            "target_mass": 5,
            "mass_unit": "g",
            "target_vessel": "A1",
            "purpose": "标准液",
        },
    )
    intent = manager.to_formal_intent(draft)

    assert intent["intent_type"] == "dispense"
    assert intent["task_type"] == "WEIGHING"
    assert intent["reagent_hint"]["raw_text"] == "氯化钠"
    assert intent["params"]["target_mass_mg"] == 5000
    assert intent["params"]["target_vessel"] == "A1"
    assert "command_id" not in intent
    assert "motor_id" not in str(intent)


def test_confirm_before_ready_does_not_create_proposal():
    manager = DraftManager()
    draft = manager.apply_patch(
        "session_test",
        TaskType.WEIGHING,
        {"chemical_name": "氯化钠", "target_mass": 5, "mass_unit": "g"},
    )
    route = route_intent("确认", draft)

    assert route.route == "clarify"
    assert draft.ready_for_review is False
    with pytest.raises(ValueError):
        manager.create_proposal_intent(draft, user_message="确认")


def test_cancel_marks_draft_cancelled_without_proposal():
    manager = DraftManager()
    draft = manager.apply_patch(
        "session_test",
        TaskType.WEIGHING,
        {"chemical_name": "氯化钠"},
    )
    cancelled = manager.cancel("session_test")

    assert cancelled is draft
    assert cancelled.status == DraftStatus.CANCELLED
    assert cancelled.proposal_intent is None
    assert manager.get_active("session_test") is None
    assert cancelled.events[-1].event_type == "draft_cancelled"


@pytest.mark.asyncio
async def test_mid_draft_mass_change_updates_and_records_event():
    manager = DraftManager()
    extractor = AIExtractor()
    draft = manager.apply_patch(
        "session_test",
        TaskType.WEIGHING,
        {
            "chemical_name": "氯化钠",
            "target_mass": 5,
            "mass_unit": "g",
            "target_vessel": "A1",
            "purpose": "标准液",
        },
    )

    patch = await extractor.extract_patch(
        TaskType.WEIGHING,
        draft.current_draft,
        "不是 5g，改成 3g",
    )
    updated = manager.apply_patch(
        "session_test",
        TaskType.WEIGHING,
        patch,
        user_message="不是 5g，改成 3g",
        ai_patch=patch,
    )

    assert updated.current_draft["target_mass"] == 3
    assert updated.current_draft["mass_unit"] == "g"
    assert any(e.event_type == "patch_applied" for e in updated.events)
    assert updated.events[-2].user_message == "不是 5g，改成 3g"


def test_unknown_and_hardware_fields_are_discarded():
    manager = DraftManager()
    draft = manager.apply_patch(
        "session_test",
        TaskType.WEIGHING,
        {
            "chemical_name": "氯化钠",
            "target_mass": 5,
            "mass_unit": "g",
            "slot_id": "slot_1",
            "motor_id": "motor_9",
            "pump_id": "pump_1",
            "valve_id": "valve_1",
            "complete": True,
            "ready_for_review": True,
        },
    )

    assert draft.current_draft["chemical_name"] == "氯化钠"
    assert "slot_id" not in draft.current_draft
    assert "motor_id" not in draft.current_draft
    assert "pump_id" not in draft.current_draft
    assert "valve_id" not in draft.current_draft
    assert draft.ready_for_review is False


def test_empty_patch_does_not_destroy_existing_draft():
    manager = DraftManager()
    draft = manager.apply_patch(
        "session_test",
        TaskType.WEIGHING,
        {"chemical_name": "氯化钠", "target_mass": 5, "mass_unit": "g"},
    )
    before = dict(draft.current_draft)
    updated = manager.apply_patch("session_test", TaskType.WEIGHING, {})

    assert updated.current_draft == before
    assert updated.missing_slots == ["target_vessel", "purpose"]


def test_duplicate_proposal_creation_is_idempotent():
    manager = DraftManager()
    draft = manager.apply_patch(
        "session_test",
        TaskType.WEIGHING,
        {
            "chemical_name": "氯化钠",
            "target_mass": 5,
            "mass_unit": "g",
            "target_vessel": "A1",
            "purpose": "标准液",
        },
    )
    first = manager.create_proposal_intent(draft, user_message="确认")
    second = manager.create_proposal_intent(draft, user_message="确认")

    assert first is second
    assert draft.status == DraftStatus.PROPOSAL_CREATED
    assert [e.event_type for e in draft.events].count("proposal_created") == 1


def test_weighing_adapter_is_the_only_legacy_dispense_boundary():
    manager = DraftManager()
    draft = manager.apply_patch(
        "session_test",
        TaskType.WEIGHING,
        {
            "chemical_name": "氯化钠",
            "target_mass": 5,
            "mass_unit": "g",
            "target_vessel": "A1",
            "purpose": "标准液",
        },
    )

    intent = weighing_draft_to_legacy_dispense_intent(draft)

    assert intent["task_type"] == "WEIGHING"
    assert intent["intent_type"] == "dispense"
    assert intent["params"]["target_mass_mg"] == 5000


@pytest.mark.asyncio
async def test_debug_draft_events_endpoint_returns_audit_events():
    from app.api.debug import get_draft_events

    manager = DraftManager()
    draft = manager.apply_patch(
        "session_test",
        TaskType.WEIGHING,
        {"chemical_name": "氯化钠"},
        user_message="我要氯化钠",
        ai_patch={"chemical_name": "氯化钠"},
    )

    from app.services import draft_manager as draft_manager_module
    original_global = draft_manager_module.draft_manager
    try:
        draft_manager_module.draft_manager = manager
        import app.api.debug as debug_module
        debug_module.draft_manager = manager
        result = await get_draft_events(draft.draft_id)
    finally:
        draft_manager_module.draft_manager = original_global

    event_types = [event["event_type"] for event in result["events"]]
    assert "draft_created" in event_types
    assert "patch_applied" in event_types
    assert "validation_failed" in event_types
