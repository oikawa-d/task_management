from dataclasses import dataclass
from datetime import timedelta
from typing import Literal, Protocol, TypedDict
from uuid import UUID

from fastapi import Response
from starlette.requests import Request

from app.core.config import BackendSettings
from app.repository.session_repository import SessionRepository


class SessionUser(Protocol):
	id: UUID


class CookieOptions(TypedDict, total=False):
	secure: bool
	httponly: bool
	samesite: Literal["lax", "strict", "none"]
	path: str
	domain: str


@dataclass(frozen=True)
class SessionAuthContext:
	user_id: UUID
	session_id: str


@dataclass(frozen=True)
class SessionLoginResult:
	auth_mode: Literal["session"]
	session_id: str
	csrf_token: str
	expires_in: int


class SessionAuthService:
	def __init__(self, repository: SessionRepository, settings: BackendSettings) -> None:
		self._repository = repository
		self._settings = settings

	@staticmethod
	def _user_id(user: UUID | SessionUser) -> UUID:
		return user if isinstance(user, UUID) else user.id

	def _cookie_options(self, httponly: bool) -> CookieOptions:
		options: CookieOptions = {
			"secure": self._settings.cookie_secure,
			"httponly": httponly,
			"samesite": self._settings.cookie_samesite,
			"path": "/",
		}
		if self._settings.cookie_domain:
			options["domain"] = self._settings.cookie_domain
		return options

	def _set_cookies(self, response: Response, session_id: str, csrf_token: str) -> None:
		response.set_cookie(
			self._settings.cookie_name_session,
			session_id,
			**self._cookie_options(httponly=True),
		)
		response.set_cookie(
			self._settings.cookie_name_csrf,
			csrf_token,
			**self._cookie_options(httponly=False),
		)

	def _delete_cookies(self, response: Response) -> None:
		response.delete_cookie(
			self._settings.cookie_name_session,
			**self._cookie_options(httponly=True),
		)
		response.delete_cookie(
			self._settings.cookie_name_csrf,
			**self._cookie_options(httponly=False),
		)

	async def login(
		self,
		user: UUID | SessionUser,
		request: Request | Response | None = None,
		response: Response | None = None,
	) -> SessionLoginResult:
		if isinstance(request, Response) and response is None:
			response = request
			request = None
		if response is None:
			raise ValueError("response is required")
		request_obj = request if isinstance(request, Request) else None
		ip = request_obj.client.host if request_obj is not None and request_obj.client is not None else None
		session_id, csrf_token = await self._repository.create_session(
			self._user_id(user), ip, self._settings.session_ttl_seconds
		)
		self._set_cookies(response, session_id, csrf_token)
		return SessionLoginResult("session", session_id, csrf_token, self._settings.session_ttl_seconds)

	async def authenticate(self, request: Request) -> SessionAuthContext | None:
		session_id = request.cookies.get(self._settings.cookie_name_session)
		if not session_id:
			return None
		session = await self._repository.get_session(session_id)
		if session is None:
			return None
		absolute_expires_at = session.created_at + timedelta(seconds=self._settings.session_absolute_ttl_seconds)
		if not await self._repository.touch_session(
			session_id,
			session.user_id,
			self._settings.session_ttl_seconds,
			absolute_expires_at,
		):
			return None
		return SessionAuthContext(session.user_id, session_id)

	def has_session_cookie(self, request: Request) -> bool:
		return bool(request.cookies.get(self._settings.cookie_name_session))

	async def logout(self, request: Request, response: Response) -> None:
		session_id = request.cookies.get(self._settings.cookie_name_session)
		if session_id:
			session = await self._repository.get_session(session_id)
			if session is not None:
				await self._repository.delete_session(session_id, session.user_id)
			self._delete_cookies(response)
