from uuid import uuid4

from app.core.config import BackendSettings
from app.service.auth_strategy import (
	AuthContext,
	AuthStrategy,
	JwtAuthStrategy,
	LoginResult,
	SessionAuthStrategy,
	get_auth_strategy,
)


def _settings(auth_mode: str) -> BackendSettings:
	return BackendSettings(
		_env_file=None,
		database_url="postgresql+asyncpg://user:password@localhost/db",
		jwt_secret_key="secret",
		google_client_id="client-id",
		google_client_secret="client-secret",
		initial_admin_email="admin@example.com",
		initial_admin_username="admin",
		initial_admin_password="password",
		auth_mode=auth_mode,
	)


def test_auth_context_keeps_only_authentication_context() -> None:
	user_id = uuid4()
	context = AuthContext(user_id=user_id, session_id="sid")

	assert context.user_id == user_id
	assert context.role is None


def test_login_result_allows_mode_specific_optional_values() -> None:
	result = LoginResult(auth_mode="session", csrf_token="csrf", expires_in=1800)

	assert result.access_token is None
	assert result.auth_mode == "session"


def test_get_auth_strategy_returns_cached_session_strategy() -> None:
	first = get_auth_strategy(_settings("session"))
	second = get_auth_strategy(_settings("session"))

	assert isinstance(first, SessionAuthStrategy)
	assert first is second


def test_get_auth_strategy_returns_jwt_strategy() -> None:
	strategy = get_auth_strategy(_settings("jwt"))

	assert isinstance(strategy, JwtAuthStrategy)


def test_strategies_implement_auth_strategy_interface() -> None:
	assert isinstance(get_auth_strategy(_settings("session")), AuthStrategy)
	assert isinstance(get_auth_strategy(_settings("jwt")), AuthStrategy)
