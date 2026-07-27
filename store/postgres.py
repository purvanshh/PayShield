import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

logger = logging.getLogger(__name__)

DATABASE_URL = "postgresql+asyncpg://payshield:payshield@localhost:5432/payshield"

_engine = None
_session_maker = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(DATABASE_URL, pool_size=10, max_overflow=20, echo=False)
    return _engine


def get_session_maker():
    global _session_maker
    if _session_maker is None:
        _session_maker = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_maker


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    session = get_session_maker()
    async with session() as s:
        try:
            yield s
        finally:
            await s.close()


async def init_db():
    from store.models import Base
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created")


async def close_db():
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None
        logger.info("Database engine disposed")
