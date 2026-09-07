import pytest
from app.core.config import BatchSettings
from pydantic import ValidationError


def test_settings_valid_env_ok(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://cerberus:cerberus@localhost:5432/cerberus_test")

	settings = BatchSettings(_env_file=None)

	assert settings.database_url.startswith("postgresql+asyncpg://")
	assert settings.notify_due_run_hours == "10,17"


def test_settings_missing_database_url_raises(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.delenv("DATABASE_URL", raising=False)

	with pytest.raises(ValidationError):
		BatchSettings(_env_file=None)


def test_settings_batch_enabled_bool_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://cerberus:cerberus@localhost:5432/cerberus_test")
	monkeypatch.setenv("BATCH_ENABLED", "false")

	settings = BatchSettings(_env_file=None)

	assert settings.batch_enabled is False
