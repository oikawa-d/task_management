import pytest
from app.core.config import BackendSettings
from pydantic import ValidationError


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


TTL_ENV_FIELDS = [
	"SESSION_TTL_SECONDS",
	"SESSION_ABSOLUTE_TTL_SECONDS",
	"ACCESS_TOKEN_TTL_SECONDS",
	"REFRESH_TTL_SECONDS",
	"GOOGLE_JWKS_CACHE_TTL_SECONDS",
	"OAUTH_STATE_TTL_SECONDS",
	"OAUTH_HANDOFF_TTL_SECONDS",
	"PASSWORD_RESET_TTL_SECONDS",
	"EMAIL_VERIFY_TTL_SECONDS",
]


@pytest.mark.parametrize("field", TTL_ENV_FIELDS)
@pytest.mark.parametrize("value", ["0", "-1"])
def test_settings_auth_ttl_must_be_positive(monkeypatch: pytest.MonkeyPatch, field: str, value: str) -> None:
	_base_env(monkeypatch)
	monkeypatch.setenv(field, value)

	with pytest.raises(ValidationError):
		BackendSettings(_env_file=None)


def test_settings_every_ttl_field_is_validated() -> None:
	"""TTLフィールドを追加したのにバリデータへ登録し忘れる事故を防ぐ。"""
	ttl_fields = {name for name in BackendSettings.model_fields if name.endswith("_ttl_seconds")}
	covered = {field.lower() for field in TTL_ENV_FIELDS}

	assert ttl_fields == covered
