import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

_ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def _alembic_config() -> Config:
	return Config(str(_ALEMBIC_INI))


def _sync_database_url() -> str:
	return os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)


@pytest.fixture(autouse=True)
def _reset_schema():
	cfg = _alembic_config()
	command.downgrade(cfg, "base")
	yield
	command.downgrade(cfg, "base")


def test_task_procedures_keep_legacy_signature_until_notification_tables_exist() -> None:
	cfg = _alembic_config()
	command.upgrade(cfg, "0010")

	engine = create_engine(_sync_database_url())
	try:
		with engine.begin() as connection:
			user_id = connection.execute(
				text(
					"INSERT INTO users (username, email, password_hash) "
					"VALUES ('migration-task', 'migration-task@example.com', 'hash') RETURNING id"
				)
			).scalar_one()
			connection.execute(
				text("CALL sp_create_task(NULL, :created_by, NULL, 'legacy', NULL, 'todo', NULL, NULL, NULL)"),
				{"created_by": user_id},
			)

		with engine.connect() as connection:
			assert connection.execute(text("SELECT count(*) FROM tasks WHERE title = 'legacy'")).scalar_one() == 1
			assert connection.execute(text("SELECT to_regclass('public.notifications')")).scalar_one() is None
	finally:
		engine.dispose()


def test_task_notification_procedure_revision_is_reversible() -> None:
	cfg = _alembic_config()
	command.upgrade(cfg, "head")

	engine = create_engine(_sync_database_url())
	try:
		with engine.connect() as connection:
			for procedure_name in ("sp_create_task", "sp_update_task"):
				argument_names = connection.execute(
					text("SELECT p.proargnames FROM pg_proc p WHERE p.proname = :procedure_name"),
					{"procedure_name": procedure_name},
				).scalar_one()
				assert {"p_day_start_utc", "p_day_end_utc"} <= set(argument_names)

		command.downgrade(cfg, "0015")
		with engine.connect() as connection:
			for procedure_name in ("sp_create_task", "sp_update_task"):
				argument_names = connection.execute(
					text("SELECT p.proargnames FROM pg_proc p WHERE p.proname = :procedure_name"),
					{"procedure_name": procedure_name},
				).scalar_one()
				assert not {"p_day_start_utc", "p_day_end_utc"} & set(argument_names)
	finally:
		engine.dispose()
