"""認証・通知で共有するRedisキー操作の公開API。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from redis.asyncio import Redis

from app.core.config import get_backend_settings
from app.redis_client import get_redis_client
from app.repository import redis_store_auth, redis_store_security, redis_store_session
from app.repository.redis_store_common import OAuthHandoffData, OAuthStateData, RefreshData, SessionData, TokenReused

__all__ = [
	"OAuthHandoffData",
	"OAuthStateData",
	"RefreshData",
	"SessionData",
	"TokenReused",
	"check_rate_limit",
	"consume_email_verify_token",
	"consume_oauth_handoff",
	"consume_oauth_state",
	"consume_password_reset_token",
	"create_session",
	"delete_all_sessions",
	"delete_session",
	"get_csrf_token",
	"get_login_failure_count",
	"get_login_failure_ttl",
	"get_rate_limit_ttl",
	"get_refresh_token",
	"get_session",
	"get_rate_limit_ttl",
	"incr_login_failure",
	"mark_email_verify_sent",
	"ping",
	"replace_email_verify_token",
	"reset_login_failure",
	"revoke_all_refresh_tokens",
	"revoke_refresh_token",
	"revoke_token_family",
	"rotate_refresh_token",
	"save_oauth_handoff",
	"save_oauth_state",
	"save_password_reset_token",
	"store_refresh_token",
	"touch_session",
]


def _redis() -> Redis:
	return get_redis_client()


def _key_prefix() -> str:
	return get_backend_settings().redis_key_prefix


async def create_session(user_id: UUID, ip: str | None, ttl: int) -> tuple[str, str]:
	return await redis_store_session.create_session(_redis(), _key_prefix(), user_id, ip, ttl)


async def get_session(session_id: str) -> SessionData | None:
	return await redis_store_session.get_session(_redis(), _key_prefix(), session_id)


async def touch_session(session_id: str, user_id: UUID, ttl: int, absolute_expires_at: datetime) -> bool:
	return await redis_store_session.touch_session(
		_redis(), _key_prefix(), session_id, user_id, ttl, absolute_expires_at
	)


async def get_csrf_token(session_id: str) -> str | None:
	return await redis_store_session.get_csrf_token(_redis(), _key_prefix(), session_id)


async def delete_session(session_id: str, user_id: UUID) -> None:
	await redis_store_session.delete_session(_redis(), _key_prefix(), session_id, user_id)


async def delete_all_sessions(user_id: UUID) -> int:
	return await redis_store_session.delete_all_sessions(_redis(), _key_prefix(), user_id)


async def store_refresh_token(token: str, user_id: UUID, family_id: str, ttl: int) -> None:
	await redis_store_auth.store_refresh_token(_redis(), _key_prefix(), token, user_id, family_id, ttl)


async def get_refresh_token(token: str) -> RefreshData | None:
	return await redis_store_auth.get_refresh_token(_redis(), _key_prefix(), token)


async def rotate_refresh_token(token: str, new_token: str, ttl: int) -> RefreshData | TokenReused | None:
	return await redis_store_auth.rotate_refresh_token(_redis(), _key_prefix(), token, new_token, ttl)


async def revoke_refresh_token(token: str, user_id: UUID) -> None:
	await redis_store_auth.revoke_refresh_token(_redis(), _key_prefix(), token, user_id)


async def revoke_token_family(user_id: UUID, family_id: str, ttl: int | None = None) -> int:
	return await redis_store_auth.revoke_token_family(_redis(), _key_prefix(), user_id, family_id, ttl)


async def revoke_all_refresh_tokens(user_id: UUID) -> int:
	return await redis_store_auth.revoke_all_refresh_tokens(_redis(), _key_prefix(), user_id)


async def save_oauth_state(state: str, redirect_to: str, code_verifier: str, nonce: str, ttl: int) -> None:
	await redis_store_auth.save_oauth_state(_redis(), _key_prefix(), state, redirect_to, code_verifier, nonce, ttl)


async def consume_oauth_state(state: str) -> OAuthStateData | None:
	return await redis_store_auth.consume_oauth_state(_redis(), _key_prefix(), state)


async def save_oauth_handoff(code: str, user_id: UUID, redirect_to: str, ttl: int) -> None:
	await redis_store_auth.save_oauth_handoff(_redis(), _key_prefix(), code, user_id, redirect_to, ttl)


async def consume_oauth_handoff(code: str) -> OAuthHandoffData | None:
	return await redis_store_auth.consume_oauth_handoff(_redis(), _key_prefix(), code)


async def save_password_reset_token(token: str, user_id: UUID, ttl: int) -> None:
	await redis_store_auth.save_password_reset_token(_redis(), _key_prefix(), token, user_id, ttl)


async def consume_password_reset_token(token: str) -> UUID | None:
	return await redis_store_auth.consume_password_reset_token(_redis(), _key_prefix(), token)


async def replace_email_verify_token(token: str, user_id: UUID, ttl: int) -> None:
	await redis_store_auth.replace_email_verify_token(_redis(), _key_prefix(), token, user_id, ttl)


async def consume_email_verify_token(token: str) -> UUID | None:
	return await redis_store_auth.consume_email_verify_token(_redis(), _key_prefix(), token)


async def mark_email_verify_sent(user_id: UUID, interval: int) -> bool:
	return await redis_store_security.mark_email_verify_sent(_redis(), _key_prefix(), user_id, interval)


async def get_login_failure_count(identifier: str, client_ip: str) -> int:
	return await redis_store_security.get_login_failure_count(_redis(), _key_prefix(), identifier, client_ip)


async def get_login_failure_ttl(identifier: str, client_ip: str) -> int:
	return await redis_store_security.get_login_failure_ttl(_redis(), _key_prefix(), identifier, client_ip)


async def incr_login_failure(identifier: str, client_ip: str, window: int) -> int:
	return await redis_store_security.incr_login_failure(_redis(), _key_prefix(), identifier, client_ip, window)


async def reset_login_failure(identifier: str, client_ip: str) -> None:
	await redis_store_security.reset_login_failure(_redis(), _key_prefix(), identifier, client_ip)


async def check_rate_limit(scope: str, value: str, max_requests: int, window: int) -> int:
	return await redis_store_security.check_rate_limit(_redis(), _key_prefix(), scope, value, max_requests, window)


async def get_rate_limit_ttl(scope: str, value: str) -> int:
	return await redis_store_security.get_rate_limit_ttl(_redis(), _key_prefix(), scope, value)


async def ping() -> bool:
	return bool(await _redis().ping())
