from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from fastapi import Request, Response

from app.core.config import AuthMode, BackendSettings, get_backend_settings
from app.models.user import User


@dataclass(frozen=True)
class AuthContext:
	user_id: UUID
	role: str | None = None
	username: str | None = None
	session_id: str | None = None


@dataclass(frozen=True)
class LoginResult:
	auth_mode: AuthMode
	access_token: str | None = None
	refresh_token: str | None = None
	csrf_token: str | None = None
	expires_in: int | None = None


class AuthStrategy(ABC):
	mode: AuthMode

	def __init__(self, settings: BackendSettings) -> None:
		self.settings = settings

	@abstractmethod
	async def login(self, user: User, request: Request, response: Response) -> LoginResult: ...

	@abstractmethod
	async def authenticate(self, request: Request) -> AuthContext | None: ...

	@abstractmethod
	async def logout(self, request: Request, response: Response) -> None: ...

	@abstractmethod
	async def refresh(self, request: Request, response: Response) -> LoginResult: ...


class _PendingAuthStrategy(AuthStrategy):
	async def login(self, user: User, request: Request, response: Response) -> LoginResult:
		raise NotImplementedError("認証方式の実装は対応するphaseで提供します")

	async def authenticate(self, request: Request) -> AuthContext | None:
		return None

	async def logout(self, request: Request, response: Response) -> None:
		return None

	async def refresh(self, request: Request, response: Response) -> LoginResult:
		raise NotImplementedError("認証方式の実装は対応するphaseで提供します")


class SessionAuthStrategy(_PendingAuthStrategy):
	mode: Literal["session"] = "session"


class JwtAuthStrategy(_PendingAuthStrategy):
	mode: Literal["jwt"] = "jwt"


def _build_auth_strategy(settings: BackendSettings) -> AuthStrategy:
	if settings.auth_mode == "session":
		return SessionAuthStrategy(settings)
	if settings.auth_mode == "jwt":
		return JwtAuthStrategy(settings)
	raise ValueError(f"unsupported auth mode: {settings.auth_mode}")


_strategies: dict[AuthMode, AuthStrategy] = {}


def get_auth_strategy(settings: BackendSettings | None = None) -> AuthStrategy:
	current_settings = settings or get_backend_settings()
	if current_settings.auth_mode not in _strategies:
		_strategies[current_settings.auth_mode] = _build_auth_strategy(current_settings)
	return _strategies[current_settings.auth_mode]
