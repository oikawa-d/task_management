from app.db import get_db_engine, get_db_session, get_session_factory
from sqlalchemy.ext.asyncio import AsyncSession


def test_get_db_engine_returns_singleton() -> None:
	assert get_db_engine() is get_db_engine()


def test_get_session_factory_bound_to_engine() -> None:
	factory = get_session_factory()

	assert factory.kw["bind"] is get_db_engine()


async def test_get_db_session_yields_async_session_and_closes() -> None:
	agen = get_db_session()
	session = await agen.__anext__()
	try:
		assert isinstance(session, AsyncSession)
	finally:
		await agen.aclose()
