from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _make_engine():
    db_path = Path(settings.sqlite_db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite+aiosqlite:///{db_path.resolve()}"
    return create_async_engine(url, echo=settings.is_development)


engine = _make_engine()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


_MIGRATIONS: dict[str, list[str]] = {
    "tasks": [
        "ALTER TABLE tasks ADD COLUMN intent_json TEXT",
        "ALTER TABLE tasks ADD COLUMN command_json TEXT",
        "ALTER TABLE tasks ADD COLUMN result_json TEXT",
        "ALTER TABLE tasks ADD COLUMN confirmed_at DATETIME",
        "ALTER TABLE tasks ADD COLUMN started_at DATETIME",
        "ALTER TABLE tasks ADD COLUMN completed_at DATETIME",
    ],
    "stations": [
        "ALTER TABLE stations ADD COLUMN created_at DATETIME",
    ],
    "dialog_sessions": [
        "ALTER TABLE dialog_sessions ADD COLUMN task_id VARCHAR(64)",
        "ALTER TABLE dialog_sessions ADD COLUMN created_at DATETIME",
        "ALTER TABLE dialog_sessions ADD COLUMN updated_at DATETIME",
    ],
}

_MIGRATION_BACKFILLS: dict[str, str] = {
    "UPDATE stations SET created_at = datetime('now') WHERE created_at IS NULL": "stations.created_at",
    "UPDATE dialog_sessions SET created_at = datetime('now') WHERE created_at IS NULL": "dialog_sessions.created_at",
    "UPDATE dialog_sessions SET updated_at = datetime('now') WHERE updated_at IS NULL": "dialog_sessions.updated_at",
}


def _migrate_schema(connection) -> None:
    """检查并补齐旧表缺失的列，回填空时间戳。"""
    inspector = inspect(connection)
    existing_tables = set(inspector.get_table_names())

    for table_name, alter_list in _MIGRATIONS.items():
        if table_name not in existing_tables:
            continue

        existing_cols = {col["name"] for col in inspector.get_columns(table_name)}
        for stmt in alter_list:
            col_name = _parse_add_column_name(stmt)
            if col_name and col_name not in existing_cols:
                try:
                    connection.execute(text(stmt))
                    logger.info("数据库迁移成功: %s", stmt)
                except Exception:
                    logger.exception("数据库迁移失败: %s", stmt)

    for update_stmt, label in _MIGRATION_BACKFILLS.items():
        try:
            result = connection.execute(text(update_stmt))
            if result.rowcount > 0:
                logger.info("数据库回填成功 (%d 行): %s", result.rowcount, label)
        except Exception:
            logger.exception("数据库回填失败: %s", label)


def _parse_add_column_name(alter_stmt: str) -> str | None:
    """从 ALTER TABLE ... ADD COLUMN col_name ... 中提取列名。"""
    parts = alter_stmt.split()
    try:
        add_idx = parts.index("ADD") if "ADD" in parts else -1
        col_idx = parts.index("COLUMN") if "COLUMN" in parts else add_idx
        if col_idx >= 0 and col_idx + 1 < len(parts):
            return parts[col_idx + 1]
    except ValueError:
        pass
    return None


async def init_db() -> None:
    """创建所有 ORM 模型对应的数据表，并插入种子数据。"""
    import app.models  # noqa: F401 — 延迟导入，避免循环依赖
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_schema)

    from app.core.seed_data import seed_database
    await seed_database()

    from app.core.seed_formulas import seed_formulas
    await seed_formulas()
