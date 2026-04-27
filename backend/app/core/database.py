from collections.abc import AsyncGenerator
from pathlib import Path

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
    """创建所有 ORM 模型对应的数据表，并插入种子数据。"""
    import app.models  # noqa: F401 — 延迟导入，避免循环依赖
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from app.core.seed_data import seed_database
    await seed_database()

    from app.core.seed_formulas import seed_formulas
    await seed_formulas()
