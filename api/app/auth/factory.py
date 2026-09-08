from functools import lru_cache

from app.auth.base import AuthStrategy
from app.auth.jwt_auth import JwtAuthStrategy
from app.auth.session_auth import SessionAuthStrategy
from app.core.config import get_backend_settings


@lru_cache(maxsize=1)
def get_auth_strategy() -> AuthStrategy:
	settings = get_backend_settings()
	if settings.auth_mode == "session":
		return SessionAuthStrategy(settings)
	if settings.auth_mode == "jwt":
		return JwtAuthStrategy(settings)
	raise ValueError(f"unsupported auth mode: {settings.auth_mode}")
