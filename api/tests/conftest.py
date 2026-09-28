"""api配下pytest共通のfixtureとテスト用環境変数のデフォルト値を定義するモジュール。

DB接続・Redis接続・JWT/OAuth関連の必須環境変数が未設定でもテストが起動できるよう、
モジュール読み込み時にデフォルト値を設定する。また、設定キャッシュのクリアや
Alembicマイグレーション適用、DBセッション生成などの共通fixtureを提供する。
"""

import os
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config

_REQUIRED_ENV_DEFAULTS = {
	"DATABASE_URL": "postgresql+asyncpg://cerberus:cerberus@localhost:5432/cerberus_test",
	"REDIS_URL": "redis://localhost:6379/1",
	"JWT_SECRET_KEY": "test-jwt-secret-key",
	"GOOGLE_CLIENT_ID": "test-google-client-id",
	"GOOGLE_CLIENT_SECRET": "test-google-client-secret",
	"INITIAL_ADMIN_EMAIL": "admin@example.com",
	"INITIAL_ADMIN_USERNAME": "admin",
	"INITIAL_ADMIN_PASSWORD": "test-admin-password",
}

for key, value in _REQUIRED_ENV_DEFAULTS.items():
	os.environ.setdefault(key, value)


@pytest.fixture(autouse=True)
def _clear_settings_cache():
	"""各テストの前後で`get_backend_settings`のlru_cacheをクリアするautouse fixture。

	何かを提供するfixtureではなく、テストごとに環境変数を書き換えても
	キャッシュされた古いSettingsが再利用されないようにするための副作用専用fixture。
	スコープは関数単位（デフォルト）。後片付けとして、テスト終了後にも
	再度キャッシュをクリアし、後続テストへ影響を残さないようにする。
	"""
	from app.core.config import get_backend_settings

	get_backend_settings.cache_clear()
	yield
	get_backend_settings.cache_clear()


_ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def _alembic_config() -> Config:
	"""`api/alembic.ini`を読み込んだAlembicの`Config`を生成するヘルパー関数。

	Returns:
		Config: `apply_migrations`fixtureがマイグレーションの適用・巻き戻しに使う設定。
	"""
	return Config(str(_ALEMBIC_INI))


@pytest.fixture(scope="module")
def apply_migrations() -> None:
	"""テスト用DBにAlembicマイグレーションを`head`まで適用するモジュールスコープfixture。

	モジュール内の最初の利用時に一度だけマイグレーションを実行し、
	同一モジュール内の後続テストで使い回す。後片付けとして、モジュール内の
	全テスト終了後にマイグレーションを`base`まで巻き戻し、DBスキーマを未適用状態に戻す。
	"""
	command.upgrade(_alembic_config(), "head")
	yield
	command.downgrade(_alembic_config(), "base")


@pytest_asyncio.fixture
async def db_session(apply_migrations: None):
	"""マイグレーション適用済みDBへの`AsyncSession`をテストごとに生成するfixture。

	テスト関数ごとに新しいイベントループで実行されるため、lru_cacheされた
	`app.db.get_db_engine()`は再利用せず、テスト専用の非同期engineとsessionを
	都度生成して提供する。後片付けとして、テスト内での変更をロールバックしたうえで
	engineを`dispose()`し、コネクションを解放する。

	Args:
		apply_migrations: DBスキーマが適用済みであることを保証する前提fixture。
	"""
	from app.core.config import get_backend_settings
	from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

	# テスト関数ごとに新しいイベントループで実行されるため、
	# lru_cacheされたapp.db.get_db_engine()を再利用せずテスト専用のengineを都度生成・破棄する。
	engine = create_async_engine(get_backend_settings().database_url)
	session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
	try:
		async with session_factory() as session:
			yield session
			await session.rollback()
	finally:
		await engine.dispose()
