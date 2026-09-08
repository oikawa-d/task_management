import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.repository.refresh_token_repository import (
	RefreshTokenData,
	RefreshTokenRepository,
	TokenRotationResult,
)


class FakePipeline:
	def __init__(self, redis: "FakeRedis") -> None:
		self.redis = redis
		self.operations: list[tuple[str, tuple[object, ...]]] = []

	def set(self, key: str, value: str, ex: int) -> "FakePipeline":
		self.operations.append(("set", (key, value, ex)))
		return self

	def sadd(self, key: str, value: str) -> "FakePipeline":
		self.operations.append(("sadd", (key, value)))
		return self

	def expire(self, key: str, ttl: int) -> "FakePipeline":
		self.operations.append(("expire", (key, ttl)))
		return self

	def delete(self, *keys: str) -> "FakePipeline":
		self.operations.append(("delete", keys))
		return self

	def srem(self, key: str, value: str) -> "FakePipeline":
		self.operations.append(("srem", (key, value)))
		return self

	async def execute(self) -> list[object]:
		results: list[object] = []
		for operation, args in self.operations:
			method = getattr(self.redis, operation)
			results.append(await method(*args))
		return results


class FakeRedis:
	def __init__(self) -> None:
		self.values: dict[str, str] = {}
		self.ttls: dict[str, int] = {}
		self.sets: dict[str, set[str]] = {}

	def pipeline(self, transaction: bool = True) -> FakePipeline:
		return FakePipeline(self)

	async def set(self, key: str, value: str, ex: int) -> bool:
		self.values[key] = value
		self.ttls[key] = ex
		return True

	async def get(self, key: str) -> str | None:
		return self.values.get(key)

	async def delete(self, *keys: str) -> int:
		deleted = 0
		for key in keys:
			if self.values.pop(key, None) is not None:
				deleted += 1
			self.sets.pop(key, None)
		return deleted

	async def sadd(self, key: str, value: str) -> int:
		members = self.sets.setdefault(key, set())
		before = len(members)
		members.add(value)
		return int(len(members) > before)

	async def expire(self, key: str, ttl: int) -> bool:
		self.ttls[key] = ttl
		return True

	async def srem(self, key: str, value: str) -> int:
		members = self.sets.get(key, set())
		if value not in members:
			return 0
		members.remove(value)
		return 1

	async def eval(self, script: str, numkeys: int, *args: object) -> list[str]:
		return ["invalid", "", ""]


@pytest.fixture
def repository() -> tuple[RefreshTokenRepository, FakeRedis]:
	redis = FakeRedis()
	return RefreshTokenRepository(redis), redis


@pytest.mark.asyncio
async def test_store_and_get_refresh_token_never_store_plaintext(repository) -> None:
	refresh_repo, redis = repository
	plain_token = "refresh-secret-value"
	user_id = uuid4()
	created_at = datetime.now(UTC).replace(microsecond=0)

	await refresh_repo.store(
		plain_token,
		RefreshTokenData(user_id=user_id, jti="refresh-jti", family_id="family-1", created_at=created_at),
		ttl_seconds=900,
	)

	assert plain_token not in redis.values
	assert await refresh_repo.get(plain_token) == RefreshTokenData(
		user_id=user_id, jti="refresh-jti", family_id="family-1", created_at=created_at
	)
	assert redis.ttls[refresh_repo.key_for_token(plain_token)] == 900
	assert json.dumps(redis.values).find(plain_token) == -1


@pytest.mark.asyncio
async def test_delete_refresh_token_removes_value_and_user_index(repository) -> None:
	refresh_repo, redis = repository
	plain_token = "refresh-secret-value"
	metadata = RefreshTokenData(user_id=uuid4(), jti="jti", family_id="family", created_at=datetime.now(UTC))

	await refresh_repo.store(plain_token, metadata, ttl_seconds=60)
	assert await refresh_repo.delete(plain_token) is True
	assert await refresh_repo.get(plain_token) is None
	assert refresh_repo.token_hash(plain_token) not in redis.sets[refresh_repo.user_key(metadata.user_id)]


@pytest.mark.asyncio
async def test_rotate_rejects_missing_token_without_creating_new_token(repository) -> None:
	refresh_repo, _ = repository
	result = await refresh_repo.rotate(
		"old-token",
		"new-token",
		RefreshTokenData(user_id=uuid4(), jti="new-jti", family_id="family", created_at=datetime.now(UTC)),
		ttl_seconds=60,
	)

	assert result == TokenRotationResult.INVALID


def test_refresh_token_data_rejects_invalid_uuid() -> None:
	with pytest.raises(ValueError):
		RefreshTokenData.from_json(
			'{"user_id":"not-a-uuid","jti":"j","family_id":"f","created_at":"2026-01-01T00:00:00+00:00"}'
		)
