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
	from app.core.config import get_backend_settings

	get_backend_settings.cache_clear()
	yield
	get_backend_settings.cache_clear()


_ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def _alembic_config() -> Config:
	return Config(str(_ALEMBIC_INI))


@pytest.fixture(scope="module")
def apply_migrations() -> None:
	command.upgrade(_alembic_config(), "head")
	yield
	command.downgrade(_alembic_config(), "base")


@pytest_asyncio.fixture
async def db_session(apply_migrations: None):
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
