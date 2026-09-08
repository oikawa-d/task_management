from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID

from fastapi import Request, Response

from app.core.config import AuthMode, BackendSettings
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
