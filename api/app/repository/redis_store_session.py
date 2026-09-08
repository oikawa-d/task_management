from __future__ import annotations

import math
import secrets
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from redis.asyncio import Redis

from app.repository.redis_store_common import (
	SessionData,
	dump,
	key,
	parse_datetime,
	parse_json,
	validate_ttl,
)


async def create_session(client: Redis, prefix: str, user_id: UUID, ip: str | None, ttl: int) -> tuple[str, str]:
	validate_ttl(ttl)
	session_id = secrets.token_urlsafe(32)
	csrf_token = secrets.token_urlsafe(32)
	created_at = datetime.now(UTC)
	pipe = client.pipeline(transaction=True)
	pipe.setex(
		key("session", prefix, session_id),
		ttl,
		dump({"user_id": user_id, "created_at": created_at.isoformat(), "ip": ip}),
	)
	pipe.setex(key("csrf", prefix, session_id), ttl, dump({"token": csrf_token}))
	pipe.sadd(key("user_sessions", prefix, user_id), session_id)
	pipe.expire(key("user_sessions", prefix, user_id), ttl)
	await pipe.execute()
	return session_id, csrf_token


async def get_session(client: Redis, prefix: str, session_id: str) -> SessionData | None:
	data = parse_json(await client.get(key("session", prefix, session_id)))
	if data is None:
		return None
	return SessionData(
		user_id=UUID(str(data["user_id"])),
		created_at=parse_datetime(data["created_at"]),
		ip=cast(str | None, data.get("ip")),
	)


async def touch_session(
	client: Redis, prefix: str, session_id: str, user_id: UUID, ttl: int, absolute_expires_at: datetime
) -> bool:
	validate_ttl(ttl)
	if await client.get(key("session", prefix, session_id)) is None:
		return False
	remaining = (absolute_expires_at - datetime.now(UTC)).total_seconds()
	if remaining <= 0:
		return False
	effective_ttl = min(ttl, math.ceil(remaining))
	pipe = client.pipeline(transaction=True)
	pipe.expire(key("session", prefix, session_id), effective_ttl)
	pipe.expire(key("csrf", prefix, session_id), effective_ttl)
	pipe.expire(key("user_sessions", prefix, user_id), effective_ttl)
	await pipe.execute()
	return True


async def get_csrf_token(client: Redis, prefix: str, session_id: str) -> str | None:
	data = parse_json(await client.get(key("csrf", prefix, session_id)))
	return cast(str | None, data.get("token")) if data else None


async def delete_session(client: Redis, prefix: str, session_id: str, user_id: UUID) -> None:
	pipe = client.pipeline(transaction=True)
	pipe.delete(key("session", prefix, session_id), key("csrf", prefix, session_id))
	pipe.srem(key("user_sessions", prefix, user_id), session_id)
	await pipe.execute()


async def delete_all_sessions(client: Redis, prefix: str, user_id: UUID) -> int:
	raw_session_ids = await cast(Any, client.smembers)(key("user_sessions", prefix, user_id))
	session_ids = [
		session_id.decode() if isinstance(session_id, bytes) else str(session_id) for session_id in raw_session_ids
	]
	pipe = client.pipeline(transaction=True)
	for session_id in session_ids:
		pipe.delete(key("session", prefix, session_id), key("csrf", prefix, session_id))
	pipe.delete(key("user_sessions", prefix, user_id))
	await pipe.execute()
	return len(session_ids)
