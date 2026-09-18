"""jwtモードのAuthStrategy実装。

access tokenはstateless（署名検証のみ、jti以外にサーバ側の失効機構を持たない）で
Authorizationヘッダに載せてJSON応答として返す。refresh tokenとcsrf tokenはCookieで管理し、
refresh tokenはRedisにfamily_id単位で保持してローテーション・再利用検知（token family revocation）を行う。
"""

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
	"""`Response.set_cookie`へ渡すCookie属性（`secure`/`httponly`/`samesite`/`path`/`domain`）。"""

	secure: bool
	httponly: bool
	samesite: Literal["lax", "strict", "none"]
	path: str
	domain: str


class JwtAuthStrategy(AuthStrategy):
	"""access token（stateless JWT）とrefresh token（Redis管理）によるjwtモード認証。"""

	mode: Literal["jwt"] = "jwt"

	def _cookie_options(
		self,
		*,
		httponly: bool,
		samesite: Literal["lax", "strict", "none"],
		path: str,
	) -> CookieOptions:
		"""設定値（`cookie_secure`/`cookie_domain`）と引数からCookie属性一式を組み立てる。

		Args:
			httponly: JavaScriptからの参照を禁止するか。
			samesite: クロスサイトリクエストでの送信可否（`lax`/`strict`/`none`）。
			path: Cookieを送信する対象パス。

		Returns:
			`Response.set_cookie`にそのまま渡せるCookie属性の辞書。
		"""
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
		"""refresh token（httponly、パス`/api/auth`限定）とcsrf token（非httponly、全パス）をCookieに設定する。

		どちらも有効期限は`refresh_ttl_seconds`とする。refresh tokenのパスを`/api/auth`に
		限定することで、他エンドポイントへの不要な送出を防ぐ。

		Args:
			response: Set-Cookie設定先のレスポンス。
			refresh_token: 発行済みのrefresh token値。
			csrf_token: 発行済みのCSRFトークン値。
		"""
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
		"""refresh tokenとcsrf tokenのCookieを、設定時と同じ属性・パスで削除する。

		Args:
			response: Cookie削除を反映するレスポンス。
		"""
		for name, httponly, samesite, path in (
			(self.settings.cookie_name_refresh, True, self.settings.cookie_samesite_refresh, "/api/auth"),
			(self.settings.cookie_name_csrf, False, self.settings.cookie_samesite, "/"),
		):
			response.delete_cookie(
				name,
				**self._cookie_options(httponly=httponly, samesite=samesite, path=path),
			)

	async def login(self, user: User, request: Request, response: Response) -> LoginResult:
		"""新しいtoken familyでaccess/refresh/csrf tokenを発行し、Cookieを設定する。

		Args:
			user: ログイン対象ユーザー。
			request: このStrategyでは未使用（インターフェース互換のため保持）。
			response: Set-Cookie設定先のレスポンス。

		Returns:
			発行したaccess token・refresh token等を含む`LoginResult`。
		"""
		family_id = str(uuid4())
		return await self._issue_tokens(user.id, family_id, response)

	async def rollback_login(self, user: User, result: LoginResult, response: Response) -> None:
		"""login後続処理の失敗時にrefresh tokenを失効させ、Cookieを削除する。

		access tokenはstatelessで失効機構が無いためrefresh tokenのみを対象とする。

		Args:
			user: ログイン対象ユーザー（`result.user_id`が無い場合のフォールバック）。
			result: 直前の`login`が返した認証情報。
			response: Cookie削除を反映するレスポンス。
		"""
		try:
			if result.refresh_token is not None:
				await redis_store.revoke_refresh_token(result.refresh_token, result.user_id or user.id)
		finally:
			# Access tokenはstatelessで既存基盤に失効機構がないため、refresh tokenのみ失効する。
			self._delete_cookies(response)

	async def _issue_tokens(self, user_id: UUID, family_id: str, response: Response) -> LoginResult:
		"""access token・refresh token・csrf tokenを発行し、refresh tokenをRedisへ登録する。

		Args:
			user_id: 発行対象ユーザーのID。
			family_id: refresh tokenのローテーション系列を識別するID（再利用検知に用いる）。
			response: Cookie設定先のレスポンス。

		Returns:
			発行したaccess token・refresh token・csrf tokenを含む`LoginResult`。
		"""
		issued_at = datetime.now(UTC)
		access_token = self._issue_access_token(user_id, issued_at)
		refresh_token = secrets.token_urlsafe(48)
		await redis_store.store_refresh_token(refresh_token, user_id, family_id, self.settings.refresh_ttl_seconds)
		csrf_token = secrets.token_urlsafe(32)
		self._set_cookies(response, refresh_token, csrf_token)
		return LoginResult(
			"jwt",
			access_token,
			refresh_token,
			csrf_token,
			self.settings.access_token_ttl_seconds,
			user_id=user_id,
		)

	def _issue_access_token(self, user_id: UUID, issued_at: datetime) -> str:
		"""access_token_ttl_seconds後に失効するstateless JWTを生成する。

		Args:
			user_id: `sub`クレームに設定するユーザーID。
			issued_at: 発行時刻（`iat`・`exp`クレームの基準）。

		Returns:
			署名済みJWT文字列。
		"""
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
		"""`Authorization: Bearer <access token>`ヘッダのJWTを検証する。

		署名・有効期限に加え、`typ`が`access`であること・`jti`が存在することを確認する。
		Cookieは参照しない（jwtモードの通常APIはAuthorizationヘッダのみで認証する）。

		Args:
			request: 検証対象のリクエスト。

		Returns:
			検証に成功した場合は`AuthContext`。ヘッダが無い・形式不正・署名不正・期限切れの
			場合は例外を送出せず`None`を返す（呼び出し側が401 UNAUTHENTICATEDへ変換する）。
		"""
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
		"""refresh tokenをローテーションし、新しいaccess/refresh/csrf tokenを発行する。

		古いrefresh tokenが既に使用済み（再利用）と判定された場合は、盗用の疑いとして
		同じtoken family全体を失効させる。

		Args:
			request: refresh token Cookie読み取りに用いるリクエスト。
			response: 新しいCookie設定先のレスポンス。

		Returns:
			再発行したaccess token等を含む`LoginResult`。

		Raises:
			TokenInvalidError: refresh token Cookieが存在しない場合。
			TokenRevokedError: refresh tokenが再利用検知された、または既に失効済みの場合。
		"""
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
		"""refresh tokenをRedisから失効させ、refresh/csrf tokenのCookieを削除する。

		Cookieが無い場合や対応するメタデータがRedisに無い場合も例外にせず、Cookie削除のみ行う。

		Args:
			request: refresh token Cookie読み取りに用いるリクエスト。
			response: Cookie削除を反映するレスポンス。
		"""
		refresh_token = request.cookies.get(self.settings.cookie_name_refresh)
		if refresh_token:
			metadata = await redis_store.get_refresh_token(refresh_token)
			if metadata is not None:
				await redis_store.revoke_refresh_token(refresh_token, metadata.user_id)
		self._delete_cookies(response)
