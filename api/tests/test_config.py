import pytest
from pydantic import ValidationError

from app.core.config import BackendSettings


def _base_env(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://cerberus:cerberus@localhost:5432/cerberus_test")
	monkeypatch.setenv("JWT_SECRET_KEY", "secret")
	monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")
	monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret")
	monkeypatch.setenv("INITIAL_ADMIN_EMAIL", "admin@example.com")
	monkeypatch.setenv("INITIAL_ADMIN_USERNAME", "admin")
	monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "password")


def test_settings_valid_env_ok(monkeypatch: pytest.MonkeyPatch) -> None:
	_base_env(monkeypatch)

	settings = BackendSettings(_env_file=None)

	assert settings.database_url.startswith("postgresql+asyncpg://")


def test_settings_missing_database_url_raises(monkeypatch: pytest.MonkeyPatch) -> None:
	_base_env(monkeypatch)
	monkeypatch.delenv("DATABASE_URL", raising=False)

	with pytest.raises(ValidationError):
		BackendSettings(_env_file=None)


def test_settings_missing_jwt_secret_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
	_base_env(monkeypatch)
	monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

	with pytest.raises(ValidationError):
		BackendSettings(_env_file=None)


def test_settings_missing_initial_admin_raises(monkeypatch: pytest.MonkeyPatch) -> None:
	_base_env(monkeypatch)
	monkeypatch.setenv("INITIAL_ADMIN_EMAIL", "")

	with pytest.raises(ValidationError):
		BackendSettings(_env_file=None)


def test_settings_cors_origins_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
	_base_env(monkeypatch)
	monkeypatch.setenv("CORS_ALLOW_ORIGINS", "http://a,http://b")

	settings = BackendSettings(_env_file=None)

	assert settings.cors_allow_origins == ["http://a", "http://b"]


def test_settings_bool_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
	_base_env(monkeypatch)
	monkeypatch.setenv("COOKIE_SECURE", "false")

	settings = BackendSettings(_env_file=None)

	assert settings.cookie_secure is False


def test_settings_unknown_auth_mode_raises(monkeypatch: pytest.MonkeyPatch) -> None:
	_base_env(monkeypatch)
	monkeypatch.setenv("AUTH_MODE", "invalid")

	with pytest.raises(ValidationError):
		BackendSettings(_env_file=None)
