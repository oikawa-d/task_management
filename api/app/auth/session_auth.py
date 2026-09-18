"""sessionモードのAuthStrategy実装。

セッション本体はRedisで管理し、クライアントにはセッションIDとcsrf tokenのみを
Cookieとして渡す（access tokenのようなJSON応答は行わない）。セッションには
スライディング有効期限（`session_ttl_seconds`、アクセス毎に延長）と絶対有効期限
（`session_absolute_ttl_seconds`、作成時刻からの上限）の二重の期限を設ける。
"""

from datetime import timedelta
from typing import Literal, TypedDict

from fastapi import Request, Response

from app.auth.base import AuthContext, AuthStrategy, LoginResult
from app.core.client_ip import resolve_client_ip
from app.core.exceptions import NotSupportedInModeError, SessionExpiredError
from app.models.user import User
from app.repository import redis_store


class CookieOptions(TypedDict, total=False):
	"""`Response.set_cookie`へ渡すCookie属性（`secure`/`httponly`/`samesite`/`path`/`domain`）。"""

	secure: bool
	httponly: bool
	samesite: Literal["lax", "strict", "none"]
	path: str
	domain: str


class SessionAuthStrategy(AuthStrategy):
	"""Redis管理のセッションIDとcsrf tokenをCookieで扱うsessionモード認証。"""

	mode: Literal["session"] = "session"

	def _cookie_options(self, httponly: bool) -> CookieOptions:
		"""設定値（`cookie_secure`/`cookie_samesite`/`cookie_domain`）からCookie属性一式を組み立てる。

		Args:
			httponly: JavaScriptからの参照を禁止するか。

		Returns:
			`Response.set_cookie`にそのまま渡せるCookie属性の辞書（パスは常に`/`）。
		"""
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
		"""セッションID（httponly）とcsrf token（非httponly）を全パス向けにCookie設定する。

		Args:
			response: Set-Cookie設定先のレスポンス。
			session_id: 発行済みセッションID。
			csrf_token: 発行済みのCSRFトークン値。
		"""
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
		"""セッションIDとcsrf tokenのCookieを削除する。

		Args:
			response: Cookie削除を反映するレスポンス。
		"""
		for name in (self.settings.cookie_name_session, self.settings.cookie_name_csrf):
			response.delete_cookie(
				name,
				**self._cookie_options(httponly=name == self.settings.cookie_name_session),
			)

	async def login(self, user: User, request: Request, response: Response) -> LoginResult:
		"""Redisに新しいセッションを作成し、セッションID・csrf tokenをCookieに設定する。

		Args:
			user: ログイン対象ユーザー。
			request: クライアントIP解決に用いるリクエスト（信頼済みプロキシ設定を考慮する）。
			response: Set-Cookie設定先のレスポンス。

		Returns:
			発行したセッションID・csrf token等を含む`LoginResult`。
		"""
		ip = resolve_client_ip(request, self.settings.trusted_proxy_cidrs).client_ip
		session_id, csrf_token = await redis_store.create_session(user.id, ip, self.settings.session_ttl_seconds)
		self._set_cookies(response, session_id, csrf_token)
		return LoginResult(
			"session",
			csrf_token=csrf_token,
			expires_in=self.settings.session_ttl_seconds,
			session_id=session_id,
			user_id=user.id,
		)

	async def rollback_login(self, user: User, result: LoginResult, response: Response) -> None:
		"""login後続処理の失敗時にセッションを削除し、Cookieを削除する。

		Args:
			user: ログイン対象ユーザー（`result.user_id`が無い場合のフォールバック）。
			result: 直前の`login`が返した認証情報。
			response: Cookie削除を反映するレスポンス。
		"""
		try:
			if result.session_id is not None:
				await redis_store.delete_session(result.session_id, result.user_id or user.id)
		finally:
			self._delete_cookies(response)

	async def authenticate(self, request: Request) -> AuthContext | None:
		"""セッションID Cookieを検証し、有効ならスライディング有効期限を延長する。

		Args:
			request: セッションID Cookie読み取りに用いるリクエスト。

		Returns:
			検証に成功した場合は`AuthContext`。Cookieが無い場合は`None`。

		Raises:
			SessionExpiredError: セッションがRedisに存在しない、または絶対有効期限を
				超過して延長できない場合（呼び出し側が401 SESSION_EXPIREDへ変換する）。
		"""
		session_id = request.cookies.get(self.settings.cookie_name_session)
		if not session_id:
			return None
		session = await redis_store.get_session(session_id)
		if session is None:
			raise SessionExpiredError()
		absolute_expires_at = session.created_at + timedelta(seconds=self.settings.session_absolute_ttl_seconds)
		if not await redis_store.touch_session(
			session_id, session.user_id, self.settings.session_ttl_seconds, absolute_expires_at
		):
			raise SessionExpiredError()
		return AuthContext(user_id=session.user_id, session_id=session_id)

	async def logout(self, request: Request, response: Response) -> None:
		"""セッションをRedisから削除し、セッションID・csrf tokenのCookieを削除する。

		Cookieが無い場合や対応するセッションがRedisに無い場合も例外にせず、Cookie削除のみ行う。

		Args:
			request: セッションID Cookie読み取りに用いるリクエスト。
			response: Cookie削除を反映するレスポンス。
		"""
		session_id = request.cookies.get(self.settings.cookie_name_session)
		if not session_id:
			return
		session = await redis_store.get_session(session_id)
		if session is not None:
			await redis_store.delete_session(session_id, session.user_id)
		self._delete_cookies(response)

	async def refresh(self, request: Request, response: Response) -> LoginResult:
		"""sessionモードにはトークン再発行の概念が無いため、常に非対応エラーを送出する。

		Args:
			request: このStrategyでは未使用（インターフェース互換のため保持）。
			response: このStrategyでは未使用（インターフェース互換のため保持）。

		Raises:
			NotSupportedInModeError: 常に送出する（405 NOT_SUPPORTED_IN_MODE）。
		"""
		raise NotSupportedInModeError()
