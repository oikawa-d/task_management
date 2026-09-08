from app.auth.factory import get_auth_strategy
from app.auth.session_auth import SessionAuthStrategy
from app.core.config import get_backend_settings


def test_factory_returns_cached_strategy_for_configured_mode(monkeypatch):
	get_auth_strategy.cache_clear()
	monkeypatch.setenv("AUTH_MODE", "session")
	get_backend_settings.cache_clear()
	assert isinstance(get_auth_strategy(), SessionAuthStrategy)
	assert get_auth_strategy() is get_auth_strategy()
