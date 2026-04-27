"""
mock-qt/server.py
=================
模拟 C++ 后级控制程序的 HTTP 服务，仅用于开发联调阶段。

行为：
  1. 接收 AI 层下发的 command JSON（POST /api/command）
  2. 立即返回 accepted/rejected
  3. 在后台异步等待 execution_delay_ms 后，按 failure_rate 概率决定成功/失败
   4. 主动 POST 回调 AI 层的 /api/tasks/callback
  5. 支持 emergency_stop（立即取消所有进行中任务）
  6. 支持 cancel（取消指定任务）
  7. GET /api/status 返回当前设备状态

注意：
  - 不做任何业务逻辑，只做格式基础校验 + 模拟延迟 + 回调
  - 不部署到生产环境
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import uvicorn

# ---------------------------------------------------------------------------
# 时区工具
# ---------------------------------------------------------------------------
CST = timezone(timedelta(hours=8))


def now_iso() -> str:
    return datetime.now(CST).isoformat(timespec="milliseconds")


# ---------------------------------------------------------------------------
# 配置加载
# ---------------------------------------------------------------------------
DEFAULT_CONFIG: dict[str, Any] = {
    "port": 9000,
    "ai_callback_url": "http://localhost:8000/api/tasks/callback",
    "execution_delay_ms": 2000,
    "failure_rate": 0.05,
    "simulate_actual_mass": True,
    "actual_mass_deviation_pct": 0.3,
    "log_all_commands": True,
    "simulate_formula_step_delay_ms": 1500,
}


def load_config(path: str | None) -> dict[str, Any]:
    cfg = DEFAULT_CONFIG.copy()
    if path:
        p = Path(path)
        if p.exists():
            with open(p, encoding="utf-8") as f:
                overrides = json.load(f)
                # 忽略注释字段
                cfg.update({k: v for k, v in overrides.items() if not k.startswith("_")})
        else:
            logging.warning(f"配置文件不存在，使用默认配置：{path}")
    return cfg


# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [mock-qt] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("mock-qt")

# ---------------------------------------------------------------------------
# 应用状态
# ---------------------------------------------------------------------------
app = FastAPI(title="mock-qt 控制程序模拟服务", version="1.0.0")

# 全局配置（启动时注入）
CFG: dict[str, Any] = {}

# 当前正在执行的任务：command_id -> asyncio.Task
_running_tasks: dict[str, asyncio.Task] = {}

# 设备状态
_device_state = {
    "status": "idle",          # idle | executing | error
    "current_command_id": None,
}


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _validate_command_basics(body: dict) -> str | None:
    """
    基础格式校验，返回 command_id（校验通过）或抛出错误信息（校验失败）。
    只做必填字段检查，不做业务逻辑。
    """
    required = ["schema_version", "command_id", "timestamp", "operator_id", "command_type", "payload"]
    for field in required:
        if field not in body:
            raise ValueError(f"缺少必填字段：{field}")

    # command_id 必须是合法 UUID
    try:
        UUID(body["command_id"])
    except (ValueError, AttributeError):
        raise ValueError(f"command_id 不是合法的 UUID v4：{body['command_id']}")

    valid_types = [
        "dispense", "aliquot", "mix", "formula",
        "query_stock", "restock", "cancel", "emergency_stop", "device_status",
    ]
    if body["command_type"] not in valid_types:
        raise ValueError(f"未知的 command_type：{body['command_type']}")

    return body["command_id"]


def _simulate_actual_mass(target_mg: int) -> tuple[int, int]:
    """
    模拟实际称量值：在目标质量附近加随机偏差。
    返回 (actual_mass_mg, deviation_mg)。
    """
    deviation_pct = CFG.get("actual_mass_deviation_pct", 0.3) / 100.0
    max_dev = max(1, int(target_mg * deviation_pct))
    dev = random.randint(-max_dev, max_dev)
    actual = target_mg + dev
    return actual, dev


async def _do_callback(payload: dict) -> None:
    """异步 POST 回调到 AI 层，失败时只记日志，不抛出。"""
    url = CFG["ai_callback_url"]
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            logger.info(f"回调 {url} -> HTTP {resp.status_code}")
    except Exception as e:
        logger.error(f"回调失败（AI层未就绪或地址错误）：{e}")


# ---------------------------------------------------------------------------
# 各指令类型的后台执行逻辑
# ---------------------------------------------------------------------------

async def _execute_dispense(command_id: str, payload: dict) -> None:
    """模拟单步 dispense 执行。"""
    delay = CFG["execution_delay_ms"] / 1000.0
    await asyncio.sleep(delay)

    failed = random.random() < CFG["failure_rate"]
    completed_at = now_iso()

    if failed:
        await _do_callback({
            "command_id": command_id,
            "status": "failed",
            "completed_at": completed_at,
            "result": None,
            "error": {"code": "HARDWARE_ERROR", "message": "模拟：下料电机通信超时"},
        })
    else:
        target_mg = payload.get("target_mass_mg", 1000)
        actual, dev = _simulate_actual_mass(target_mg)
        await _do_callback({
            "command_id": command_id,
            "status": "completed",
            "completed_at": completed_at,
            "result": {
                "actual_mass_mg": actual,
                "deviation_mg": dev,
                "vessel": payload.get("target_vessel", "unknown"),
            },
            "error": None,
        })


async def _execute_aliquot(command_id: str, payload: dict) -> None:
    """模拟分料执行：逐份执行，每份独立延迟。"""
    portions = payload.get("portions", 1)
    mass_per = payload.get("mass_per_portion_mg", 1000)
    vessels = payload.get("target_vessels", [f"V{i}" for i in range(portions)])
    step_delay = CFG["execution_delay_ms"] / 1000.0

    step_results = []
    for i in range(portions):
        await asyncio.sleep(step_delay)
        if random.random() < CFG["failure_rate"]:
            await _do_callback({
                "command_id": command_id,
                "status": "failed",
                "completed_at": now_iso(),
                "result": {"completed_portions": i, "steps": step_results},
                "error": {"code": "HARDWARE_ERROR", "message": f"模拟：第 {i+1} 份下料失败"},
            })
            return
        actual, dev = _simulate_actual_mass(mass_per)
        step_results.append({
            "portion_index": i + 1,
            "vessel": vessels[i] if i < len(vessels) else f"V{i}",
            "actual_mass_mg": actual,
            "deviation_mg": dev,
        })

    await _do_callback({
        "command_id": command_id,
        "status": "completed",
        "completed_at": now_iso(),
        "result": {"portions": portions, "steps": step_results},
        "error": None,
    })


async def _execute_mix(command_id: str, payload: dict) -> None:
    """模拟混合配方执行：按组分顺序逐步执行。"""
    components = payload.get("components", [])
    step_delay = CFG["execution_delay_ms"] / 1000.0
    step_results = []

    for i, comp in enumerate(components):
        await asyncio.sleep(step_delay)
        if random.random() < CFG["failure_rate"]:
            await _do_callback({
                "command_id": command_id,
                "status": "failed",
                "completed_at": now_iso(),
                "result": {"completed_components": i, "steps": step_results},
                "error": {
                    "code": "HARDWARE_ERROR",
                    "message": f"模拟：组分 {comp.get('reagent_name_cn', i)} 下料失败",
                },
            })
            return
        target_mg = comp.get("calculated_mass_mg", 1000)
        actual, dev = _simulate_actual_mass(target_mg)
        step_results.append({
            "component_index": i + 1,
            "reagent_code": comp.get("reagent_code", ""),
            "reagent_name_cn": comp.get("reagent_name_cn", ""),
            "actual_mass_mg": actual,
            "deviation_mg": dev,
        })

    await _do_callback({
        "command_id": command_id,
        "status": "completed",
        "completed_at": now_iso(),
        "result": {
            "target_vessel": payload.get("target_vessel", "main"),
            "steps": step_results,
        },
        "error": None,
    })


async def _execute_formula(command_id: str, payload: dict) -> None:
    """模拟多步配方执行：按步骤顺序执行，任一步失败按 on_step_failure 策略处理。"""
    steps = payload.get("steps", [])
    on_failure = payload.get("on_step_failure", "pause_and_notify")
    step_delay = CFG.get("simulate_formula_step_delay_ms", 1500) / 1000.0
    step_results = []

    for step in steps:
        await asyncio.sleep(step_delay)
        step_idx = step.get("step_index", len(step_results) + 1)
        step_payload = step.get("payload", {})
        target_mg = step_payload.get("target_mass_mg", 1000)

        if random.random() < CFG["failure_rate"]:
            step_results.append({
                "step_index": step_idx,
                "status": "failed",
                "actual_mass_mg": None,
                "error": "模拟：步骤执行失败",
            })
            if on_failure == "abort_all":
                await _do_callback({
                    "command_id": command_id,
                    "status": "failed",
                    "completed_at": now_iso(),
                    "result": {"steps": step_results},
                    "error": {
                        "code": "STEP_FAILED",
                        "message": f"步骤 {step_idx} 失败，已中止全部",
                    },
                })
            else:
                # pause_and_notify：回调 partial，等待 AI 层处理
                await _do_callback({
                    "command_id": command_id,
                    "status": "partial",
                    "completed_at": now_iso(),
                    "result": {"steps": step_results},
                    "error": {
                        "code": "STEP_FAILED",
                        "message": f"步骤 {step_idx} 失败，已暂停等待处理",
                    },
                })
            return

        actual, dev = _simulate_actual_mass(target_mg)
        step_results.append({
            "step_index": step_idx,
            "status": "completed",
            "actual_mass_mg": actual,
            "deviation_mg": dev,
        })

    await _do_callback({
        "command_id": command_id,
        "status": "completed",
        "completed_at": now_iso(),
        "result": {"steps": step_results},
        "error": None,
    })


async def _execute_query_stock(command_id: str, payload: dict) -> None:
    """模拟库存查询：直接返回假数据。"""
    await asyncio.sleep(0.1)
    reagent_code = payload.get("reagent_code") or payload.get("reagent_name_cn") or "UNKNOWN"
    await _do_callback({
        "command_id": command_id,
        "status": "completed",
        "completed_at": now_iso(),
        "result": {
            "reagent_code": reagent_code,
            "stock_mg": random.randint(10000, 500000),
            "note": "模拟数据，非真实库存",
        },
        "error": None,
    })


async def _run_task(command_id: str, command_type: str, payload: dict) -> None:
    """后台任务入口，执行完成后清理状态。"""
    try:
        _device_state["status"] = "executing"
        _device_state["current_command_id"] = command_id

        if command_type == "dispense":
            await _execute_dispense(command_id, payload)
        elif command_type == "aliquot":
            await _execute_aliquot(command_id, payload)
        elif command_type == "mix":
            await _execute_mix(command_id, payload)
        elif command_type == "formula":
            await _execute_formula(command_id, payload)
        elif command_type == "query_stock":
            await _execute_query_stock(command_id, payload)
        elif command_type in ("restock", "device_status"):
            # 简单延迟后回调成功
            await asyncio.sleep(CFG["execution_delay_ms"] / 1000.0)
            await _do_callback({
                "command_id": command_id,
                "status": "completed",
                "completed_at": now_iso(),
                "result": {"note": f"模拟 {command_type} 完成"},
                "error": None,
            })
    except asyncio.CancelledError:
        logger.info(f"任务被取消：{command_id}")
        await _do_callback({
            "command_id": command_id,
            "status": "cancelled",
            "completed_at": now_iso(),
            "result": None,
            "error": None,
        })
    finally:
        _running_tasks.pop(command_id, None)
        if _device_state["current_command_id"] == command_id:
            _device_state["status"] = "idle"
            _device_state["current_command_id"] = None


# ---------------------------------------------------------------------------
# API 路由
# ---------------------------------------------------------------------------

@app.post("/api/command")
async def receive_command(request: Request) -> JSONResponse:
    received_at = now_iso()

    # 解析请求体
    try:
        body: dict = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求体不是合法 JSON")

    # 日志
    if CFG.get("log_all_commands"):
        logger.info(f"收到指令：{json.dumps(body, ensure_ascii=False, indent=2)}")

    # 基础格式校验
    try:
        command_id = _validate_command_basics(body)
    except ValueError as e:
        logger.warning(f"指令格式错误：{e}")
        return JSONResponse(status_code=400, content={
            "command_id": body.get("command_id", "unknown"),
            "received_at": received_at,
            "status": "rejected",
            "message": f"FORMAT_ERROR: {e}",
        })

    command_type: str = body["command_type"]
    payload: dict = body.get("payload", {})

    # --- emergency_stop：立即处理，取消所有进行中任务 ---
    if command_type == "emergency_stop":
        cancelled = list(_running_tasks.keys())
        for task in list(_running_tasks.values()):
            task.cancel()
        _device_state["status"] = "idle"
        _device_state["current_command_id"] = None
        logger.warning(f"紧急停止！取消任务：{cancelled}")
        return JSONResponse(content={
            "command_id": command_id,
            "received_at": received_at,
            "status": "accepted",
            "message": f"emergency_stop 已执行，取消任务数：{len(cancelled)}",
        })

    # --- cancel：取消指定任务 ---
    if command_type == "cancel":
        target_id = payload.get("target_command_id")
        if target_id and target_id in _running_tasks:
            _running_tasks[target_id].cancel()
            logger.info(f"取消任务：{target_id}")
            return JSONResponse(content={
                "command_id": command_id,
                "received_at": received_at,
                "status": "accepted",
                "message": f"已取消任务：{target_id}",
            })
        else:
            return JSONResponse(content={
                "command_id": command_id,
                "received_at": received_at,
                "status": "rejected",
                "message": f"TASK_NOT_FOUND: 找不到可取消的任务 {target_id}",
            })

    # --- 幂等检查：同一 command_id 不重复执行 ---
    if command_id in _running_tasks:
        logger.warning(f"重复指令，已忽略：{command_id}")
        return JSONResponse(content={
            "command_id": command_id,
            "received_at": received_at,
            "status": "rejected",
            "message": "DUPLICATE_COMMAND: 该指令已在执行中",
        })

    # --- 设备忙检查（emergency_stop/cancel/query 类不受此限制）---
    non_blocking_types = {"query_stock", "device_status"}
    if (
        _device_state["status"] == "executing"
        and command_type not in non_blocking_types
    ):
        logger.warning(f"设备忙，拒绝指令：{command_id} ({command_type})")
        return JSONResponse(content={
            "command_id": command_id,
            "received_at": received_at,
            "status": "rejected",
            "message": f"DEVICE_BUSY: 设备正在执行 {_device_state['current_command_id']}",
        })

    # --- 接受指令，启动后台执行任务 ---
    task = asyncio.create_task(_run_task(command_id, command_type, payload))
    _running_tasks[command_id] = task
    logger.info(f"接受指令：{command_id} ({command_type})")

    return JSONResponse(content={
        "command_id": command_id,
        "received_at": received_at,
        "status": "accepted",
        "message": "",
    })


@app.get("/api/status")
async def get_status() -> JSONResponse:
    return JSONResponse(content={
        "device_status": _device_state["status"],
        "balance_ready": True,   # mock 中天平始终就绪
        "current_command_id": _device_state["current_command_id"],
        "running_task_count": len(_running_tasks),
        "timestamp": now_iso(),
    })


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(content={"status": "ok", "service": "mock-qt"})


# ---------------------------------------------------------------------------
# 启动入口
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="mock-qt：模拟 C++ 后级控制程序")
    parser.add_argument("--port", type=int, default=None, help="监听端口（默认读 config.json）")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="监听地址")
    parser.add_argument("--config", type=str, default="config.json", help="配置文件路径")
    args = parser.parse_args()

    global CFG
    CFG = load_config(args.config)

    port = args.port if args.port is not None else CFG.get("port", 9000)

    logger.info("=" * 60)
    logger.info("mock-qt 启动 —— 仅用于开发联调，不可用于生产")
    logger.info(f"  监听端口        : {port}")
    logger.info(f"  AI 回调地址     : {CFG['ai_callback_url']}")
    logger.info(f"  模拟执行延迟    : {CFG['execution_delay_ms']} ms")
    logger.info(f"  模拟失败率      : {CFG['failure_rate'] * 100:.1f}%")
    logger.info(f"  模拟称量偏差    : ±{CFG['actual_mass_deviation_pct']}%")
    logger.info("=" * 60)

    uvicorn.run(app, host=args.host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
