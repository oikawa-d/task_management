"""batchプロセスのDB接続（非同期SQLAlchemyエンジン・セッション）を管理するモジュール。

エンジン・セッションファクトリはプロセス内で使い回すためキャッシュし、
プロセス終了時やテストの後始末で`dispose_db_engine`により明示的に破棄する。
"""

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_batch_settings


@lru_cache
def get_db_engine() -> AsyncEngine:
	"""非同期SQLAlchemyエンジンのシングルトンを返す。

	`lru_cache`により初回呼び出し時に`BatchSettings.database_url`から
	エンジンを生成し、以降は同一インスタンスを再利用する。

	Returns:
		生成済みまたはキャッシュされた`AsyncEngine`。
	"""
	settings = get_batch_settings()
	return create_async_engine(settings.database_url)


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
	"""非同期DBセッションのファクトリのシングルトンを返す。

	`get_db_engine`が返すエンジンに紐づく`async_sessionmaker`を生成・キャッシュする。
	`expire_on_commit=False`により、コミット後もオブジェクト属性へアクセス可能にする。

	Returns:
		生成済みまたはキャッシュされた`async_sessionmaker`。
	"""
	return async_sessionmaker(bind=get_db_engine(), expire_on_commit=False)


async def get_db_session() -> AsyncIterator[AsyncSession]:
	"""DBセッションを1件生成し、利用後にクローズするジェネレータ。

	`async with`ブロックを抜ける際にセッションが自動的にクローズされる。

	Yields:
		利用可能な`AsyncSession`インスタンス。
	"""
	session_factory = get_session_factory()
	async with session_factory() as session:
		yield session


async def dispose_db_engine() -> None:
	"""キャッシュ済みのDBエンジン・セッションファクトリを破棄する。

	エンジンが未生成（キャッシュが空）の場合は何もしない。
	生成済みの場合はコネクションプールを解放したうえで、
	`get_db_engine`・`get_session_factory`のキャッシュをクリアする。
	プロセス終了時やテスト間の後始末で呼び出すことを想定する。
	"""
	if get_db_engine.cache_info().currsize == 0:
		return
	await get_db_engine().dispose()
	get_session_factory.cache_clear()
	get_db_engine.cache_clear()
