"""PostgreSQL用の非同期SQLAlchemyエンジン・セッションファクトリを提供するモジュール。"""

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_backend_settings


@lru_cache
def get_db_engine() -> AsyncEngine:
	"""設定値（接続URL・プールサイズ）に基づく非同期DBエンジンを、プロセス内で1つだけ生成する。

	Returns:
		プロセス内で共有する`AsyncEngine`のシングルトンインスタンス。
	"""
	settings = get_backend_settings()
	return create_async_engine(
		settings.database_url,
		pool_size=settings.database_pool_size,
		max_overflow=settings.database_max_overflow,
	)


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
	"""`get_db_engine`のエンジンに紐づく非同期セッションファクトリを、プロセス内で1つだけ生成する。

	`expire_on_commit=False`により、コミット後もオブジェクト属性へアクセス可能にする。

	Returns:
		プロセス内で共有する`async_sessionmaker`のシングルトンインスタンス。
	"""
	return async_sessionmaker(bind=get_db_engine(), expire_on_commit=False)


async def get_db_session() -> AsyncIterator[AsyncSession]:
	"""FastAPIのDependsで利用する、リクエストスコープの非同期DBセッションを供給する。

	Yields:
		リクエスト処理中に使う`AsyncSession`。関数終了時（`async with`終了時）にクローズされる。
	"""
	session_factory = get_session_factory()
	async with session_factory() as session:
		yield session
