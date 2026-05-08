from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.schemas.task_draft_schema import DraftStatus, TaskType
from app.services.ai_extractor import AIExtractor
from app.services.dialog.dispatcher import IntentDispatcher
from app.services.dialog.session import Session
from app.services.dialog.state_machine import StateMachine
from app.services.draft_manager import DraftManager
from app.services.intent_router import route_intent


class FakeLLM:
    async def _call(self, messages, *, force_json):
        return '{"patch": {}}'

    async def interpret_confirmation(self, user_text, pending_summary):
        return "confirm" if user_text.strip() == "确认" else "unknown"


class FakeControlClient:
    def __init__(self):
        self.commands: list[dict] = []

    async def send_command(self, command):
        self.commands.append(command)
        return True, None

    async def get_status(self):
        return {"device_status": "idle", "balance_ready": True}


def test_dispensing_router_detects_start_and_ambiguous_mix():
    routed = route_intent("把氯化钠分成 3 份，每份 1g")
    assert routed.route == "start_task"
    assert routed.task_type == TaskType.DISPENSING

    ambiguous = route_intent("帮我配 10 管乙醇")
    assert ambiguous.route == "clarify"
    assert "配制新的溶液" in ambiguous.clarification


@pytest.mark.asyncio
async def test_extract_dispensing_source_count_amount_unit():
    extractor = AIExtractor()
    patch = await extractor.extract_patch(
        TaskType.DISPENSING,
        {},
        "把氯化钠分成 3 份，每份 1g",
    )

    assert patch["source_material_text"] == "氯化钠"
    assert patch["portion_count"] == 3
    assert patch["amount_per_portion"] == 1
    assert patch["amount_unit"] == "g"
    assert "chemical_id" not in patch


@pytest.mark.asyncio
async def test_extract_dispensing_vessels_without_purpose():
    extractor = AIExtractor()
    patch = await extractor.extract_patch(
        TaskType.DISPENSING,
        {},
        "放到 A1 A2 A3，做测试样品",
    )

    assert patch["target_vessels"] == ["A1", "A2", "A3"]
    assert "purpose" not in patch


@pytest.mark.asyncio
async def test_dispensing_draft_multiturn_reaches_ready_for_review():
    manager = DraftManager()
    extractor = AIExtractor()
    session_id = "dispensing_multiturn"

    first_patch = await extractor.extract_patch(
        TaskType.DISPENSING,
        {},
        "把氯化钠分成 3 份，每份 1g",
    )
    first = manager.apply_patch(session_id, TaskType.DISPENSING, first_patch)

    assert first.current_draft["chemical_id"] == "CHEM_NACL_AR_001"
    assert first.current_draft["catalog_match_status"] == "CONFIRMED"
    assert first.missing_slots == ["target_vessels"]
    assert first.ready_for_review is False

    second_patch = await extractor.extract_patch(
        TaskType.DISPENSING,
        first.current_draft,
        "放 A1 A2 A3，做测试样品",
    )
    second = manager.apply_patch(session_id, TaskType.DISPENSING, second_patch)

    assert second.current_draft["target_vessels"] == ["A1", "A2", "A3"]
    assert second.current_draft["purpose"] is None
    assert second.status == DraftStatus.READY_FOR_REVIEW
    assert second.ready_for_review is True


def test_dispensing_catalog_multiple_and_selection():
    manager = DraftManager()
    draft = manager.apply_patch(
        "dispensing_catalog_multiple",
        TaskType.DISPENSING,
        {
            "source_material_text": "乙醇",
            "portion_count": 3,
            "amount_per_portion": 1,
            "amount_unit": "g",
            "target_vessels": ["A1", "A2", "A3"],
            "purpose": "测试样品",
        },
    )

    assert draft.current_draft["catalog_match_status"] == "MULTIPLE_CANDIDATES"
    assert draft.ready_for_review is False
    assert {"catalog_candidate", "chemical_id"}.issubset(set(draft.pending_confirmation_fields))

    selected = manager.confirm_catalog_candidate(
        "dispensing_catalog_multiple",
        index=0,
        user_message="选择第一个化学品",
    )
    assert selected.current_draft["chemical_id"] == "CHEM_ETHANOL_AR_001"
    assert selected.current_draft["catalog_match_status"] == "CONFIRMED"
    assert selected.ready_for_review is True


def test_dispensing_catalog_no_match_blocks_proposal():
    manager = DraftManager()
    draft = manager.apply_patch(
        "dispensing_catalog_none",
        TaskType.DISPENSING,
        {
            "source_material_text": "不存在试剂",
            "portion_count": 3,
            "amount_per_portion": 1,
            "amount_unit": "g",
            "target_vessels": ["A1", "A2", "A3"],
            "purpose": "测试样品",
        },
    )

    assert draft.current_draft["catalog_match_status"] == "NO_MATCH"
    assert draft.ready_for_review is False
    with pytest.raises(ValueError):
        manager.create_proposal_intent(draft)


def test_dispensing_illegal_chemical_id_is_discarded():
    manager = DraftManager()
    draft = manager.apply_patch(
        "dispensing_illegal_id",
        TaskType.DISPENSING,
        {
            "source_material_text": "氯化钠",
            "chemical_id": "fake_id",
            "portion_count": 3,
            "amount_per_portion": 1,
            "amount_unit": "g",
        },
    )

    assert draft.current_draft["chemical_id"] == "CHEM_NACL_AR_001"
    assert draft.current_draft["chemical_id"] != "fake_id"


def test_dispensing_proposal_uses_catalog_confirmed_chemical():
    manager = DraftManager()
    draft = manager.apply_patch(
        "dispensing_proposal",
        TaskType.DISPENSING,
        {
            "source_material_text": "氯化钠",
            "portion_count": 3,
            "amount_per_portion": 1,
            "amount_unit": "g",
            "target_vessels": ["A1", "A2", "A3"],
            "purpose": "测试样品",
        },
    )
    intent = manager.create_proposal_intent(draft)

    assert intent["intent_type"] == "aliquot"
    assert intent["task_type"] == "DISPENSING"
    assert intent["reagent_hint"]["guessed_code"] == "CHEM_NACL_AR_001"
    assert intent["params"]["portions"] == 3
    assert intent["params"]["mass_per_portion_mg"] == 1000
    assert intent["params"]["target_vessels"] == ["A1", "A2", "A3"]


@pytest.mark.asyncio
async def test_dispensing_confirm_executes_after_rule_check(monkeypatch):
    import app.services.dialog.dispatcher as dispatcher_module

    async def fake_find_best_drug(keyword):
        drug = SimpleNamespace(
            reagent_code="NaCl-AR",
            reagent_name_cn=keyword,
            station_id="station_1",
            stock_mg=50000,
        )
        return drug, 0.95

    def fake_drug_to_dict(drug):
        return {
            "reagent_code": drug.reagent_code,
            "reagent_name_cn": drug.reagent_name_cn,
            "station_id": drug.station_id,
            "stock_mg": drug.stock_mg,
        }

    async def fake_create_task_record(intent_data, command):
        return "task_dispensing_execute"

    monkeypatch.setattr(dispatcher_module, "find_best_drug", fake_find_best_drug)
    monkeypatch.setattr(dispatcher_module, "drug_to_dict", fake_drug_to_dict)
    monkeypatch.setattr(dispatcher_module, "_create_task_record", fake_create_task_record)

    manager = DraftManager()
    draft = manager.apply_patch(
        "dispensing_execute",
        TaskType.DISPENSING,
        {
            "source_material_text": "氯化钠",
            "portion_count": 3,
            "amount_per_portion": 1,
            "amount_unit": "g",
            "target_vessels": ["A1", "A2", "A3"],
            "purpose": "测试样品",
        },
    )
    intent = manager.create_proposal_intent(draft)
    session = Session("dispensing_execute")
    control = FakeControlClient()
    dispatcher = IntentDispatcher(FakeLLM(), StateMachine(), control)

    result = await dispatcher.create_pending_from_intent(session, intent)

    assert result.output_type == "execute_now"
    assert len(control.commands) == 1
    command = control.commands[0]
    assert command["command_type"] == "aliquot"
    assert command["payload"]["portions"] == 3
    assert command["payload"]["mass_per_portion_mg"] == 1000
    assert command["payload"]["target_vessels"] == ["A1", "A2", "A3"]

    repeated = await dispatcher.handle_confirm(session)
    assert repeated.output_type == "reject"
    assert len(control.commands) == 1


@pytest.mark.asyncio
async def test_dispensing_rule_failure_on_vessel_count_mismatch():
    session = Session("dispensing_rule_failure")
    control = FakeControlClient()
    dispatcher = IntentDispatcher(FakeLLM(), StateMachine(), control)
    session.set_pending(
        intent_data={
            "intent_type": "aliquot",
            "task_type": "DISPENSING",
            "is_complete": True,
            "reagent_hint": {"raw_text": "氯化钠"},
            "params": {
                "portions": 3,
                "mass_per_portion_mg": 1000,
                "target_vessels": ["A1", "A2"],
            },
        },
        drug_info={"reagent_name_cn": "氯化钠", "stock_mg": 50000},
    )

    result = await dispatcher.handle_confirm(session)

    assert result.output_type == "reject"
    assert result.error_code == "RULE_CHECK_FAILED"
    assert "目标容器数量和分料份数不一致" in result.error_message
    assert control.commands == []


def test_dispensing_low_confidence_asr_blocks_ready_until_field_confirmation():
    manager = DraftManager()
    draft = manager.apply_patch(
        "dispensing_asr_low",
        TaskType.DISPENSING,
        {
            "source_material_text": "氯化钠",
            "portion_count": 3,
            "amount_per_portion": 1,
            "amount_unit": "g",
            "target_vessels": ["A1", "A2", "A3"],
            "purpose": "测试样品",
        },
        asr={
            "raw_text": "把绿化钠分成三份每份一克放A1A2A3做测试样品",
            "normalized_text": "把氯化钠分成3份每份1g放A1A2A3做测试样品",
            "confidence": 0.78,
            "needs_confirmation": True,
        },
    )

    assert draft.status == DraftStatus.NEEDS_FIELD_CONFIRMATION
    assert draft.ready_for_review is False
    assert "source_material_text" in draft.pending_confirmation_fields

    confirmed = manager.confirm_asr_fields("dispensing_asr_low", user_message="确认")
    assert confirmed.status == DraftStatus.READY_FOR_REVIEW
    assert confirmed.ready_for_review is True
