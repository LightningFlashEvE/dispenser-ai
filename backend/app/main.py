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
from app.ws.channels import router as ws_router
from app.core.config import settings
from app.core.database import init_db
from app.core.logging import setup_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    setup_logging()
    logger.info(f"dispenser-ai 后端启动，环境：{settings.env}")
    await init_db()
    logger.info("数据库初始化完成")
    yield
    from app.services.ai.llm import get_llm
    from app.services.device.control_client import get_control_client

    llm = get_llm()
    await llm.close()
    logger.info("LLM 客户端已关闭")

    client = get_control_client()
    await client.close()
    logger.info("控制客户端已关闭")

    logger.info("dispenser-ai 后端关闭")


app = FastAPI(
    title="dispenser-ai 后端",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000"] if settings.is_development else [],
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
app.include_router(ws_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "env": settings.env}
