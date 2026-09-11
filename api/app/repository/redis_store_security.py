from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from redis.asyncio import Redis

from app.repository.redis_store_common import identifier_hash, key, rate_limit_key, validate_ttl


async def mark_email_verify_sent(client: Redis, prefix: str, user_id: UUID, interval: int) -> bool:
	validate_ttl(interval, "interval")
	return bool(
		await client.set(
			key("emailverify_sent", prefix, user_id), str(datetime.now(UTC).timestamp()), nx=True, ex=interval
		)
	)


async def get_login_failure_count(client: Redis, prefix: str, identifier: str, client_ip: str) -> int:
	value = await client.get(key("login_fail", prefix, identifier_hash(identifier, client_ip)))
	return int(value) if value is not None else 0


async def get_login_failure_ttl(client: Redis, prefix: str, identifier: str, client_ip: str) -> int:
	return cast(int, await client.ttl(key("login_fail", prefix, identifier_hash(identifier, client_ip))))


async def incr_login_failure(client: Redis, prefix: str, identifier: str, client_ip: str, window: int) -> int:
	validate_ttl(window, "window")
	login_key = key("login_fail", prefix, identifier_hash(identifier, client_ip))
	count = int(await client.incr(login_key))
	if count == 1:
		await client.expire(login_key, window)
	return count


async def reset_login_failure(client: Redis, prefix: str, identifier: str, client_ip: str) -> None:
	await client.delete(key("login_fail", prefix, identifier_hash(identifier, client_ip)))


async def check_rate_limit(client: Redis, prefix: str, scope: str, value: str, max_requests: int, window: int) -> int:
	if max_requests <= 0:
		raise ValueError("max_requests must be positive")
	validate_ttl(window, "window")
	rate_key = rate_limit_key(scope, value, prefix)
	count = int(await client.incr(rate_key))
	if count == 1:
		await client.expire(rate_key, window)
	return count


async def get_rate_limit_ttl(client: Redis, prefix: str, scope: str, value: str) -> int:
	milliseconds = int(await client.pttl(rate_limit_key(scope, value, prefix)))
	if milliseconds <= 0:
		return 1
	return max(1, (milliseconds + 999) // 1000)
