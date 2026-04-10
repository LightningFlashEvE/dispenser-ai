import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.drug import Drug
from app.models.task import Task
from app.services.ai.llm import DialogSession, get_llm
from app.services.dialog.intent import validate_intent
from app.services.dialog.rules import build_command
from app.services.dialog.state_machine import get_state_machine
from app.services.device.control_client import get_control_client
from app.ws.manager import ws_manager

router = APIRouter(tags=["WebSocket"])
logger = get_logger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fuzzy_score(drug: Drug, keyword: str) -> float:
    kw = keyword.lower().strip()
    if not kw:
        return 0.0
    if drug.reagent_code.lower() == kw:
        return 1.0
    if drug.reagent_name_cn.lower() == kw:
        return 0.95
    if drug.reagent_code.lower().startswith(kw):
        return 0.9
    if drug.reagent_name_cn.lower().startswith(kw):
        return 0.85
    if kw in [alias.lower() for alias in drug.aliases_list]:
        return 0.95
    if any(kw in alias.lower() for alias in drug.aliases_list):
        return 0.75
    if drug.reagent_name_formula and kw in drug.reagent_name_formula.lower():
        return 0.7
    if drug.reagent_name_en and kw in drug.reagent_name_en.lower():
        return 0.6
    if kw in drug.reagent_name_cn.lower():
        return 0.5
    return 0.0


def _drug_to_dict(drug: Drug) -> dict:
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


def _default_tolerance(target_mass_mg: int | None) -> int:
    if not target_mass_mg or target_mass_mg <= 0:
        return settings.default_tolerance_mg
    pct_value = int(target_mass_mg * settings.default_tolerance_pct / 100)
    return max(settings.default_tolerance_mg, pct_value)


async def _find_best_drug(keyword: str | None) -> tuple[Drug | None, float]:
    if not keyword:
        return None, 0.0
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Drug).where(Drug.is_active == True))
        drugs = list(result.scalars().all())
    if not drugs:
        return None, 0.0
    best_drug: Drug | None = None
    best_score = 0.0
    for drug in drugs:
        score = _fuzzy_score(drug, keyword)
        if score > best_score:
            best_drug = drug
            best_score = score
    return best_drug, best_score


async def _send_error(client_id: str, code: str, message: str) -> None:
    await ws_manager.send_json(client_id, {"type": "error", "code": code, "message": message})


async def _send_state(client_id: str, state: str) -> None:
    await ws_manager.send_json(client_id, {"type": "state_change", "state": state})


async def _create_task_record(intent_data: dict, command: dict) -> str:
    task_id = str(uuid.uuid4())
    async with AsyncSessionLocal() as db:
        task = Task(
            task_id=task_id,
            command_id=command["command_id"],
            command_type=command["command_type"],
            operator_id=command.get("operator_id", "admin"),
            status="EXECUTING",
            intent_json=json.dumps(intent_data, ensure_ascii=False),
            command_json=json.dumps(command, ensure_ascii=False),
            started_at=datetime.now(timezone.utc),
        )
        db.add(task)
        await db.commit()
    return task_id


async def _update_task_failure(task_id: str, message: str) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Task).where(Task.task_id == task_id))
        task = result.scalar_one_or_none()
        if task is None:
            return
        task.status = "FAILED"
        task.error_message = message
        task.completed_at = datetime.now(timezone.utc)
        await db.commit()


async def _load_current_task() -> Task | None:
    state_machine = get_state_machine()
    current_task_id = state_machine.current_task_id
    if not current_task_id:
        return None
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Task).where(Task.task_id == current_task_id))
        return result.scalar_one_or_none()


async def _resolve_mix_components(intent_data: dict) -> tuple[bool, str | None]:
    params = intent_data.get("params", {})
    components = params.get("components") or []
    total_mass_mg = params.get("total_mass_mg")
    ratio_type = params.get("ratio_type") or "mass_fraction"
    if not isinstance(components, list) or not isinstance(total_mass_mg, int) or total_mass_mg <= 0:
        return False, "混合参数不完整"

    resolved_components: list[dict] = []
    if ratio_type == "molar_fraction":
        weighted_sum = 0.0
        weights: list[float] = []
        matched_drugs: list[Drug] = []
        for comp in components:
            drug, score = await _find_best_drug(comp.get("raw_text"))
            if drug is None or score < 0.5:
                return False, f"未找到组分药品：{comp.get('raw_text')}"
            if not drug.molar_weight_g_mol or drug.molar_weight_g_mol <= 0:
                return False, f"组分缺少摩尔质量：{drug.reagent_name_cn}"
            fraction = comp.get("fraction")
            if not isinstance(fraction, (int, float)):
                return False, f"组分占比无效：{comp.get('raw_text')}"
            weight = float(fraction) * float(drug.molar_weight_g_mol)
            weights.append(weight)
            weighted_sum += weight
            matched_drugs.append(drug)
        if weighted_sum <= 0:
            return False, "摩尔分数无法换算质量"
        for comp, drug, weight in zip(components, matched_drugs, weights):
            calculated_mass = max(1, round(total_mass_mg * weight / weighted_sum))
            resolved_components.append(
                {
                    **_drug_to_dict(drug),
                    "fraction": comp.get("fraction"),
                    "calculated_mass_mg": calculated_mass,
                    "tolerance_mg": _default_tolerance(calculated_mass),
                }
            )
    else:
        for comp in components:
            drug, score = await _find_best_drug(comp.get("raw_text"))
            if drug is None or score < 0.5:
                return False, f"未找到组分药品：{comp.get('raw_text')}"
            fraction = comp.get("fraction")
            if not isinstance(fraction, (int, float)):
                return False, f"组分占比无效：{comp.get('raw_text')}"
            calculated_mass = max(1, round(total_mass_mg * float(fraction)))
            resolved_components.append(
                {
                    **_drug_to_dict(drug),
                    "fraction": fraction,
                    "calculated_mass_mg": calculated_mass,
                    "tolerance_mg": _default_tolerance(calculated_mass),
                }
            )

    intent_data.setdefault("params", {})["components"] = resolved_components
    return True, None


@router.websocket("/ws/voice")
async def voice_websocket(websocket: WebSocket) -> None:
    client_id = f"voice_{id(websocket)}"
    llm = get_llm()
    state_machine = get_state_machine()
    control_client = get_control_client()
    dialog_session = DialogSession()
    await ws_manager.connect(client_id, websocket)
    try:
        await ws_manager.send_json(client_id, {
            "type": "connected",
            "client_id": client_id,
            "timestamp": _now_iso(),
        })
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await _send_error(client_id, "INVALID_JSON", "无效 JSON")
                continue

            msg_type = msg.get("type", "")

            if msg_type == "cancel":
                current_task = await _load_current_task()
                if current_task is None or not current_task.command_id:
                    await ws_manager.send_json(client_id, {"type": "question", "text": "当前没有可取消的任务"})
                    await _send_state(client_id, "IDLE")
                    continue

                cancel_command = {
                    "schema_version": "2.1",
                    "command_id": str(uuid.uuid4()),
                    "timestamp": _now_iso(),
                    "operator_id": "admin",
                    "command_type": "cancel",
                    "payload": {"target_command_id": current_task.command_id},
                }
                await control_client.send_command(cancel_command)
                state_machine.cancel_task(current_task.task_id)
                await ws_manager.send_json(
                    client_id,
                    {
                        "type": "command_result",
                        "data": {
                            "command_id": current_task.command_id,
                            "status": "cancelled",
                            "result": None,
                            "error": None,
                            "completed_at": _now_iso(),
                        },
                    },
                )
                await _send_state(client_id, "IDLE")
                dialog_session.reset()
                continue

            if msg_type != "transcript":
                await _send_error(client_id, "UNSUPPORTED_MESSAGE", f"不支持的消息类型: {msg_type}")
                continue

            user_text = msg.get("text")
            if not isinstance(user_text, str) or not user_text.strip():
                await _send_error(client_id, "INVALID_TRANSCRIPT", "缺少有效文本")
                continue

            user_text = user_text.strip()
            await _send_state(client_id, "PROCESSING")
            await ws_manager.send_json(client_id, {"type": "stt_final", "text": user_text})

            intent_result = await llm.process(user_text, session=dialog_session)
            if intent_result.error:
                await _send_state(client_id, "ERROR")
                await _send_error(client_id, "LLM_ERROR", intent_result.error)
                continue

            intent_data = intent_result.raw_json
            is_valid, errors, clarification = validate_intent(intent_data)
            if clarification or not intent_result.is_complete:
                question = clarification or intent_data.get("clarification_question") or "请补充必要信息"
                await ws_manager.send_json(client_id, {"type": "question", "text": question})
                await _send_state(client_id, "ASKING")
                continue

            if not is_valid:
                await _send_state(client_id, "ERROR")
                await _send_error(client_id, "INTENT_INVALID", "；".join(errors))
                continue

            intent_type = intent_data.get("intent_type")

            if intent_type == "unknown":
                await ws_manager.send_json(client_id, {"type": "question", "text": "我没有理解，请换种说法再说一次"})
                await _send_state(client_id, "ASKING")
                continue

            if intent_type == "query_device_status":
                device_status = await control_client.get_status()
                text = f"设备状态：{device_status.get('device_status', 'unknown')}，天平就绪：{device_status.get('balance_ready', False)}"
                await ws_manager.send_json(client_id, {"type": "question", "text": text})
                await _send_state(client_id, "FEEDBACK")
                dialog_session.reset()
                continue

            if intent_type == "query_stock":
                keyword = (
                    intent_data.get("params", {}).get("raw_text")
                    or (intent_data.get("reagent_hint") or {}).get("raw_text")
                )
                if keyword:
                    drug, score = await _find_best_drug(keyword)
                    if drug is None or score < 0.5:
                        await ws_manager.send_json(client_id, {"type": "question", "text": f"没有找到药品：{keyword}"})
                    else:
                        await ws_manager.send_json(
                            client_id,
                            {"type": "question", "text": f"{drug.reagent_name_cn} 当前库存 {drug.stock_mg} mg，工位 {drug.station_id or '未知'}"},
                        )
                else:
                    await ws_manager.send_json(client_id, {"type": "question", "text": "请提供要查询的药品名称"})
                await _send_state(client_id, "FEEDBACK")
                dialog_session.reset()
                continue

            if intent_type == "emergency_stop":
                state_machine.trigger_emergency_stop()
                ok = await control_client.send_emergency_stop()
                if not ok:
                    await _send_state(client_id, "ERROR")
                    await _send_error(client_id, "EMERGENCY_STOP_FAILED", "急停指令下发失败")
                    continue
                await ws_manager.send_json(
                    client_id,
                    {
                        "type": "command_result",
                        "data": {
                            "command_id": "emergency_stop",
                            "status": "completed",
                            "result": {"message": "急停已触发"},
                            "error": None,
                            "completed_at": _now_iso(),
                        },
                    },
                )
                await _send_state(client_id, "FEEDBACK")
                dialog_session.reset()
                continue

            if intent_type == "cancel_task":
                current_task = await _load_current_task()
                if current_task is None or not current_task.command_id:
                    await ws_manager.send_json(client_id, {"type": "question", "text": "当前没有执行中的任务"})
                    await _send_state(client_id, "IDLE")
                    continue
                cancel_command = {
                    "schema_version": "2.1",
                    "command_id": str(uuid.uuid4()),
                    "timestamp": _now_iso(),
                    "operator_id": "admin",
                    "command_type": "cancel",
                    "payload": {"target_command_id": current_task.command_id},
                }
                ok = await control_client.send_command(cancel_command)
                if not ok:
                    await _send_state(client_id, "ERROR")
                    await _send_error(client_id, "CANCEL_FAILED", "取消指令下发失败")
                    continue
                state_machine.cancel_task(current_task.task_id)
                await ws_manager.send_json(
                    client_id,
                    {
                        "type": "command_result",
                        "data": {
                            "command_id": current_task.command_id,
                            "status": "cancelled",
                            "result": None,
                            "error": None,
                            "completed_at": _now_iso(),
                        },
                    },
                )
                await _send_state(client_id, "IDLE")
                dialog_session.reset()
                continue

            drug_info: dict | None = None
            reagent_hint = intent_data.get("reagent_hint") or {}
            if intent_type in {"dispense_powder", "aliquot_powder"}:
                drug, score = await _find_best_drug(reagent_hint.get("raw_text"))
                if drug is None or score < 0.5:
                    await ws_manager.send_json(client_id, {"type": "question", "text": f"未找到药品：{reagent_hint.get('raw_text')}，请重新确认名称"})
                    await _send_state(client_id, "ASKING")
                    continue
                drug_info = _drug_to_dict(drug)

            if intent_type == "mix_powder":
                ok, error_message = await _resolve_mix_components(intent_data)
                if not ok:
                    await ws_manager.send_json(client_id, {"type": "question", "text": error_message or "混合参数无法解析"})
                    await _send_state(client_id, "ASKING")
                    continue

            can_start, reason = state_machine.can_start_task()
            if not can_start:
                await _send_state(client_id, "ERROR")
                await _send_error(client_id, "DEVICE_BUSY", reason)
                continue

            command = await build_command(intent_data, drug_info)
            task_id = await _create_task_record(intent_data, command)

            if not state_machine.start_task(task_id):
                await _update_task_failure(task_id, "状态机拒绝启动任务")
                await _send_state(client_id, "ERROR")
                await _send_error(client_id, "STATE_MACHINE_REJECTED", "状态机拒绝启动任务")
                continue

            await _send_state(client_id, "EXECUTING")
            ok = await control_client.send_command(command)
            if not ok:
                state_machine.fail_task(task_id, "命令下发失败")
                await _update_task_failure(task_id, "命令下发失败")
                await _send_state(client_id, "ERROR")
                await _send_error(client_id, "COMMAND_SEND_FAILED", "命令下发失败")
                continue

            await ws_manager.send_json(client_id, {"type": "command_sent", "command_id": command["command_id"]})
            dialog_session.reset()
    except WebSocketDisconnect:
        ws_manager.disconnect(client_id)
    except Exception:
        logger.exception("voice_websocket 未预期异常")
        await _send_error(client_id, "INTERNAL_ERROR", "服务内部错误，请重试")
        ws_manager.disconnect(client_id)


@router.websocket("/ws/balance")
async def balance_websocket(websocket: WebSocket) -> None:
    """
    天平实时数据通道。
    服务端持续推送天平读数（mg 整数），客户端只读。
    """
    client_id = f"balance_{id(websocket)}"
    await ws_manager.connect(client_id, websocket)
    try:
        await websocket.send_json({
            "type": "connected",
            "client_id": client_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(client_id)
    except Exception:
        logger.exception("balance_websocket 异常，client=%s", client_id)
        ws_manager.disconnect(client_id)


async def push_balance(mass_mg: int, stable: bool) -> None:
    await ws_manager.broadcast({
        "type": "balance_reading",
        "mass_mg": mass_mg,
        "stable": stable,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


async def push_balance_over_limit(mass_mg: int) -> None:
    await ws_manager.broadcast({
        "type": "balance_over_limit",
        "mass_mg": mass_mg,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
