import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def _alembic_config() -> Config:
	return Config(str(ALEMBIC_INI))


def _sync_database_url() -> str:
	return os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)


def _pgcrypto_installed() -> bool:
	engine = create_engine(_sync_database_url())
	try:
		with engine.connect() as connection:
			row = connection.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'pgcrypto'")).scalar()
		return row == 1
	finally:
		engine.dispose()


def _login_history_id_comment() -> str | None:
	engine = create_engine(_sync_database_url())
	try:
		with engine.connect() as connection:
			return connection.execute(
				text(
					"SELECT col_description(attrelid, attnum) "
					"FROM pg_catalog.pg_attribute "
					"WHERE attrelid = 'login_history'::regclass AND attname = 'id'"
				)
			).scalar()
	finally:
		engine.dispose()


@pytest.fixture(autouse=True)
def _reset_schema():
	command.downgrade(_alembic_config(), "base")
	yield
	command.downgrade(_alembic_config(), "base")


def test_migration_upgrade_head_succeeds() -> None:
	command.upgrade(_alembic_config(), "head")


def test_migration_pgcrypto_extension_enabled_after_upgrade() -> None:
	command.upgrade(_alembic_config(), "head")

	assert _pgcrypto_installed() is True


def test_migration_downgrade_full_chain() -> None:
	cfg = _alembic_config()
	command.upgrade(cfg, "head")

	command.downgrade(cfg, "base")

	assert _pgcrypto_installed() is False


def test_migration_upgrade_downgrade_upgrade_roundtrip() -> None:
	cfg = _alembic_config()
	command.upgrade(cfg, "head")
	command.downgrade(cfg, "base")

	command.upgrade(cfg, "head")

	assert _pgcrypto_installed() is True


def test_login_history_comment_migration_downgrade_restores_previous_comment() -> None:
	cfg = _alembic_config()
	command.upgrade(cfg, "head")

	assert _login_history_id_comment() is None

	command.downgrade(cfg, "0017")

	assert _login_history_id_comment() == "ログイン試行を一意に識別するUUID"
