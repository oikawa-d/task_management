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
