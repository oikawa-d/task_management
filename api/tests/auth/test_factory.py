from app.auth.factory import get_auth_strategy
from app.auth.jwt_auth import JwtAuthStrategy
from app.auth.session_auth import SessionAuthStrategy
from app.core.config import get_backend_settings


def test_factory_returns_cached_strategy_for_configured_mode(monkeypatch):
	try:
		get_auth_strategy.cache_clear()
		monkeypatch.setenv("AUTH_MODE", "session")
		get_backend_settings.cache_clear()
		assert isinstance(get_auth_strategy(), SessionAuthStrategy)
		assert get_auth_strategy() is get_auth_strategy()

		get_auth_strategy.cache_clear()
		monkeypatch.setenv("AUTH_MODE", "jwt")
		get_backend_settings.cache_clear()
		assert isinstance(get_auth_strategy(), JwtAuthStrategy)
	finally:
		# get_auth_strategyはlru_cache(maxsize=1)でプロセス全体に共有されるため、
		# ここで固定したjwtモードのインスタンスを残すと、他のテスト（実アプリ経由でauth_strategyの
		# 実インスタンスを使う結合テスト等）がAUTH_MODE環境変数と無関係にjwtへ固定されてしまう。
		get_auth_strategy.cache_clear()
