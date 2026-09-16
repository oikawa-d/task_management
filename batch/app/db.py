from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_batch_settings


@lru_cache
def get_db_engine() -> AsyncEngine:
	settings = get_batch_settings()
	return create_async_engine(settings.database_url)


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
	return async_sessionmaker(bind=get_db_engine(), expire_on_commit=False)


async def get_db_session() -> AsyncIterator[AsyncSession]:
	session_factory = get_session_factory()
	async with session_factory() as session:
		yield session
