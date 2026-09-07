from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import get_backend_settings


@lru_cache
def get_db_engine() -> AsyncEngine:
	settings = get_backend_settings()
	return create_async_engine(
		settings.database_url,
		pool_size=settings.database_pool_size,
		max_overflow=settings.database_max_overflow,
	)
