"""認証サービス共通の監査ログ。"""

from __future__ import annotations

import hashlib
import logging

from fastapi import Request

from app.core.client_ip import ClientIpInfo
from app.models.user import User

logger = logging.getLogger("app.oauth")
SERVICE_UNAVAILABLE_FAILURE_REASON = "service_unavailable"


def request_id(request: Request) -> str | None:
	"""リクエストに紐づくrequest_idを`request.state`から取り出す。

	`request.state.request_id`が未設定、または文字列以外の場合は`None`を返す。

	Args:
		request: 現在処理中のリクエスト。

	Returns:
		str | None: リクエストID。取得できない場合は`None`。
	"""
	request_state = getattr(request, "state", None)
	value = getattr(request_state, "request_id", None)
	return value if isinstance(value, str) else None


def log_login_attempt(
	request: Request,
	user: User | None,
	client_info: ClientIpInfo,
	identifier: str,
	auth_mode: str,
	success: bool,
	failure_reason: str | None,
) -> None:
	"""ログイン試行の監査ログを出力する。

	識別子（メールアドレス等）は平文をログへ残さないようSHA-256でハッシュ化する。

	Args:
		request: 現在処理中のリクエスト。
		user: ログイン試行対象として特定できたユーザー。未特定の場合は`None`。
		client_info: クライアントIP等の接続元情報。
		identifier: ログインに使用された識別子（メールアドレス等、平文）。
		auth_mode: 認証方式（`session`/`jwt`）。
		success: ログインが成功したかどうか。
		failure_reason: 失敗理由（成功時は`None`）。

	Returns:
		None
	"""
	logger.info(
		"Login attempt",
		extra={
			"operation": "login",
			"event": "login_attempt",
			"identifier": hashlib.sha256(identifier.strip().lower().encode()).hexdigest(),
			"user_id": str(user.id) if user is not None else None,
			"success": success,
			"auth_mode": auth_mode,
			"failure_reason": failure_reason,
			"client_ip": client_info.client_ip,
			"proxy_peer_ip": client_info.proxy_peer_ip,
			"ip_source": client_info.ip_source,
			"request_id": request_id(request),
		},
	)


def log_user_registered(request: Request, user: User) -> None:
	"""ユーザー登録完了の監査ログを出力する。

	Args:
		request: 現在処理中のリクエスト。
		user: 登録されたユーザー。

	Returns:
		None
	"""
	logger.info(
		"User registered",
		extra={
			"operation": "register",
			"event": "user_registered",
			"user_id": str(user.id),
			"request_id": request_id(request),
		},
	)


def log_login_history_write_failed(
	request: Request,
	user: User | None,
	client_info: ClientIpInfo,
	*,
	user_id: str | None = None,
	operation: str = "oauth_login",
	login_method: str = "oauth_google",
	failure_reason: str = SERVICE_UNAVAILABLE_FAILURE_REASON,
) -> None:
	"""ログイン履歴のDB書き込み失敗を監査ログへ記録する。

	ログイン履歴の書き込み失敗はログイン自体の成否には影響させない設計であり、
	本関数は失敗を運用者が検知できるようにするための記録のみを行う。

	Args:
		request: 現在処理中のリクエスト。
		user: ログインしたユーザー。未特定の場合は`None`（`user_id`引数優先）。
		client_info: クライアントIP等の接続元情報。
		user_id: 記録するユーザーID文字列。指定時は`user`より優先される。
		operation: 発生元の操作種別（例: `oauth_login`）。
		login_method: ログイン方式（例: `oauth_google`）。
		failure_reason: 失敗理由（既定はサービス利用不可）。

	Returns:
		None
	"""
	logger.warning(
		"Login history write failed",
		extra={
			"operation": operation,
			"event": "login_history_write_failed",
			"user_id": user_id if user_id is not None else (str(user.id) if user is not None else None),
			"login_method": login_method,
			"failure_reason": failure_reason,
			"client_ip": client_info.client_ip,
			"proxy_peer_ip": client_info.proxy_peer_ip,
			"ip_source": client_info.ip_source,
			"request_id": request_id(request),
		},
	)


def log_auth_state_revoke_failed(
	request: Request,
	user: User,
	operation: str,
	client_info: ClientIpInfo,
	*,
	user_id: str | None = None,
) -> None:
	"""認証状態（セッション・リフレッシュトークン）の失効操作の失敗を監査ログへ記録する。

	Args:
		request: 現在処理中のリクエスト。
		user: 対象ユーザー。
		operation: 発生元の操作種別。
		client_info: クライアントIP等の接続元情報。
		user_id: 記録するユーザーID文字列。指定時は`user.id`より優先される。

	Returns:
		None
	"""
	logger.error(
		"Authentication state revoke failed",
		extra={
			"operation": operation,
			"event": "auth_state_revoke_failed",
			"user_id": user_id if user_id is not None else str(user.id),
			"deleted_session_count": None,
			"deleted_refresh_count": None,
			"client_ip": client_info.client_ip,
			"proxy_peer_ip": client_info.proxy_peer_ip,
			"ip_source": client_info.ip_source,
			"request_id": request_id(request),
		},
	)
