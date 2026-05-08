import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.drugs import router as drugs_router
from app.api.formulas import router as formulas_router
from app.api.tasks import router as tasks_router
from app.api.stations import router as stations_router
from app.api.device import router as device_router
from app.api.logs import router as logs_router
from app.api.manual import router as manual_router
from app.api.system import router as system_router
from app.api.dialog_sessions import router as dialog_sessions_router
from app.api.reagent_bottles import router as reagent_bottles_router
from app.api.debug import router as debug_router
from app.ws.channels import router as ws_router
from app.core.config import settings
from app.core.database import init_db
from app.core.logging import setup_logging, get_logger

logger = get_logger(__name__)
_tts_warmup_task: asyncio.Task | None = None


async def _warmup_tts_background() -> None:
    """Warm up TTS without blocking FastAPI startup health checks."""
    try:
        from app.services.ai.tts import get_tts_client

        tts = get_tts_client()
        await tts.health()
        for attempt_idx, warmup_text in enumerate([
            "配药助手已就绪",
            "配药小助手启动完成",
        ]):
            try:
                result = await asyncio.wait_for(
                    tts.speak(warmup_text, interrupt=True, speed=settings.tts_speed),
                    timeout=30.0,
                )
                if result and result.get("audio_base64"):
                    logger.info("TTS 预热完成（尝试 %d）", attempt_idx + 1)
                    break
                logger.warning("TTS 预热返回空结果，继续重试")
            except asyncio.TimeoutError:
                logger.warning("TTS 预热超时（尝试 %d）", attempt_idx + 1)
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001
        logger.warning("TTS 预热失败（服务继续）: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _tts_warmup_task

    setup_logging()
    logger.info(f"dispenser-ai 后端启动，环境：{settings.env}")
    await init_db()
    logger.info("数据库初始化完成")

    # 预热 intent schema validator（启动时暴露 schema 文件缺失问题）
    try:
        from app.services.dialog.intent import get_intent_validator

        get_intent_validator()
        logger.info("intent_schema.json 加载成功（Draft-07）")
    except Exception as e:  # noqa: BLE001
        logger.error("intent_schema.json 加载失败: %s（服务继续，但 Schema 校验将降级）", e)

    # 预热 TTS（避免首次用户请求时模型冷启动导致延迟），但不能阻塞 /health 就绪。
    _tts_warmup_task = asyncio.create_task(_warmup_tts_background())
    logger.info("TTS 后台预热已启动")

    try:
        from app.services.device.weight_stream import start_weight_stream

        await start_weight_stream()
        logger.info("重量流订阅已启动")
    except Exception as e:  # noqa: BLE001
        logger.warning("重量流订阅启动失败（服务继续）: %s", e)

    yield

    from app.services.ai.llm import get_llm
    from app.services.device.control_client import get_control_client
    from app.services.device.weight_stream import stop_weight_stream

    if _tts_warmup_task is not None:
        _tts_warmup_task.cancel()
        try:
            await _tts_warmup_task
        except asyncio.CancelledError:
            pass
        _tts_warmup_task = None

    try:
        await stop_weight_stream()
        logger.info("重量流订阅已关闭")
    except Exception:  # noqa: BLE001
        logger.exception("关闭重量流订阅异常")

    try:
        await get_llm().close()
        logger.info("LLM 客户端已关闭")
    except Exception:  # noqa: BLE001
        logger.exception("关闭 LLM 客户端异常")

    try:
        await get_control_client().close()
        logger.info("控制客户端已关闭")
    except Exception:  # noqa: BLE001
        logger.exception("关闭控制客户端异常")

    logger.info("dispenser-ai 后端关闭")


app = FastAPI(
    title="dispenser-ai 后端",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(drugs_router)
app.include_router(formulas_router)
app.include_router(tasks_router)
app.include_router(stations_router)
app.include_router(device_router)
app.include_router(logs_router)
app.include_router(manual_router)
app.include_router(system_router)
app.include_router(dialog_sessions_router)
app.include_router(reagent_bottles_router)
app.include_router(debug_router)
app.include_router(ws_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "env": settings.env, "version": "0.2.0"}
