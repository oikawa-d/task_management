from datetime import timedelta
from typing import Literal, TypedDict

from fastapi import Request, Response

from app.auth.base import AuthContext, AuthStrategy, LoginResult
from app.core.exceptions import NotSupportedInModeError
from app.models.user import User
from app.repository import redis_store


class CookieOptions(TypedDict, total=False):
	secure: bool
	httponly: bool
	samesite: Literal["lax", "strict", "none"]
	path: str
	domain: str


class SessionAuthStrategy(AuthStrategy):
	mode: Literal["session"] = "session"

	def _cookie_options(self, httponly: bool) -> CookieOptions:
		options: CookieOptions = {
			"secure": self.settings.cookie_secure,
			"httponly": httponly,
			"samesite": self.settings.cookie_samesite,
			"path": "/",
		}
		if self.settings.cookie_domain:
			options["domain"] = self.settings.cookie_domain
		return options

	def _set_cookies(self, response: Response, session_id: str, csrf_token: str) -> None:
		response.set_cookie(
			self.settings.cookie_name_session,
			session_id,
			**self._cookie_options(httponly=True),
		)
		response.set_cookie(
			self.settings.cookie_name_csrf,
			csrf_token,
			**self._cookie_options(httponly=False),
		)

	def _delete_cookies(self, response: Response) -> None:
		for name in (self.settings.cookie_name_session, self.settings.cookie_name_csrf):
			response.delete_cookie(
				name,
				**self._cookie_options(httponly=name == self.settings.cookie_name_session),
			)

	async def login(self, user: User, request: Request, response: Response) -> LoginResult:
		ip = request.client.host if request.client is not None else None
		session_id, csrf_token = await redis_store.create_session(user.id, ip, self.settings.session_ttl_seconds)
		self._set_cookies(response, session_id, csrf_token)
		return LoginResult(
			"session",
			csrf_token=csrf_token,
			expires_in=self.settings.session_ttl_seconds,
			session_id=session_id,
		)

	async def rollback_login(self, user: User, result: LoginResult, response: Response) -> None:
		try:
			if result.session_id is not None:
				await redis_store.delete_session(result.session_id, user.id)
		finally:
			self._delete_cookies(response)

	async def authenticate(self, request: Request) -> AuthContext | None:
		session_id = request.cookies.get(self.settings.cookie_name_session)
		if not session_id:
			return None
		session = await redis_store.get_session(session_id)
		if session is None:
			return None
		absolute_expires_at = session.created_at + timedelta(seconds=self.settings.session_absolute_ttl_seconds)
		if not await redis_store.touch_session(
			session_id, session.user_id, self.settings.session_ttl_seconds, absolute_expires_at
		):
			return None
		return AuthContext(user_id=session.user_id, session_id=session_id)

	async def logout(self, request: Request, response: Response) -> None:
		session_id = request.cookies.get(self.settings.cookie_name_session)
		if not session_id:
			return
		session = await redis_store.get_session(session_id)
		if session is not None:
			await redis_store.delete_session(session_id, session.user_id)
		self._delete_cookies(response)

	async def refresh(self, request: Request, response: Response) -> LoginResult:
		raise NotSupportedInModeError()
