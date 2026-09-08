import builtins
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from app.repository.session_repository import SessionRepository


class MemoryRedis:
	def __init__(self) -> None:
		self.values: dict[str, str] = {}
		self.expirations: dict[str, float] = {}
		self.sets: dict[str, set[str]] = {}
		self.now = 1000.0

	def pipeline(self, transaction: bool = True) -> "MemoryPipeline":
		return MemoryPipeline(self)

	def _expire(self, key: str) -> None:
		if key in self.expirations and self.expirations[key] <= self.now:
			self.values.pop(key, None)
			self.sets.pop(key, None)
			self.expirations.pop(key, None)

	async def set(self, key: str, value: str, ex: int) -> bool:
		self.values[key] = value
		self.expirations[key] = self.now + ex
		return True

	async def get(self, key: str) -> str | None:
		self._expire(key)
		return self.values.get(key)

	async def delete(self, *keys: str) -> int:
		deleted = 0
		for key in keys:
			self._expire(key)
			if key in self.values or key in self.sets:
				deleted += 1
			self.values.pop(key, None)
			self.sets.pop(key, None)
			self.expirations.pop(key, None)
		return deleted

	async def sadd(self, key: str, value: str) -> int:
		self._expire(key)
		members = self.sets.setdefault(key, set())
		before = len(members)
		members.add(value)
		return int(len(members) > before)

	async def srem(self, key: str, value: str) -> int:
		self._expire(key)
		members = self.sets.get(key, set())
		removed = int(value in members)
		members.discard(value)
		return removed

	async def smembers(self, key: str) -> builtins.set[str]:
		self._expire(key)
		return set(self.sets.get(key, set()))

	async def expire(self, key: str, seconds: int) -> bool:
		self._expire(key)
		if key not in self.values and key not in self.sets:
			return False
		self.expirations[key] = self.now + seconds
		return True


class MemoryPipeline:
	def __init__(self, redis: MemoryRedis) -> None:
		self.redis = redis
		self.commands: list[object] = []

	def set(self, key: str, value: str, ex: int) -> "MemoryPipeline":
		self.commands.append(self.redis.set(key, value, ex))
		return self

	def delete(self, *keys: str) -> "MemoryPipeline":
		self.commands.append(self.redis.delete(*keys))
		return self

	def sadd(self, key: str, value: str) -> "MemoryPipeline":
		self.commands.append(self.redis.sadd(key, value))
		return self

	def srem(self, key: str, value: str) -> "MemoryPipeline":
		self.commands.append(self.redis.srem(key, value))
		return self

	def expire(self, key: str, seconds: int) -> "MemoryPipeline":
		self.commands.append(self.redis.expire(key, seconds))
		return self

	async def execute(self) -> list[object]:
		return [await command for command in self.commands]


async def test_create_get_delete_session_preserves_user_and_created_at() -> None:
	redis = MemoryRedis()
	repository = SessionRepository(redis, key_prefix="test:")
	user_id = uuid4()

	session_id, csrf_token = await repository.create_session(user_id, "127.0.0.1", ttl=30)
	data = await repository.get_session(session_id)

	assert data is not None
	assert data.user_id == user_id
	assert data.ip == "127.0.0.1"
	assert data.created_at.tzinfo is not None
	assert await repository.get_csrf_token(session_id) == csrf_token
	assert redis.expirations["test:session:" + session_id] == 1030

	await repository.delete_session(session_id, user_id)
	assert await repository.get_session(session_id) is None
	assert await repository.get_csrf_token(session_id) is None


async def test_session_expires_when_redis_ttl_is_elapsed() -> None:
	redis = MemoryRedis()
	repository = SessionRepository(redis)
	session_id, _ = await repository.create_session(uuid4(), None, ttl=5)
	redis.now += 5

	assert await repository.get_session(session_id) is None


async def test_touch_session_does_not_extend_past_absolute_expiration() -> None:
	redis = MemoryRedis()
	repository = SessionRepository(redis)
	user_id = uuid4()
	session_id, _ = await repository.create_session(user_id, None, ttl=30)
	absolute_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

	assert await repository.touch_session(session_id, user_id, 30, absolute_expires_at) is False


@pytest.mark.asyncio
async def test_session_data_rejects_corrupt_payload() -> None:
	redis = MemoryRedis()
	repository = SessionRepository(redis)
	await redis.set("session:broken", json.dumps({"user_id": "not-uuid"}), ex=30)

	with pytest.raises(ValueError):
		await repository.get_session("broken")
