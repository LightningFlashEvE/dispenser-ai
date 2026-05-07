from __future__ import annotations

import sys
import types
from types import SimpleNamespace

import pytest

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

from app.services.dialog.dispatcher import DispatchResult, IntentDispatcher
from app.services.dialog.rules import build_command
from app.services.dialog.session import Session
from app.services.dialog.state_machine import StateMachine
from app.services.intent_router import route_intent
from app.ws import channels


class FakeLLM:
    async def process_dialog_stream(self, *args, **kwargs):
        if False:
            yield ""

    async def process_intent(self, *args, **kwargs):
        return SimpleNamespace(error="not used", raw_json=None)

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


class FakeWsManager:
    def __init__(self):
        self.messages: list[dict] = []

    async def send_json(self, client_id: str, data: dict) -> bool:
        self.messages.append(data)
        return True


def _formula(formula_id: str, formula_name: str, step_count: int):
    steps = [
        SimpleNamespace(
            step_index=i + 1,
            step_name=f"步骤 {i + 1}",
            command_type="dispense",
            reagent_code=f"R{i + 1:03d}",
            target_mass_mg=1000 + i,
            tolerance_mg=20,
            target_vessel=f"A{i + 1}",
        )
        for i in range(step_count)
    ]
    return SimpleNamespace(
        formula_id=formula_id,
        formula_name=formula_name,
        aliases_list=[],
        steps=steps,
    )


def _formulas():
    return [
        _formula("F001", "0.9% 生理盐水", 1),
        _formula("F002", "复合维生素溶液", 3),
        _formula("F004", "氯化钾注射液", 2),
    ]


def _dispatcher(formulas: list[SimpleNamespace], control: FakeControlClient | None = None):
    dispatcher = IntentDispatcher(
        llm=FakeLLM(),
        state_machine=StateMachine(),
        control_client=control or FakeControlClient(),
    )

    async def load_all_formulas():
        return formulas

    async def load_formula_by_id(formula_id: str):
        return next((item for item in formulas if item.formula_id == formula_id), None)

    dispatcher._load_all_formulas = load_all_formulas
    dispatcher._load_formula_by_id = load_formula_by_id
    return dispatcher


def test_formula_selection_route_precedes_mixing_words():
    assert route_intent("查看配方").route == "query_formula"
    assert route_intent("查询配方").route == "query_formula"
    assert route_intent("应用第三个配方").route == "select_formula"
    assert route_intent("使用第二个配方").route == "select_formula"
    assert route_intent("执行第 3 个配方").route == "select_formula"
    assert route_intent("套用 F004 配方").route == "select_formula"
    assert route_intent("应用氯化钾注射液配方").route == "select_formula"


@pytest.mark.asyncio
async def test_query_formula_stores_last_results_and_selects_third_formula():
    formulas = _formulas()
    session = Session("formula_select_session")
    dispatcher = _dispatcher(formulas)

    query_result = await dispatcher.handle_query_formula(session, "查看配方")
    assert query_result.output_type == "execute_now"
    assert session.last_formula_results == [
        {"formula_id": "F001", "formula_name": "0.9% 生理盐水", "step_count": 1},
        {"formula_id": "F002", "formula_name": "复合维生素溶液", "step_count": 3},
        {"formula_id": "F004", "formula_name": "氯化钾注射液", "step_count": 2},
    ]

    select_result = await dispatcher.handle_select_formula(session, "应用第三个配方")
    assert select_result.output_type == "action_proposal"
    assert select_result.pending_payload["intent_type"] == "formula"
    assert select_result.pending_payload["params"]["formula_id"] == "F004"
    assert select_result.pending_payload["params"]["formula_name"] == "氯化钾注射液"
    assert select_result.pending_payload["params"]["execution_mode"] == "sequential"
    assert "请确认是否应用" in select_result.dialog_text


@pytest.mark.asyncio
async def test_select_formula_without_list_and_out_of_range():
    dispatcher = _dispatcher(_formulas())
    session = Session("formula_empty_session")

    empty_result = await dispatcher.handle_select_formula(session, "应用第三个配方")
    assert "请先说查看配方" in empty_result.dialog_text
    assert empty_result.pending_payload is None

    await dispatcher.handle_query_formula(session, "查看配方")
    out_of_range = await dispatcher.handle_select_formula(session, "应用第十个配方")
    assert "上次只列出了 3 个配方" in out_of_range.dialog_text
    assert out_of_range.pending_payload is None


@pytest.mark.asyncio
async def test_select_formula_by_id_and_name():
    formulas = _formulas()
    dispatcher = _dispatcher(formulas)
    session = Session("formula_match_session")
    await dispatcher.handle_query_formula(session, "查看配方")

    by_id = await dispatcher.handle_select_formula(session, "应用 F004 配方")
    assert by_id.pending_payload["params"]["formula_id"] == "F004"

    session.clear_pending()
    by_name = await dispatcher.handle_select_formula(session, "应用氯化钾注射液配方")
    assert by_name.pending_payload["params"]["formula_id"] == "F004"


@pytest.mark.asyncio
async def test_formula_confirm_executes_after_rule_check(monkeypatch):
    import app.services.dialog.dispatcher as dispatcher_module

    formulas = _formulas()
    control = FakeControlClient()
    dispatcher = _dispatcher(formulas, control)
    monkeypatch.setattr(
        dispatcher_module,
        "_create_task_record",
        lambda intent_data, command: _async_value("task_formula_confirm"),
    )
    session = Session("formula_confirm_session")
    await dispatcher.handle_query_formula(session, "查看配方")
    await dispatcher.handle_select_formula(session, "应用第三个配方")

    result = await dispatcher.handle_confirm(session)
    assert result.output_type == "execute_now"
    assert result.pending_payload == "clear"
    assert result.command_id == control.commands[0]["command_id"]
    command = control.commands[0]
    assert command["command_type"] == "formula"
    assert command["payload"]["formula_id"] == "F004"
    assert command["payload"]["formula_name"] == "氯化钾注射液"
    assert len(command["payload"]["steps"]) == 2
    assert command["payload"]["execution_mode"] == "sequential"
    assert command["payload"]["on_step_failure"] == "pause_and_notify"


@pytest.mark.asyncio
async def test_formula_rule_failure_blocks_command():
    formulas = [_formula("F404", "空步骤配方", 0)]
    control = FakeControlClient()
    dispatcher = _dispatcher(formulas, control)
    session = Session("formula_rule_failure_session")
    session.set_pending(
        intent_data={
            "intent_type": "formula",
            "task_type": "FORMULA",
            "is_complete": True,
            "params": {
                "formula_id": "F404",
                "formula_name": "空步骤配方",
                "steps": [],
                "execution_mode": "sequential",
                "on_step_failure": "pause_and_notify",
            },
        }
    )

    result = await dispatcher.handle_confirm(session)

    assert result.output_type == "reject"
    assert result.error_code == "RULE_CHECK_FAILED"
    assert "配方步骤为空" in result.error_message
    assert result.pending_payload == "clear"
    assert control.commands == []


@pytest.mark.asyncio
async def test_formula_selection_websocket_continuous_dialogue(monkeypatch):
    formulas = _formulas()
    fake_ws = FakeWsManager()
    monkeypatch.setattr(channels, "ws_manager", fake_ws)
    dispatcher = _dispatcher(formulas)
    session = Session("formula_ws_session")

    async def fake_handle_query_stock(session, keyword):
        return DispatchResult(
            dialog_text=f"库存查询：{keyword}",
            speak_text=f"库存查询：{keyword}",
            state="FEEDBACK",
            output_type="execute_now",
        )

    dispatcher.handle_query_stock = fake_handle_query_stock

    await channels._process_text_input(dispatcher, session, "client_formula", "查看库存")
    assert _last_message(fake_ws.messages, "chat.done")["text"]

    await channels._process_text_input(dispatcher, session, "client_formula", "查看配方")
    assert session.last_formula_results[2]["formula_id"] == "F004"

    await channels._process_text_input(dispatcher, session, "client_formula", "应用第三个配方")
    pending = _last_message(fake_ws.messages, "pending_intent")
    assert pending["data"]["intent_type"] == "formula"
    assert pending["data"]["params"]["formula_id"] == "F004"
    assert "混合任务涉及配方" not in _last_message(fake_ws.messages, "chat.done")["text"]

    await channels._process_text_input(dispatcher, session, "client_formula", "设备状态")
    assert "设备状态" in _last_message(fake_ws.messages, "chat.done")["text"]


@pytest.mark.asyncio
async def test_build_formula_command_payload_directly():
    command = await build_command(
        {
            "intent_type": "formula",
            "params": {
                "formula_id": "F004",
                "formula_name": "氯化钾注射液",
                "steps": [{"step_index": 1, "command_type": "dispense"}],
            },
        }
    )
    assert command["payload"] == {
        "formula_id": "F004",
        "formula_name": "氯化钾注射液",
        "steps": [{"step_index": 1, "command_type": "dispense"}],
        "execution_mode": "sequential",
        "on_step_failure": "pause_and_notify",
    }


def _last_message(messages: list[dict], msg_type: str) -> dict:
    for msg in reversed(messages):
        if msg.get("type") == msg_type:
            return msg
    raise AssertionError(f"message type not found: {msg_type}")


async def _async_value(value):
    return value
