from __future__ import annotations

import sys
import types
from types import SimpleNamespace

import pytest

from app.services.draft_manager import draft_manager

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
    assert first_draft["data"]["missing_slots"] == ["target_vessel", "purpose"]
    first_reply = _last_message(fake_ws.messages, "chat.done")
    assert "目标容器" in first_reply["text"]
    assert "本次任务用途" in first_reply["text"]

    await channels._process_text_input(dispatcher, session, "client_1", "放 A1，做标准液")
    ready_draft = _last_message(fake_ws.messages, "draft_update")
    assert ready_draft["data"]["status"] == "READY_FOR_REVIEW"
    assert ready_draft["data"]["ready_for_review"] is True
    second_reply = _last_message(fake_ws.messages, "chat.done")
    assert "称量 5g 氯化钠" in second_reply["text"]
    assert "请确认是否正确" in second_reply["text"]

    await channels._process_text_input(dispatcher, session, "client_1", "确认")
    proposal_draft = _last_message(fake_ws.messages, "draft_update")
    assert proposal_draft["data"]["status"] == "PROPOSAL_CREATED"
    proposal_reply = _last_message(fake_ws.messages, "chat.done")
    assert "正式任务 proposal" in proposal_reply["text"]
    assert "5000mg" in proposal_reply["text"]

    pending = _last_message(fake_ws.messages, "pending_intent")
    assert pending["data"]["intent_type"] == "dispense"
    assert pending["data"]["params"]["target_mass_mg"] == 5000
    assert pending["data"]["params"]["target_vessel"] == "A1"

    await channels._process_text_input(dispatcher, session, "client_1", "确认")
    held_reply = _last_message(fake_ws.messages, "chat.done")
    assert "已生成称量 proposal" in held_reply["text"]
    assert "不会下发控制命令" in held_reply["text"]
    assert _last_message(fake_ws.messages, "pending_cleared")
    assert control.commands == []
    assert not any(msg.get("type") == "command_sent" for msg in fake_ws.messages)
    assert not any(msg.get("type") == "error" for msg in fake_ws.messages)


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
    assert "chemical_name" in guarded["data"]["pending_confirmation_fields"]
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
