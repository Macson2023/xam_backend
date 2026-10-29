from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool, StaticPool

from app.core.config import settings


def build_engine(url: str, echo: bool = False) -> AsyncEngine:
    kwargs: dict = {"echo": echo, "pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs.pop("pool_pre_ping")
        kwargs["poolclass"] = StaticPool if ":memory:" in url else NullPool
    return create_async_engine(url, **kwargs)


engine = build_engine(settings.database_url, settings.database_echo)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
