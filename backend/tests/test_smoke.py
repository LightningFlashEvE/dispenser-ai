"""
基础联调冒烟测试
================
验证后端 + mock-qt 联调的基本功能链路。

使用方式：
  1. 先启动 mock-qt:  cd mock-qt && python server.py --port 9000
  2. 再启动后端:       cd backend && python -m uvicorn app.main:app --port 8000
  3. 运行此脚本:       cd backend && python -m pytest tests/test_smoke.py -v

或不启动服务直接运行（仅测试不依赖外部服务的单元）：
  cd backend && python -m pytest tests/test_smoke.py -v -k "not integration"
"""

import json
import uuid
from datetime import datetime, timezone

import pytest

from app.services.dialog.intent import INTENT_TYPES, INTENT_TYPES_NO_SLOTS, SLOT_RULES, validate_intent
from app.services.dialog.rules import VALID_COMMAND_TYPES, build_command
from app.services.dialog.state_machine import DeviceState, StateMachine


class TestIntentValidation:

    def test_valid_dispense_complete(self):
        intent = {
            "schema_version": "1.0",
            "intent_type": "dispense",
            "is_complete": True,
            "missing_slots": [],
            "reagent_hint": {"raw_text": "氯化钠"},
            "params": {
                "target_mass_mg": 5000,
                "target_vessel": "A1",
            },
        }
        is_valid, errors, clarification = validate_intent(intent)
        assert is_valid, f"应该通过校验，错误: {errors}"
        assert len(errors) == 0

    def test_invalid_dispense_missing_vessel(self):
        intent = {
            "schema_version": "1.0",
            "intent_type": "dispense",
            "is_complete": True,
            "missing_slots": [],
            "reagent_hint": {"raw_text": "氯化钠"},
            "params": {
                "target_mass_mg": 5000,
                "target_vessel": None,
            },
        }
        is_valid, errors, _ = validate_intent(intent)
        assert not is_valid
        assert any("target_vessel" in e for e in errors)

    def test_dispense_incomplete_returns_clarification(self):
        intent = {
            "schema_version": "1.0",
            "intent_type": "dispense",
            "is_complete": False,
            "missing_slots": ["params.target_vessel"],
            "clarification_question": "请问放到哪个容器？",
            "reagent_hint": {"raw_text": "氯化钠"},
            "params": {"target_mass_mg": 5000, "target_vessel": None},
        }
        is_valid, errors, clarification = validate_intent(intent)
        assert is_valid
        assert clarification == "请问放到哪个容器？"

    def test_unknown_intent_type_rejected(self):
        intent = {"intent_type": "fly_to_moon"}
        is_valid, errors, _ = validate_intent(intent)
        assert not is_valid

    def test_query_types_always_valid(self):
        for itype in ("query_stock", "device_status", "cancel", "emergency_stop"):
            intent = {"intent_type": itype, "is_complete": True}
            is_valid, errors, _ = validate_intent(intent)
            assert is_valid, f"{itype} 应该直接通过"

    def test_mass_exceeds_capacity(self):
        intent = {
            "intent_type": "dispense",
            "is_complete": True,
            "reagent_hint": {"raw_text": "NaCl"},
            "params": {"target_mass_mg": 999999, "target_vessel": "A1"},
        }
        is_valid, errors, _ = validate_intent(intent)
        assert not is_valid
        assert any("量程" in e for e in errors)

    def test_mix_fraction_sum_check(self):
        intent = {
            "intent_type": "mix",
            "is_complete": True,
            "params": {
                "total_mass_mg": 5000,
                "components": [
                    {"raw_text": "A", "fraction": 0.3},
                    {"raw_text": "B", "fraction": 0.3},
                ],
            },
        }
        is_valid, errors, _ = validate_intent(intent)
        assert not is_valid
        assert any("fraction" in e for e in errors)

    def test_formula_valid(self):
        intent = {"intent_type": "formula", "is_complete": True}
        is_valid, errors, _ = validate_intent(intent)
        assert is_valid

    def test_restock_valid(self):
        intent = {
            "intent_type": "restock",
            "is_complete": True,
            "reagent_hint": {"raw_text": "NaCl"},
            "params": {"added_mass_mg": 50000},
        }
        is_valid, errors, _ = validate_intent(intent)
        assert is_valid

    def test_all_intent_types_have_rules_or_passthrough(self):
        for itype in INTENT_TYPES:
            assert itype in SLOT_RULES or itype in INTENT_TYPES_NO_SLOTS, \
                f"{itype} 没有槽位规则也不在免校验列表"


class TestRuleEngine:

    @pytest.mark.asyncio
    async def test_dispense_command_structure(self):
        intent = {
            "intent_type": "dispense",
            "params": {"target_mass_mg": 5000, "target_vessel": "A1"},
        }
        drug = {
            "reagent_code": "NaCl-AR",
            "reagent_name_cn": "氯化钠",
            "station_id": "station_3",
            "purity_grade": "AR",
        }
        cmd = await build_command(intent, drug)
        assert cmd["schema_version"] == "2.1"
        assert cmd["command_type"] == "dispense"
        assert "command_id" in cmd
        payload = cmd["payload"]
        assert payload["target_mass_mg"] == 5000
        assert payload["target_vessel"] == "A1"
        assert payload["reagent_code"] == "NaCl-AR"
        assert payload["reagent_name_cn"] == "氯化钠"

    @pytest.mark.asyncio
    async def test_mix_has_execution_mode(self):
        intent = {
            "intent_type": "mix",
            "params": {
                "total_mass_mg": 5000,
                "components": [
                    {"raw_text": "A", "fraction": 0.6},
                    {"raw_text": "B", "fraction": 0.4},
                ],
            },
        }
        cmd = await build_command(intent, None)
        assert cmd["payload"]["execution_mode"] == "sequential"

    @pytest.mark.asyncio
    async def test_restock_command(self):
        intent = {
            "intent_type": "restock",
            "params": {"added_mass_mg": 50000, "station_id": "station_1"},
        }
        drug = {"reagent_code": "NaCl-AR", "reagent_name_cn": "氯化钠"}
        cmd = await build_command(intent, drug)
        assert cmd["command_type"] == "restock"
        assert cmd["payload"]["added_mass_mg"] == 50000

    @pytest.mark.asyncio
    async def test_all_intent_types_are_valid_commands(self):
        """契约校验：intent_type（除 unknown）必须全部是合法的 command_type。"""
        for itype in INTENT_TYPES:
            if itype == "unknown":
                continue
            assert itype in VALID_COMMAND_TYPES, \
                f"intent_type '{itype}' 不在 VALID_COMMAND_TYPES 中"


class TestStateMachine:

    def test_initial_state_is_idle(self):
        sm = StateMachine()
        assert sm.device_state == DeviceState.IDLE

    def test_can_start_when_idle(self):
        sm = StateMachine()
        ok, reason = sm.can_start_task()
        assert ok

    def test_cannot_start_when_busy(self):
        sm = StateMachine()
        sm.start_task("task-1")
        ok, reason = sm.can_start_task()
        assert not ok
        assert "正在执行" in reason

    def test_complete_returns_to_idle(self):
        sm = StateMachine()
        sm.start_task("task-1")
        sm.complete_task("task-1")
        assert sm.device_state == DeviceState.IDLE
        assert sm.current_task_id is None

    def test_fail_sets_error(self):
        sm = StateMachine()
        sm.start_task("task-1")
        sm.fail_task("task-1", "测试错误")
        assert sm.device_state == DeviceState.ERROR

    def test_emergency_stop(self):
        sm = StateMachine()
        sm.start_task("task-1")
        sm.trigger_emergency_stop()
        assert sm.device_state == DeviceState.EMERGENCY_STOP
        assert sm.current_task_id is None

    def test_recover_from_error(self):
        sm = StateMachine()
        sm.start_task("task-1")
        sm.fail_task("task-1", "err")
        sm.recover_from_error()
        assert sm.device_state == DeviceState.IDLE

    def test_cancel_returns_to_idle(self):
        sm = StateMachine()
        sm.start_task("task-1")
        sm.cancel_task("task-1")
        assert sm.device_state == DeviceState.IDLE
