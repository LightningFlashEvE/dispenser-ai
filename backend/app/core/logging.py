import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from app.core.config import settings

_FORMATTER = logging.Formatter(
    fmt="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)


def setup_logging() -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    # 清空已有 handler，避免重复
    for h in root.handlers[:]:
        root.removeHandler(h)

    # 1. 控制台输出
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(_FORMATTER)
    root.addHandler(stream_handler)

    # 2. 文件输出（按天轮转，保留 60 天）
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    file_handler = TimedRotatingFileHandler(
        filename=log_dir / "backend.log",
        when="midnight",
        interval=1,
        backupCount=60,
        encoding="utf-8",
    )
    file_handler.setFormatter(_FORMATTER)
    root.addHandler(file_handler)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.is_development else logging.WARNING
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
