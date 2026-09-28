"""`app.core.config.BackendSettings`の環境変数バリデーション（必須項目・CORS・
本番環境の安全境界・TTL/文字数上限）を検証するテスト。
"""

import pytest
from app.core.config import BackendSettings
from app.core.constants import PASSWORD_MIN_LENGTH, TOKEN_URLSAFE_LENGTH
from pydantic import ValidationError


def _base_env(monkeypatch: pytest.MonkeyPatch) -> None:
	"""`BackendSettings`が読み込みに最低限必要な環境変数一式を設定するヘルパー関数。

	Args:
		monkeypatch: 環境変数を設定するための`pytest.MonkeyPatch`。
	"""
	monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://cerberus:cerberus@localhost:5432/cerberus_test")
	monkeypatch.setenv("JWT_SECRET_KEY", "secret")
	monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")
	monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret")
	monkeypatch.setenv("INITIAL_ADMIN_EMAIL", "admin@example.com")
	monkeypatch.setenv("INITIAL_ADMIN_USERNAME", "admin")
	monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "password")


def test_settings_valid_env_ok(monkeypatch: pytest.MonkeyPatch) -> None:
	"""必須環境変数が一通り揃っている場合、`BackendSettings`の生成に成功し、
	`database_url`が期待するドライバプレフィックスで始まることを検証する。
	"""
	_base_env(monkeypatch)

	settings = BackendSettings(_env_file=None)

	assert settings.database_url.startswith("postgresql+asyncpg://")


def test_settings_missing_database_url_raises(monkeypatch: pytest.MonkeyPatch) -> None:
	"""必須の`DATABASE_URL`が未設定の場合、`BackendSettings`の生成が`ValidationError`で失敗することを検証する。"""
	_base_env(monkeypatch)
	monkeypatch.delenv("DATABASE_URL", raising=False)

	with pytest.raises(ValidationError):
		BackendSettings(_env_file=None)


def test_settings_missing_jwt_secret_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
	"""必須の`JWT_SECRET_KEY`が未設定の場合、`BackendSettings`の生成が`ValidationError`で失敗することを検証する。"""
	_base_env(monkeypatch)
	monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

	with pytest.raises(ValidationError):
		BackendSettings(_env_file=None)


def test_settings_missing_initial_admin_raises(monkeypatch: pytest.MonkeyPatch) -> None:
	"""`INITIAL_ADMIN_EMAIL`が空文字の場合、`BackendSettings`の生成が`ValidationError`で失敗することを検証する。"""
	_base_env(monkeypatch)
	monkeypatch.setenv("INITIAL_ADMIN_EMAIL", "")

	with pytest.raises(ValidationError):
		BackendSettings(_env_file=None)


def test_settings_cors_origins_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
	"""`CORS_ALLOW_ORIGINS`にカンマ区切りで複数Originを設定した場合、
	`cors_allow_origins`がリストへ正しく分割されることを検証する。
	"""
	_base_env(monkeypatch)
	monkeypatch.setenv("CORS_ALLOW_ORIGINS", "http://a,http://b")

	settings = BackendSettings(_env_file=None)

	assert settings.cors_allow_origins == ["http://a", "http://b"]


def test_settings_cors_origins_wildcard_raises(monkeypatch: pytest.MonkeyPatch) -> None:
	"""`CORS_ALLOW_ORIGINS`にワイルドカード`*`を設定した場合、
	`allow_credentials`との併用禁止方針により`ValidationError`が送出されることを検証する。
	"""
	_base_env(monkeypatch)
	monkeypatch.setenv("CORS_ALLOW_ORIGINS", "*")

	with pytest.raises(ValidationError):
		BackendSettings(_env_file=None)


def test_settings_cors_methods_and_headers_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
	"""`CORS_ALLOW_METHODS`・`CORS_ALLOW_HEADERS`にカンマ区切りの値を設定した場合、
	それぞれがリストへ正しく分割されることを検証する。
	"""
	_base_env(monkeypatch)
	monkeypatch.setenv("CORS_ALLOW_METHODS", "GET,POST")
	monkeypatch.setenv("CORS_ALLOW_HEADERS", "Content-Type,X-CSRF-Token")

	settings = BackendSettings(_env_file=None)

	assert settings.cors_allow_methods == ["GET", "POST"]
	assert settings.cors_allow_headers == ["Content-Type", "X-CSRF-Token"]


def test_settings_bool_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
	"""`COOKIE_SECURE=false`という文字列が、bool型フィールド`cookie_secure`へ
	`False`として正しく変換されることを検証する。
	"""
	_base_env(monkeypatch)
	monkeypatch.setenv("COOKIE_SECURE", "false")

	settings = BackendSettings(_env_file=None)

	assert settings.cookie_secure is False


def test_settings_unknown_auth_mode_raises(monkeypatch: pytest.MonkeyPatch) -> None:
	"""`AUTH_MODE`に想定外の値（"invalid"）を設定した場合、`ValidationError`が送出されることを検証する。"""
	_base_env(monkeypatch)
	monkeypatch.setenv("AUTH_MODE", "invalid")

	with pytest.raises(ValidationError):
		BackendSettings(_env_file=None)


def _production_env(monkeypatch: pytest.MonkeyPatch) -> None:
	"""本番環境（`APP_ENV=production`）想定の安全な設定一式を、基本環境変数に追加設定するヘルパー関数。

	Args:
		monkeypatch: 環境変数を設定するための`pytest.MonkeyPatch`。
	"""
	_base_env(monkeypatch)
	monkeypatch.setenv("APP_ENV", "production")
	monkeypatch.setenv("COOKIE_SECURE", "true")
	monkeypatch.setenv("SMTP_USE_TLS", "true")
	monkeypatch.setenv("FRONTEND_BASE_URL", "https://app.example.com")
	monkeypatch.setenv("GOOGLE_REDIRECT_URI", "https://app.example.com/api/auth/oauth/google/callback")
	monkeypatch.setenv("ENABLE_API_DOCS", "false")
	monkeypatch.setenv("JWT_SECRET_KEY", "a-production-jwt-secret")
	monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "a-production-google-secret")
	monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "A-production-admin-password-1!")


def test_settings_production_accepts_safe_security_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
	"""本番向けの安全な設定（Cookie secure・TLS有効・httpsの各URL・API docs無効等）を
	すべて満たす場合、`BackendSettings`の生成に成功することを検証する。
	"""
	_production_env(monkeypatch)

	settings = BackendSettings(_env_file=None)

	assert settings.app_env == "production"


@pytest.mark.parametrize("app_env", ["local", "ci"])
def test_settings_non_production_allows_development_security_boundaries(
	monkeypatch: pytest.MonkeyPatch, app_env: str
) -> None:
	"""`APP_ENV`が"local"または"ci"の場合、本番相当の安全境界チェックは適用されず、
	開発向けの緩い既定値のままでも`BackendSettings`の生成に成功することを検証する。
	"""
	_base_env(monkeypatch)
	monkeypatch.setenv("APP_ENV", app_env)

	settings = BackendSettings(_env_file=None)

	assert settings.app_env == app_env


@pytest.mark.parametrize(
	"field,value",
	[
		("COOKIE_SECURE", "false"),
		("SMTP_USE_TLS", "false"),
		("FRONTEND_BASE_URL", "http://app.example.com"),
		("GOOGLE_REDIRECT_URI", "http://app.example.com/callback"),
		("ENABLE_API_DOCS", "true"),
	],
)
def test_settings_production_rejects_insecure_boundaries(
	monkeypatch: pytest.MonkeyPatch, field: str, value: str
) -> None:
	"""本番環境で、Cookie非secure・TLS無効・http URL・API docs有効など、
	安全でない設定値を1項目でも設定すると`ValidationError`が送出されることを検証する。
	"""
	_production_env(monkeypatch)
	monkeypatch.setenv(field, value)

	with pytest.raises(ValidationError):
		BackendSettings(_env_file=None)


@pytest.mark.parametrize("field", ["JWT_SECRET_KEY", "GOOGLE_CLIENT_SECRET", "INITIAL_ADMIN_PASSWORD"])
@pytest.mark.parametrize("value", ["", "secret", "password", "changeme", "test-secret"])
def test_settings_production_rejects_development_placeholders(
	monkeypatch: pytest.MonkeyPatch, field: str, value: str
) -> None:
	"""本番環境で、`JWT_SECRET_KEY`・`GOOGLE_CLIENT_SECRET`・`INITIAL_ADMIN_PASSWORD`のいずれかに
	開発用のプレースホルダー値（空文字・"secret"・"password"・"changeme"・"test-secret"）を
	設定した場合、`ValidationError`が送出されることを検証する。
	"""
	_production_env(monkeypatch)
	monkeypatch.setenv(field, value)

	with pytest.raises(ValidationError):
		BackendSettings(_env_file=None)


# 各種TTL（有効期限）系環境変数のバリデーション対象一覧。
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
	"""セッション・アクセストークン・OAuth state等の各TTL系環境変数に0または負数を設定した場合、
	`ValidationError`が送出されることを検証する。
	"""
	_base_env(monkeypatch)
	monkeypatch.setenv(field, value)

	with pytest.raises(ValidationError):
		BackendSettings(_env_file=None)


def test_settings_every_ttl_field_is_validated() -> None:
	"""TTLフィールドを追加したのにバリデータへ登録し忘れる事故を防ぐ。"""
	ttl_fields = {name for name in BackendSettings.model_fields if name.endswith("_ttl_seconds")}
	covered = {field.lower() for field in TTL_ENV_FIELDS}

	assert ttl_fields == covered


@pytest.mark.parametrize("field", ["PASSWORD_MAX_LENGTH", "AUTH_TOKEN_MAX_LENGTH"])
@pytest.mark.parametrize("value", ["0", "-1"])
def test_settings_input_length_limits_must_be_positive(monkeypatch: pytest.MonkeyPatch, field: str, value: str) -> None:
	"""`PASSWORD_MAX_LENGTH`・`AUTH_TOKEN_MAX_LENGTH`に0または負数を設定した場合、
	`ValidationError`が送出されることを検証する。
	"""
	_base_env(monkeypatch)
	monkeypatch.setenv(field, value)

	with pytest.raises(ValidationError):
		BackendSettings(_env_file=None)


def test_settings_input_length_limits_are_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
	"""`PASSWORD_MAX_LENGTH`・`AUTH_TOKEN_MAX_LENGTH`に正の値を設定した場合、
	その値がそのまま`password_max_length`・`auth_token_max_length`へ反映されることを検証する。
	"""
	_base_env(monkeypatch)
	monkeypatch.setenv("PASSWORD_MAX_LENGTH", "64")
	monkeypatch.setenv("AUTH_TOKEN_MAX_LENGTH", "256")

	settings = BackendSettings(_env_file=None)

	assert settings.password_max_length == 64
	assert settings.auth_token_max_length == 256


@pytest.mark.parametrize("value", [TOKEN_URLSAFE_LENGTH - 1, TOKEN_URLSAFE_LENGTH])
def test_settings_auth_token_limit_matches_generated_token_boundary(
	monkeypatch: pytest.MonkeyPatch, value: int
) -> None:
	"""`AUTH_TOKEN_MAX_LENGTH`が`TOKEN_URLSAFE_LENGTH`（生成トークン長）ちょうどなら成功し、
	それより1小さい値では実際に生成されるトークン長を下回るため`ValidationError`になることを検証する。
	"""
	_base_env(monkeypatch)
	monkeypatch.setenv("AUTH_TOKEN_MAX_LENGTH", str(value))

	if value == TOKEN_URLSAFE_LENGTH:
		settings = BackendSettings(_env_file=None)
		assert settings.auth_token_max_length == TOKEN_URLSAFE_LENGTH
	else:
		with pytest.raises(ValidationError):
			BackendSettings(_env_file=None)


@pytest.mark.parametrize("value", [PASSWORD_MIN_LENGTH - 1, PASSWORD_MIN_LENGTH])
def test_settings_password_limit_matches_schema_minimum_boundary(monkeypatch: pytest.MonkeyPatch, value: int) -> None:
	"""`PASSWORD_MAX_LENGTH`が`PASSWORD_MIN_LENGTH`ちょうどなら成功し、
	それより1小さい値ではパスワード最小長を下回るため`ValidationError`になることを検証する。
	"""
	_base_env(monkeypatch)
	monkeypatch.setenv("PASSWORD_MAX_LENGTH", str(value))

	if value == PASSWORD_MIN_LENGTH:
		settings = BackendSettings(_env_file=None)
		assert settings.password_max_length == PASSWORD_MIN_LENGTH
	else:
		with pytest.raises(ValidationError):
			BackendSettings(_env_file=None)
