from __future__ import annotations

import sys
import types
from types import SimpleNamespace

import pytest

from app.services.draft_manager import draft_manager

try:
    from app.models.drug import Drug  # noqa: F401
    from app.models.task import Task  # noqa: F401
except ModuleNotFoundError:
    models_pkg = types.ModuleType("app.models")
    task_module = types.ModuleType("app.models.task")
    drug_module = types.ModuleType("app.models.drug")

    class Task:
        pass

    class Drug:
        pass

    task_module.Task = Task
    drug_module.Drug = Drug
    sys.modules.setdefault("app.models", models_pkg)
    sys.modules.setdefault("app.models.task", task_module)
    sys.modules.setdefault("app.models.drug", drug_module)

from app.services.dialog.dispatcher import IntentDispatcher
from app.services.dialog.session import Session
from app.services.dialog.state_machine import StateMachine
from app.ws import channels


class FakeWsManager:
    def __init__(self):
        self.messages: list[dict] = []

    async def send_json(self, client_id: str, data: dict) -> bool:
        self.messages.append(data)
        return True


class FakeLLM:
    async def _call(self, messages, *, force_json):
        raise RuntimeError("force rule fallback in tests")

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


@pytest.mark.asyncio
async def test_weighing_draft_websocket_text_flow(monkeypatch):
    async def fake_find_best_drug(keyword):
        drug = SimpleNamespace(
            reagent_code="NaCl-AR",
            reagent_name_cn=keyword,
            station_id="station_1",
        )
        return drug, 0.95

    def fake_drug_to_dict(drug):
        return {
            "reagent_code": drug.reagent_code,
            "reagent_name_cn": drug.reagent_name_cn,
            "station_id": drug.station_id,
        }

    import app.services.dialog.dispatcher as dispatcher_module

    fake_ws = FakeWsManager()
    monkeypatch.setattr(channels, "ws_manager", fake_ws)
    monkeypatch.setattr(dispatcher_module, "find_best_drug", fake_find_best_drug)
    monkeypatch.setattr(dispatcher_module, "drug_to_dict", fake_drug_to_dict)
    monkeypatch.setattr(
        dispatcher_module,
        "_create_task_record",
        lambda intent_data, command: _async_value("task_weighing_ws"),
    )

    session_id = "ws_draft_test"
    draft_manager.clear(session_id)
    session = Session(session_id=session_id)
    control = FakeControlClient()
    dispatcher = IntentDispatcher(
        llm=FakeLLM(),
        state_machine=StateMachine(),
        control_client=control,
    )

    await channels._process_text_input(dispatcher, session, "client_1", "帮我称 5g 氯化钠")
    first_draft = _last_message(fake_ws.messages, "draft_update")
    assert first_draft["data"]["status"] == "COLLECTING"
    assert first_draft["data"]["missing_slots"] == ["target_vessel"]
    first_reply = _last_message(fake_ws.messages, "chat.done")
    assert "目标容器" in first_reply["text"]

    await channels._process_text_input(dispatcher, session, "client_1", "放 A1，做标准液")
    ready_draft = _last_message(fake_ws.messages, "draft_update")
    assert ready_draft["data"]["status"] == "READY_FOR_REVIEW"
    assert ready_draft["data"]["ready_for_review"] is True
    second_reply = _last_message(fake_ws.messages, "chat.done")
    assert "称量 5g 氯化钠" in second_reply["text"]
    assert "请确认是否正确" in second_reply["text"]

    await channels._process_text_input(dispatcher, session, "client_1", "确认")
    proposal_draft = _last_message(fake_ws.messages, "draft_update")
    assert proposal_draft["data"]["status"] == "DISPATCHED"
    assert any(
        msg.get("type") == "chat.done"
        and "正式任务 proposal" in msg.get("text", "")
        and "5000mg" in msg.get("text", "")
        for msg in fake_ws.messages
    )

    command_sent = _last_message(fake_ws.messages, "command_sent")
    assert command_sent["command_id"] == control.commands[0]["command_id"]
    assert _last_message(fake_ws.messages, "pending_cleared")
    assert len(control.commands) == 1
    command = control.commands[0]
    assert command["command_type"] == "dispense"
    assert command["payload"]["target_mass_mg"] == 5000
    assert command["payload"]["target_vessel"] == "A1"
    assert command["payload"]["reagent_name_cn"] == "氯化钠"
    assert any(
        msg.get("type") == "chat.done" and "已下发指令" in msg.get("text", "")
        for msg in fake_ws.messages
    )

    await channels._process_text_input(dispatcher, session, "client_1", "确认")
    assert len(control.commands) == 1
    assert not any(msg.get("type") == "error" for msg in fake_ws.messages)


@pytest.mark.asyncio
async def test_weighing_rule_failure_blocks_command():
    session = Session(session_id="ws_draft_rule_failure")
    control = FakeControlClient()
    dispatcher = IntentDispatcher(
        llm=FakeLLM(),
        state_machine=StateMachine(),
        control_client=control,
    )
    session.set_pending(
        intent_data={
            "intent_type": "dispense",
            "task_type": "WEIGHING",
            "draft_id": "draft_rule_failure",
            "is_complete": True,
            "reagent_hint": {"raw_text": "氯化钠"},
            "params": {"target_mass_mg": 5000, "target_vessel": "A1"},
        },
        drug_info=None,
    )

    result = await dispatcher.handle_confirm(session)

    assert result.output_type == "reject"
    assert result.error_code == "RULE_CHECK_FAILED"
    assert "称量任务缺少已匹配试剂信息" in result.error_message
    assert result.pending_payload == "clear"
    assert control.commands == []


@pytest.mark.asyncio
async def test_weighing_confirm_creates_real_task_record_and_sends_command(monkeypatch):
    from sqlalchemy import delete, select

    from app.core.database import AsyncSessionLocal, Base, engine
    from app.models.task import Task
    import app.services.dialog.dispatcher as dispatcher_module

    async def fake_find_best_drug(keyword):
        drug = SimpleNamespace(
            reagent_code="NaCl-AR",
            reagent_name_cn=keyword,
            station_id="station_1",
            reagent_name_en=None,
            reagent_name_formula="NaCl",
            purity_grade="AR",
            molar_weight_g_mol=58.44,
            stock_mg=50000,
            notes=None,
        )
        return drug, 0.95

    def fake_drug_to_dict(drug):
        return {
            "reagent_code": drug.reagent_code,
            "reagent_name_cn": drug.reagent_name_cn,
            "reagent_name_en": drug.reagent_name_en,
            "reagent_name_formula": drug.reagent_name_formula,
            "purity_grade": drug.purity_grade,
            "station_id": drug.station_id,
            "molar_weight_g_mol": drug.molar_weight_g_mol,
            "stock_mg": drug.stock_mg,
            "notes": drug.notes,
        }

    monkeypatch.setattr(dispatcher_module, "find_best_drug", fake_find_best_drug)
    monkeypatch.setattr(dispatcher_module, "drug_to_dict", fake_drug_to_dict)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    fake_ws = FakeWsManager()
    monkeypatch.setattr(channels, "ws_manager", fake_ws)

    session_id = "ws_draft_real_task_record"
    draft_manager.clear(session_id)
    session = Session(session_id=session_id)
    control = FakeControlClient()
    dispatcher = IntentDispatcher(
        llm=FakeLLM(),
        state_machine=StateMachine(),
        control_client=control,
    )

    await channels._process_text_input(dispatcher, session, "client_real_task", "帮我称 5g 氯化钠")
    await channels._process_text_input(dispatcher, session, "client_real_task", "放 A1，做标准液")
    await channels._process_text_input(dispatcher, session, "client_real_task", "确认")

    assert len(control.commands) == 1
    command = control.commands[0]
    assert _last_message(fake_ws.messages, "command_sent")["command_id"] == command["command_id"]

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Task).where(Task.command_id == command["command_id"]))
        task = result.scalar_one_or_none()
        assert task is not None
        assert task.command_type == "dispense"
        assert task.status == "EXECUTING"
        await db.execute(delete(Task).where(Task.task_id == task.task_id))
        await db.commit()


@pytest.mark.asyncio
async def test_weighing_draft_websocket_asr_guard_flow(monkeypatch):
    import app.services.dialog.dispatcher as dispatcher_module

    fake_ws = FakeWsManager()
    monkeypatch.setattr(channels, "ws_manager", fake_ws)
    monkeypatch.setattr(dispatcher_module, "find_best_drug", lambda keyword: None)

    session_id = "ws_asr_guard_test"
    draft_manager.clear(session_id)
    session = Session(session_id=session_id)
    dispatcher = IntentDispatcher(
        llm=FakeLLM(),
        state_machine=StateMachine(),
        control_client=FakeControlClient(),
    )

    await channels._process_text_input(
        dispatcher,
        session,
        "client_asr",
        "帮我称5g氯化钠，放到 A1，做标准液",
        asr={
            "raw_text": "帮我称五克绿化钠，放到 A1，做标准液",
            "normalized_text": "帮我称5g氯化钠，放到 A1，做标准液",
            "confidence": 0.78,
            "needs_confirmation": True,
        },
    )
    guarded = _last_message(fake_ws.messages, "draft_update")
    assert guarded["data"]["status"] == "NEEDS_FIELD_CONFIRMATION"
    assert guarded["data"]["ready_for_review"] is False
    assert guarded["data"]["asr"]["raw_text"] == "帮我称五克绿化钠，放到 A1，做标准液"
    assert guarded["data"]["asr"]["needs_confirmation"] is True
    assert "chemical_name_text" in guarded["data"]["pending_confirmation_fields"]
    assert "语音识别内容" in _last_message(fake_ws.messages, "chat.done")["text"]

    await channels._process_text_input(dispatcher, session, "client_asr", "确认")
    confirmed = _last_message(fake_ws.messages, "draft_update")
    assert confirmed["data"]["status"] == "READY_FOR_REVIEW"
    assert confirmed["data"]["ready_for_review"] is True
    assert confirmed["data"]["asr"]["needs_confirmation"] is False
    assert confirmed["data"]["pending_confirmation_fields"] == []


def _last_message(messages: list[dict], msg_type: str) -> dict:
    for msg in reversed(messages):
        if msg.get("type") == msg_type:
            return msg
    raise AssertionError(f"message type not found: {msg_type}")


async def _async_value(value):
    return value
