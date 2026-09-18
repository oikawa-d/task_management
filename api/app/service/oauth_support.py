"""OAuthサービスが共有するCookie・レート制限・認証方式補助。"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlsplit

from fastapi import Request, Response
from sqlalchemy.exc import DBAPIError

from app.core.client_ip import ClientIpInfo, resolve_client_ip
from app.core.config import BackendSettings, get_backend_settings
from app.core.exceptions import ServiceUnavailableError, TooManyAttemptsError, raise_database_error
from app.models.user import User
from app.repository import login_history_repository, redis_store
from app.service.auth_logging import log_auth_state_revoke_failed, log_login_history_write_failed, request_id

logger = logging.getLogger("app.oauth")
OAUTH_RATE_LIMIT_SCOPE = {"start": "oauth_start", "callback": "oauth_callback", "exchange": "oauth_exchange"}


def normalize_redirect_to(raw: str | None, settings: BackendSettings | None = None) -> str:
	"""OAuthログイン後のリダイレクト先を検証し、安全なパスへ正規化する。

	オープンリダイレクト対策として、サイト内の絶対パス（`/`始まり）以外、
	プロトコル相対URL（`//`始まり）、スキーム・ホストを含むURL、
	長さ超過、バックスラッシュ、制御文字を含むものはすべて既定のリダイレクト先へ
	差し替える。

	Args:
		raw: クライアントから指定されたリダイレクト先（未検証）。
		settings: 使用する設定。省略時はプロセス共通設定を取得する。

	Returns:
		str: 検証済みの安全なリダイレクト先パス。不正な場合は既定のリダイレクト先。
	"""
	config = settings or get_backend_settings()
	if not raw:
		return config.oauth_default_redirect_to
	parsed = urlsplit(raw)
	if (
		not raw.startswith("/")
		or raw.startswith("//")
		or parsed.scheme
		or parsed.netloc
		or len(raw) > config.oauth_redirect_to_max_length
		or "\\" in raw
		or any(ord(char) < 0x20 or ord(char) == 0x7F for char in raw)
	):
		return config.oauth_default_redirect_to
	return raw


def set_oauth_state_cookie(response: Response, state: str, settings: BackendSettings) -> None:
	"""OAuth CSRF対策用のstate値をHttpOnly Cookieとして設定する。

	Cookieのスコープは`/api/auth/oauth`配下に限定する。

	Args:
		response: Cookieを設定するレスポンス。
		state: 発行したOAuth state値。
		settings: Cookie属性（secure/samesite/domain/TTL）を含むバックエンド設定。

	Returns:
		None
	"""
	options: dict[str, Any] = {
		"httponly": True,
		"secure": settings.cookie_secure,
		"samesite": settings.cookie_samesite,
		"path": "/api/auth/oauth",
		"max_age": settings.oauth_state_ttl_seconds,
	}
	if settings.cookie_domain:
		options["domain"] = settings.cookie_domain
	response.set_cookie(settings.cookie_name_oauth_state, state, **options)


def delete_oauth_state_cookie(response: Response, settings: BackendSettings) -> None:
	"""OAuth state用Cookieを削除する。

	Args:
		response: Cookieを削除するレスポンス。
		settings: Cookie属性（secure/samesite/domain）を含むバックエンド設定。

	Returns:
		None
	"""
	options: dict[str, Any] = {
		"secure": settings.cookie_secure,
		"httponly": True,
		"samesite": settings.cookie_samesite,
		"path": "/api/auth/oauth",
	}
	if settings.cookie_domain:
		options["domain"] = settings.cookie_domain
	response.delete_cookie(settings.cookie_name_oauth_state, **options)


def is_valid_jwt_login_result(login_result: Any) -> bool:
	"""JWT認証モードのログイン結果が、トークン交換に必要な全項目を備えているか検証する。

	Args:
		login_result: 認証戦略が返したログイン結果。

	Returns:
		bool: `auth_mode="jwt"`かつアクセストークン・リフレッシュトークン・
			CSRFトークンが空でない文字列で、`expires_in`が1以上の整数（bool除く）の場合`True`。
	"""
	if getattr(login_result, "auth_mode", None) != "jwt":
		return False
	for field in ("access_token", "refresh_token", "csrf_token"):
		value = getattr(login_result, field, None)
		if not isinstance(value, str) or not value:
			return False
	expires_in = getattr(login_result, "expires_in", None)
	return isinstance(expires_in, int) and not isinstance(expires_in, bool) and expires_in >= 1


async def check_oauth_rate_limit(request: Request, scope: str, route: str, settings: BackendSettings) -> ClientIpInfo:
	"""OAuthエンドポイントへのリクエストをIP単位でレート制限する。

	上限超過はRedis上のカウンタで検知し、警告ログを出力したうえで
	残りロック時間を`Retry-After`として`TooManyAttemptsError`を送出する。

	Args:
		request: クライアントIP解決対象の現在のリクエスト。
		scope: レート制限のスコープ（`OAUTH_RATE_LIMIT_SCOPE`の値）。
		route: ログ記録用のルート識別子。
		settings: レート制限の上限・時間窓を含むバックエンド設定。

	Returns:
		ClientIpInfo: 解決済みのクライアントIP情報。

	Raises:
		TooManyAttemptsError: レート制限の上限を超過した場合（429 TOO_MANY_ATTEMPTS）。
		ServiceUnavailableError: Redisへのアクセスに失敗した場合（503）。
	"""
	client_info = resolve_client_ip(request, settings.trusted_proxy_cidrs)
	try:
		count = await redis_store.check_rate_limit(
			scope,
			client_info.client_ip,
			settings.rate_limit_oauth_max_requests,
			settings.rate_limit_oauth_window_seconds,
		)
	except Exception as exc:
		raise ServiceUnavailableError() from exc
	if count > settings.rate_limit_oauth_max_requests:
		logger.warning(
			"OAuth rate limit rejected",
			extra={
				"operation": "rate_limit",
				"event": "rate_limit_rejected",
				"route": route,
				"scope": scope,
				"limit": settings.rate_limit_oauth_max_requests,
				"window": settings.rate_limit_oauth_window_seconds,
				"client_ip": client_info.client_ip,
				"proxy_peer_ip": client_info.proxy_peer_ip,
				"ip_source": client_info.ip_source,
				"request_id": request_id(request),
			},
		)
		try:
			ttl = await redis_store.get_rate_limit_ttl(scope, client_info.client_ip)
		except Exception as exc:
			raise ServiceUnavailableError() from exc
		raise TooManyAttemptsError(retry_after=ttl if ttl > 0 else settings.rate_limit_oauth_window_seconds)
	return client_info


async def record_oauth_login(db: Any, user: User, request: Request, client_info: ClientIpInfo | None = None) -> None:
	"""Googleログイン成功をログイン履歴テーブルへ記録する。

	記録とコミットが本関数のトランザクション境界である。

	Args:
		db: 履歴登録に使用する非同期DBセッション。
		user: ログインしたユーザー。
		request: User-Agent取得・IP解決に使用する現在のリクエスト。
		client_info: 解決済みのクライアントIP情報。未指定の場合はここで解決する。

	Returns:
		None

	Raises:
		app.core.exceptions.AppError: DB登録でSQLSTATEエラーが発生した場合、
			`raise_database_error`により業務例外へ変換されて送出される。
	"""
	resolved_ip = client_info or resolve_client_ip(request, get_backend_settings().trusted_proxy_cidrs)
	try:
		await login_history_repository.create(
			db,
			user_id=user.id,
			login_identifier=user.email,
			login_method="oauth_google",
			ip_address=resolved_ip.client_ip,
			user_agent=request.headers.get("user-agent"),
			success=True,
			failure_reason=None,
		)
		await db.commit()
	except DBAPIError as exc:
		await db.rollback()
		raise_database_error(exc)


async def rollback_oauth_login(
	strategy: Any,
	user: User,
	login_result: Any,
	response: Response,
	settings: BackendSettings,
	*,
	clear_state_cookie: bool,
	request: Request,
	client_info: ClientIpInfo,
	operation: str,
) -> None:
	"""OAuthログイン後の後続処理失敗を受けて、発行済みセッション/トークンを取り消す。

	ここでのrollbackは認証状態（セッション・リフレッシュトークン）の補償処理であり、
	DBトランザクションのロールバックとは別責務である。取り消し自体に失敗した場合は
	監査ログへ記録したうえで例外を再送出する。

	Args:
		strategy: `rollback_login`を提供する認証戦略。
		user: ログイン取り消し対象のユーザー。
		login_result: 取り消し対象のログイン結果（発行済みトークン等）。
		response: Cookie削除等に使用するレスポンス。
		settings: state Cookie削除に使用するバックエンド設定。
		clear_state_cookie: OAuth state Cookieも合わせて削除するかどうか。
		request: 監査ログに使用する現在のリクエスト。
		client_info: クライアントIP等の接続元情報。
		operation: 監査ログに記録する操作種別。

	Returns:
		None

	Raises:
		RuntimeError: 認証戦略がログイン取り消しをサポートしない場合。
		Exception: `strategy.rollback_login`が送出した例外をそのまま再送出する。
	"""
	login_user_id = str(user.id)
	try:
		rollback = getattr(strategy, "rollback_login", None)
		if rollback is None:
			raise RuntimeError("auth strategy does not support login rollback")
		await rollback(user, login_result, response)
	except Exception:
		log_auth_state_revoke_failed(request, user, operation, client_info, user_id=login_user_id)
		raise
	finally:
		if clear_state_cookie:
			delete_oauth_state_cookie(response, settings)


async def complete_oauth_session_login(
	db: Any,
	user: User,
	request: Request,
	response: Response,
	settings: BackendSettings,
	client_info: ClientIpInfo,
	strategy: Any,
	login_result: Any,
	record_login: Any,
) -> None:
	"""セッション認証モードでのOAuthログイン完了処理（履歴記録・state Cookie削除）を行う。

	ログイン履歴の記録に失敗した場合は、発行済みセッションを`rollback_oauth_login`で
	取り消したうえで`ServiceUnavailableError`とする。取り消し自体にも失敗した場合は
	その例外を起点として`ServiceUnavailableError`を送出する。

	Args:
		db: 履歴登録に使用する非同期DBセッション。
		user: ログインしたユーザー。
		request: 監査ログ・IP解決に使用する現在のリクエスト。
		response: Cookie操作に使用するレスポンス。
		settings: Cookie属性を含むバックエンド設定。
		client_info: クライアントIP等の接続元情報。
		strategy: `rollback_login`を提供する認証戦略。
		login_result: 取り消し対象のログイン結果（発行済みセッション等）。
		record_login: ログイン履歴を記録する関数（呼び出し規約は`record_oauth_login`と同一）。

	Returns:
		None

	Raises:
		ServiceUnavailableError: ログイン履歴の記録に失敗した場合。
	"""
	login_user_id = str(user.id)
	try:
		await record_login(db, user, request, client_info)
	except Exception as exc:
		log_login_history_write_failed(request, user, client_info, user_id=login_user_id)
		try:
			await rollback_oauth_login(
				strategy,
				user,
				login_result,
				response,
				settings,
				clear_state_cookie=True,
				request=request,
				client_info=client_info,
				operation="oauth_callback_session",
			)
		except Exception as rollback_exc:
			raise ServiceUnavailableError() from rollback_exc
		raise ServiceUnavailableError() from exc
	delete_oauth_state_cookie(response, settings)
