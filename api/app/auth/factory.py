from functools import lru_cache

from app.auth.base import AuthStrategy
from app.auth.session_auth import SessionAuthStrategy
from app.core.config import get_backend_settings


@lru_cache(maxsize=1)
def get_auth_strategy() -> AuthStrategy:
	settings = get_backend_settings()
	if settings.auth_mode == "session":
		return SessionAuthStrategy(settings)
	raise ValueError(f"unsupported auth mode: {settings.auth_mode}")
