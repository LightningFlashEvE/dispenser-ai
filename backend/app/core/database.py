from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


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


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        task_columns = await conn.execute(text("PRAGMA table_info(tasks)"))
        column_names = {row[1] for row in task_columns.fetchall()}
        if "command_id" not in column_names:
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN command_id VARCHAR(36)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tasks_command_id ON tasks (command_id)"))
