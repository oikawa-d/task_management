import secrets
from datetime import UTC, datetime
from typing import Literal, TypedDict
from uuid import UUID, uuid4

from fastapi import Request, Response

from app.auth.base import AuthContext, AuthStrategy, LoginResult
from app.core import security
from app.core.exceptions import TokenInvalidError, TokenRevokedError
from app.models.user import User
from app.repository import redis_store
from app.repository.redis_store_common import RefreshData, TokenReused


class CookieOptions(TypedDict, total=False):
	secure: bool
	httponly: bool
	samesite: Literal["lax", "strict", "none"]
	path: str
	domain: str


class JwtAuthStrategy(AuthStrategy):
	mode: Literal["jwt"] = "jwt"

	def _cookie_options(
		self,
		*,
		httponly: bool,
		samesite: Literal["lax", "strict", "none"],
		path: str,
	) -> CookieOptions:
		options: CookieOptions = {
			"secure": self.settings.cookie_secure,
			"httponly": httponly,
			"samesite": samesite,
			"path": path,
		}
		if self.settings.cookie_domain:
			options["domain"] = self.settings.cookie_domain
		return options

	def _set_cookies(self, response: Response, refresh_token: str, csrf_token: str) -> None:
		response.set_cookie(
			self.settings.cookie_name_refresh,
			refresh_token,
			**self._cookie_options(
				httponly=True,
				samesite=self.settings.cookie_samesite_refresh,
				path="/api/auth",
			),
			max_age=self.settings.refresh_ttl_seconds,
		)
		response.set_cookie(
			self.settings.cookie_name_csrf,
			csrf_token,
			**self._cookie_options(
				httponly=False,
				samesite=self.settings.cookie_samesite,
				path="/",
			),
			max_age=self.settings.refresh_ttl_seconds,
		)

	def _delete_cookies(self, response: Response) -> None:
		for name, httponly, samesite, path in (
			(self.settings.cookie_name_refresh, True, self.settings.cookie_samesite_refresh, "/api/auth"),
			(self.settings.cookie_name_csrf, False, self.settings.cookie_samesite, "/"),
		):
			response.delete_cookie(
				name,
				**self._cookie_options(httponly=httponly, samesite=samesite, path=path),
			)

	async def login(self, user: User, request: Request, response: Response) -> LoginResult:
		family_id = str(uuid4())
		return await self._issue_tokens(user.id, family_id, response)

	async def _issue_tokens(self, user_id: UUID, family_id: str, response: Response) -> LoginResult:
		issued_at = datetime.now(UTC)
		access_token = self._issue_access_token(user_id, issued_at)
		refresh_token = secrets.token_urlsafe(48)
		await redis_store.store_refresh_token(refresh_token, user_id, family_id, self.settings.refresh_ttl_seconds)
		csrf_token = secrets.token_urlsafe(32)
		self._set_cookies(response, refresh_token, csrf_token)
		return LoginResult("jwt", access_token, refresh_token, csrf_token, self.settings.access_token_ttl_seconds)

	def _issue_access_token(self, user_id: UUID, issued_at: datetime) -> str:
		return security.encode_jwt(
			{
				"sub": str(user_id),
				"iat": issued_at,
				"exp": int(issued_at.timestamp()) + self.settings.access_token_ttl_seconds,
				"jti": str(uuid4()),
				"typ": "access",
			},
			self.settings.jwt_secret_key,
			self.settings.jwt_algorithm,
		)

	async def authenticate(self, request: Request) -> AuthContext | None:
		header = request.headers.get("authorization", "")
		if not header.startswith("Bearer "):
			return None
		try:
			claims = security.decode_jwt(header[7:], self.settings.jwt_secret_key, self.settings.jwt_algorithm)
			if claims.get("typ") != "access" or not claims.get("jti"):
				return None
			return AuthContext(user_id=UUID(str(claims["sub"])))
		except ValueError:
			return None
		except security.JwtDecodeError:
			return None

	async def refresh(self, request: Request, response: Response) -> LoginResult:
		old_token = request.cookies.get(self.settings.cookie_name_refresh)
		if not old_token:
			raise TokenInvalidError()
		new_token = secrets.token_urlsafe(48)
		result = await redis_store.rotate_refresh_token(old_token, new_token, self.settings.refresh_ttl_seconds)
		if isinstance(result, TokenReused):
			await redis_store.revoke_token_family(result.user_id, result.family_id, self.settings.refresh_ttl_seconds)
			raise TokenRevokedError()
		if not isinstance(result, RefreshData):
			raise TokenRevokedError()
		csrf_token = secrets.token_urlsafe(32)
		self._set_cookies(response, new_token, csrf_token)
		return LoginResult(
			"jwt",
			self._issue_access_token(result.user_id, datetime.now(UTC)),
			new_token,
			csrf_token,
			self.settings.access_token_ttl_seconds,
		)

	async def logout(self, request: Request, response: Response) -> None:
		refresh_token = request.cookies.get(self.settings.cookie_name_refresh)
		if refresh_token:
			metadata = await redis_store.get_refresh_token(refresh_token)
			if metadata is not None:
				await redis_store.revoke_refresh_token(refresh_token, metadata.user_id)
		self._delete_cookies(response)
