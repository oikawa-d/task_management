from __future__ import annotations

import hashlib
from typing import Any, NoReturn

from redis.exceptions import RedisError

from app.core.config import BackendSettings, get_backend_settings
from app.core.exceptions import ServiceUnavailableError, TooManyAttemptsError


def build_login_failure_key(identifier: str, client_ip: str) -> str:
	normalized_identifier = identifier.strip().lower()
	return hashlib.sha256(f"{normalized_identifier}:{client_ip}".encode("utf-8")).hexdigest()


def _redis_key(identifier: str, client_ip: str, settings: BackendSettings) -> str:
	key_hash = build_login_failure_key(identifier, client_ip)
	return f"{settings.redis_key_prefix}login_fail:{key_hash}"


def _settings(settings: BackendSettings | None) -> BackendSettings:
	return settings or get_backend_settings()


def _raise_service_unavailable(error: Exception) -> NoReturn:
	raise ServiceUnavailableError() from error


async def check_login_allowed(
	identifier: str,
	client_ip: str,
	redis_client: Any,
	settings: BackendSettings | None = None,
) -> None:
	resolved_settings = _settings(settings)
	key = _redis_key(identifier, client_ip, resolved_settings)
	try:
		value = await redis_client.get(key)
	except (RedisError, ConnectionError, TimeoutError, OSError) as error:
		_raise_service_unavailable(error)
	if value is not None and int(value) >= resolved_settings.login_max_attempts:
		raise TooManyAttemptsError()


async def record_login_failure(
	identifier: str,
	client_ip: str,
	redis_client: Any,
	settings: BackendSettings | None = None,
) -> int:
	resolved_settings = _settings(settings)
	key = _redis_key(identifier, client_ip, resolved_settings)
	try:
		count = int(await redis_client.incr(key))
		if count == 1:
			await redis_client.expire(key, resolved_settings.login_lock_window_seconds)
		return count
	except (RedisError, ConnectionError, TimeoutError, OSError) as error:
		_raise_service_unavailable(error)


async def reset_login_failure(
	identifier: str,
	client_ip: str,
	redis_client: Any,
	settings: BackendSettings | None = None,
) -> None:
	resolved_settings = _settings(settings)
	key = _redis_key(identifier, client_ip, resolved_settings)
	try:
		await redis_client.delete(key)
	except (RedisError, ConnectionError, TimeoutError, OSError) as error:
		_raise_service_unavailable(error)
