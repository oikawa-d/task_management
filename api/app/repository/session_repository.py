import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID


class RedisSessionPipeline(Protocol):
	def set(self, key: str, value: str, ex: int) -> "RedisSessionPipeline": ...
	def delete(self, *keys: str) -> "RedisSessionPipeline": ...
	def sadd(self, key: str, value: str) -> "RedisSessionPipeline": ...
	def srem(self, key: str, value: str) -> "RedisSessionPipeline": ...
	def expire(self, key: str, seconds: int) -> "RedisSessionPipeline": ...
	async def execute(self) -> list[object]: ...


class RedisSessionInterface(Protocol):
	def pipeline(self, transaction: bool = True) -> RedisSessionPipeline: ...

	async def set(self, key: str, value: str, ex: int) -> bool: ...
	async def get(self, key: str) -> str | bytes | None: ...
	async def delete(self, *keys: str) -> int: ...
	async def sadd(self, key: str, value: str) -> int: ...
	async def srem(self, key: str, value: str) -> int: ...
	async def expire(self, key: str, seconds: int) -> bool: ...


@dataclass(frozen=True)
class SessionData:
	user_id: UUID
	created_at: datetime
	ip: str | None


class SessionRepository:
	def __init__(self, redis: RedisSessionInterface, key_prefix: str = "") -> None:
		self._redis = redis
		self._key_prefix = key_prefix

	def _key(self, kind: str, identifier: str) -> str:
		return f"{self._key_prefix}{kind}:{identifier}"

	def _session_key(self, session_id: str) -> str:
		return self._key("session", session_id)

	def _csrf_key(self, session_id: str) -> str:
		return self._key("csrf", session_id)

	def _user_sessions_key(self, user_id: UUID) -> str:
		return self._key("user_sessions", str(user_id))

	@staticmethod
	def _decode(value: str | bytes | None) -> str | None:
		if value is None:
			return None
		return value.decode() if isinstance(value, bytes) else value

	async def create_session(self, user_id: UUID, ip: str | None, ttl: int) -> tuple[str, str]:
		if ttl <= 0:
			raise ValueError("session TTL must be positive")
		session_id = secrets.token_urlsafe(32)
		csrf_token = secrets.token_urlsafe(32)
		created_at = datetime.now(timezone.utc)
		payload = json.dumps(
			{"user_id": str(user_id), "created_at": created_at.isoformat(), "ip": ip},
			separators=(",", ":"),
		)
		user_sessions_key = self._user_sessions_key(user_id)
		pipeline = self._redis.pipeline(transaction=True)
		pipeline.set(self._session_key(session_id), payload, ex=ttl)
		pipeline.set(self._csrf_key(session_id), csrf_token, ex=ttl)
		pipeline.sadd(user_sessions_key, session_id)
		pipeline.expire(user_sessions_key, ttl)
		await pipeline.execute()
		return session_id, csrf_token

	async def get_session(self, session_id: str) -> SessionData | None:
		value = self._decode(await self._redis.get(self._session_key(session_id)))
		if value is None:
			return None
		payload = json.loads(value)
		return SessionData(
			user_id=UUID(payload["user_id"]),
			created_at=datetime.fromisoformat(payload["created_at"]),
			ip=payload.get("ip"),
		)

	async def touch_session(
		self,
		session_id: str,
		user_id: UUID,
		ttl: int,
		absolute_expires_at: datetime,
	) -> bool:
		if ttl <= 0:
			return False
		session = await self.get_session(session_id)
		if session is None or session.user_id != user_id:
			return False
		remaining = int((absolute_expires_at - datetime.now(timezone.utc)).total_seconds())
		effective_ttl = min(ttl, remaining)
		if effective_ttl <= 0:
			return False
		pipeline = self._redis.pipeline(transaction=True)
		pipeline.expire(self._session_key(session_id), effective_ttl)
		pipeline.expire(self._csrf_key(session_id), effective_ttl)
		pipeline.expire(self._user_sessions_key(user_id), effective_ttl)
		await pipeline.execute()
		return True

	async def get_csrf_token(self, session_id: str) -> str | None:
		return self._decode(await self._redis.get(self._csrf_key(session_id)))

	async def delete_session(self, session_id: str, user_id: UUID) -> None:
		pipeline = self._redis.pipeline(transaction=True)
		pipeline.delete(self._session_key(session_id), self._csrf_key(session_id))
		pipeline.srem(self._user_sessions_key(user_id), session_id)
		await pipeline.execute()

	async def create(self, user_id: UUID, ip: str | None, ttl: int) -> tuple[str, str]:
		return await self.create_session(user_id, ip, ttl)

	async def get(self, session_id: str) -> SessionData | None:
		return await self.get_session(session_id)

	async def delete(self, session_id: str, user_id: UUID) -> None:
		await self.delete_session(session_id, user_id)
