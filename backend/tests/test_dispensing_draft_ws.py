from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.dialog.dispatcher import IntentDispatcher
from app.services.dialog.session import Session
from app.services.dialog.state_machine import StateMachine
from app.services.draft_manager import draft_manager
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
async def test_dispensing_draft_websocket_text_flow(monkeypatch):
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
        return "task_dispensing_ws"

    fake_ws = FakeWsManager()
    monkeypatch.setattr(channels, "ws_manager", fake_ws)
    monkeypatch.setattr(dispatcher_module, "find_best_drug", fake_find_best_drug)
    monkeypatch.setattr(dispatcher_module, "drug_to_dict", fake_drug_to_dict)
    monkeypatch.setattr(dispatcher_module, "_create_task_record", fake_create_task_record)

    session_id = "ws_dispensing_test"
    draft_manager.clear(session_id)
    session = Session(session_id=session_id)
    control = FakeControlClient()
    dispatcher = IntentDispatcher(
        llm=FakeLLM(),
        state_machine=StateMachine(),
        control_client=control,
    )

    await channels._process_text_input(dispatcher, session, "client_dispensing", "把氯化钠分成 3 份，每份 1g")
    first_draft = _last_message(fake_ws.messages, "draft_update")
    assert first_draft["data"]["task_type"] == "DISPENSING"
    assert first_draft["data"]["status"] == "COLLECTING"
    assert first_draft["data"]["current_draft"]["chemical_id"] == "CHEM_NACL_AR_001"
    assert first_draft["data"]["missing_slots"] == ["target_vessels"]

    await channels._process_text_input(dispatcher, session, "client_dispensing", "放 A1 A2 A3，做测试样品")
    ready_draft = _last_message(fake_ws.messages, "draft_update")
    assert ready_draft["data"]["status"] == "READY_FOR_REVIEW"
    assert ready_draft["data"]["ready_for_review"] is True
    assert ready_draft["data"]["current_draft"]["target_vessels"] == ["A1", "A2", "A3"]
    assert "分成 3 份" in _last_message(fake_ws.messages, "chat.done")["text"]

    await channels._process_text_input(dispatcher, session, "client_dispensing", "确认")
    dispatched = _last_message(fake_ws.messages, "draft_update")
    assert dispatched["data"]["status"] == "DISPATCHED"
    assert _last_message(fake_ws.messages, "command_sent")["command_id"] == control.commands[0]["command_id"]
    assert len(control.commands) == 1
    command = control.commands[0]
    assert command["command_type"] == "aliquot"
    assert command["payload"]["portions"] == 3
    assert command["payload"]["mass_per_portion_mg"] == 1000
    assert command["payload"]["target_vessels"] == ["A1", "A2", "A3"]

    await channels._process_text_input(dispatcher, session, "client_dispensing", "确认")
    assert len(control.commands) == 1
    assert not any(msg.get("type") == "error" for msg in fake_ws.messages)


@pytest.mark.asyncio
async def test_dispensing_draft_websocket_catalog_candidate_selection(monkeypatch):
    fake_ws = FakeWsManager()
    monkeypatch.setattr(channels, "ws_manager", fake_ws)

    session_id = "ws_dispensing_catalog"
    draft_manager.clear(session_id)
    session = Session(session_id=session_id)
    dispatcher = IntentDispatcher(
        llm=FakeLLM(),
        state_machine=StateMachine(),
        control_client=FakeControlClient(),
    )

    await channels._process_text_input(dispatcher, session, "client_dispensing_catalog", "把乙醇分成 2 份，每份 1g")
    candidate_draft = _last_message(fake_ws.messages, "draft_update")
    assert candidate_draft["data"]["status"] == "NEEDS_FIELD_CONFIRMATION"
    assert candidate_draft["data"]["current_draft"]["catalog_match_status"] == "MULTIPLE_CANDIDATES"
    assert "catalog_candidate" in candidate_draft["data"]["pending_confirmation_fields"]
    assert "请选择具体化学品" in _last_message(fake_ws.messages, "chat.done")["text"]

    await channels._process_text_input(dispatcher, session, "client_dispensing_catalog", "选择第二个化学品")
    selected_draft = _last_message(fake_ws.messages, "draft_update")
    assert selected_draft["data"]["current_draft"]["chemical_id"] == "CHEM_ETHANOL_STD_001"
    assert selected_draft["data"]["current_draft"]["catalog_match_status"] == "CONFIRMED"
    assert selected_draft["data"]["status"] == "COLLECTING"


def _last_message(messages: list[dict], msg_type: str) -> dict:
    for msg in reversed(messages):
        if msg.get("type") == msg_type:
            return msg
    raise AssertionError(f"message type not found: {msg_type}")
