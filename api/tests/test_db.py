"""`app.db`のDBエンジン・セッションファクトリ・非同期セッション取得ヘルパーのテスト。"""

from app.db import get_db_engine, get_db_session, get_session_factory
from sqlalchemy.ext.asyncio import AsyncSession


def test_get_db_engine_returns_singleton() -> None:
	"""`get_db_engine`が`lru_cache`により、複数回呼び出しても同一の`AsyncEngine`インスタンスを返すことを検証する。"""
	assert get_db_engine() is get_db_engine()


def test_get_session_factory_bound_to_engine() -> None:
	"""`get_session_factory`が返す`async_sessionmaker`のbind先が`get_db_engine()`と同一エンジンであることを検証する。"""
	factory = get_session_factory()

	assert factory.kw["bind"] is get_db_engine()


async def test_get_db_session_yields_async_session_and_closes() -> None:
	"""`get_db_session`の非同期ジェネレータが`AsyncSession`を1件yieldし、`aclose()`でエラー無く終了できることを検証する。"""
	agen = get_db_session()
	session = await agen.__anext__()
	try:
		assert isinstance(session, AsyncSession)
	finally:
		await agen.aclose()
