from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest
from app.repository import redis_store


class _Pipeline:
	def __init__(self, redis: "_FakeRedis") -> None:
		self.redis = redis
		self.operations: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

	def __enter__(self) -> "_Pipeline":
		return self

	def __exit__(self, *_args: object) -> None:
		return None

	def _add(self, name: str, *args: Any, **kwargs: Any) -> "_Pipeline":
		self.operations.append((name, args, kwargs))
		return self

	def set(self, *args: Any, **kwargs: Any) -> "_Pipeline":
		return self._add("set", *args, **kwargs)

	def setex(self, *args: Any, **kwargs: Any) -> "_Pipeline":
		return self._add("setex", *args, **kwargs)

	def sadd(self, *args: Any, **kwargs: Any) -> "_Pipeline":
		return self._add("sadd", *args, **kwargs)

	def srem(self, *args: Any, **kwargs: Any) -> "_Pipeline":
		return self._add("srem", *args, **kwargs)

	def expire(self, *args: Any, **kwargs: Any) -> "_Pipeline":
		return self._add("expire", *args, **kwargs)

	def delete(self, *args: Any, **kwargs: Any) -> "_Pipeline":
		return self._add("delete", *args, **kwargs)

	async def execute(self) -> list[Any]:
		results = []
		for name, args, kwargs in self.operations:
			results.append(await getattr(self.redis, name)(*args, **kwargs))
		return results


class _FakeRedis:
	def __init__(self) -> None:
		self.values: dict[str, str] = {}
		self.sets: dict[str, set[str]] = {}
		self.ttls: dict[str, int] = {}
		self.binary_members = False

	def pipeline(self, transaction: bool = True) -> _Pipeline:
		assert transaction
		return _Pipeline(self)

	async def set(self, name: str, value: str, ex: int | None = None, nx: bool = False) -> bool | None:
		if nx and name in self.values:
			return None
		self.values[name] = value
		if ex is not None:
			self.ttls[name] = ex
		return True

	async def setex(self, name: str, time: int, value: str) -> bool:
		self.values[name] = value
		self.ttls[name] = time
		return True

	async def get(self, name: str) -> str | None:
		return self.values.get(name)

	async def getdel(self, name: str) -> str | None:
		return self.values.pop(name, None)

	async def delete(self, *names: str) -> int:
		deleted = 0
		for name in names:
			if name in self.values:
				del self.values[name]
				deleted += 1
			self.sets.pop(name, None)
			self.ttls.pop(name, None)
		return deleted

	async def sadd(self, name: str, *values: str) -> int:
		members = self.sets.setdefault(name, set())
		before = len(members)
		members.update(values)
		return len(members) - before

	async def srem(self, name: str, *values: str) -> int:
		members = self.sets.setdefault(name, set())
		removed = sum(value in members for value in values)
		members.difference_update(values)
		return removed

	async def smembers(self, name: str) -> set[str]:
		members = self.sets.get(name, set())
		return {member.encode() if self.binary_members else member for member in members}  # type: ignore[return-value]

	async def expire(self, name: str, time: int) -> bool:
		self.ttls[name] = time
		return True

	async def incr(self, name: str) -> int:
		value = int(self.values.get(name, "0")) + 1
		self.values[name] = str(value)
		return value

	async def ttl(self, name: str) -> int:
		return self.ttls.get(name, -1)

	async def pttl(self, name: str) -> int:
		ttl = self.ttls.get(name, -1)
		return ttl * 1000 if ttl >= 0 else ttl

	async def eval(self, *_args: Any, **_kwargs: Any) -> list[Any]:
		return []

	async def ping(self) -> bool:
		return True


@pytest.fixture
def redis(monkeypatch: pytest.MonkeyPatch) -> _FakeRedis:
	fake = _FakeRedis()
	monkeypatch.setattr(redis_store, "get_redis_client", lambda: fake)
	monkeypatch.setattr(redis_store, "_key_prefix", lambda: "test:")
	return fake


async def test_session_lifecycle_keeps_keys_and_user_set_consistent(redis: _FakeRedis) -> None:
	user_id = uuid.uuid4()
	session_id, csrf_token = await redis_store.create_session(user_id, "127.0.0.1", 60)

	assert json.loads(redis.values[f"test:session:{session_id}"])["user_id"] == str(user_id)
	assert json.loads(redis.values[f"test:csrf:{session_id}"]) == {"token": csrf_token}
	assert session_id in redis.sets[f"test:user_sessions:{user_id}"]
	assert await redis_store.get_session(session_id)
	assert await redis_store.get_csrf_token(session_id) == csrf_token

	assert await redis_store.delete_session(session_id, user_id) is None
	assert await redis_store.get_session(session_id) is None
	assert session_id not in redis.sets[f"test:user_sessions:{user_id}"]


async def test_touch_session_respects_absolute_expiry_and_delete_all(redis: _FakeRedis) -> None:
	user_id = uuid.uuid4()
	first, _ = await redis_store.create_session(user_id, None, 60)
	second, _ = await redis_store.create_session(user_id, None, 60)

	assert await redis_store.touch_session(first, user_id, 30, datetime.now(UTC) + timedelta(seconds=120))
	assert redis.ttls[f"test:session:{first}"] == 30
	assert not await redis_store.touch_session(first, user_id, 30, datetime.now(UTC) - timedelta(seconds=1))
	assert await redis_store.delete_all_sessions(user_id) == 2
	assert not redis.sets.get(f"test:user_sessions:{user_id}")
	assert second not in redis.values


async def test_user_indexes_support_redis_binary_members(redis: _FakeRedis) -> None:
	user_id = uuid.uuid4()
	first, _ = await redis_store.create_session(user_id, None, 60)
	second, _ = await redis_store.create_session(user_id, None, 60)
	redis.binary_members = True

	assert await redis_store.delete_all_sessions(user_id) == 2
	assert first not in redis.values
	assert second not in redis.values

	await redis_store.store_refresh_token("one", user_id, "family", 90)
	await redis_store.store_refresh_token("two", user_id, "family", 90)
	assert await redis_store.revoke_all_refresh_tokens(user_id) == 2
	assert not [name for name in redis.values if name.startswith("test:refresh:")]


async def test_refresh_token_storage_and_revocation(redis: _FakeRedis) -> None:
	user_id = uuid.uuid4()
	await redis_store.store_refresh_token("old", user_id, "family", 90)
	data = await redis_store.get_refresh_token("old")

	assert data is not None
	assert data.user_id == user_id
	assert data.family_id == "family"
	assert await redis_store.revoke_refresh_token("old", user_id) is None
	assert await redis_store.get_refresh_token("old") is None

	await redis_store.store_refresh_token("one", user_id, "family", 90)
	await redis_store.store_refresh_token("two", user_id, "other", 90)
	assert await redis_store.revoke_token_family(user_id, "family") == 1
	assert await redis_store.revoke_all_refresh_tokens(user_id) == 1


async def test_one_time_tokens_are_consumed_once(redis: _FakeRedis) -> None:
	user_id = uuid.uuid4()
	await redis_store.save_oauth_state("state", "/dashboard", "verifier", "nonce", 60)
	assert (await redis_store.consume_oauth_state("state")).nonce == "nonce"
	assert await redis_store.consume_oauth_state("state") is None
	await redis_store.save_oauth_handoff("code", user_id, "/dashboard", 60)
	assert (await redis_store.consume_oauth_handoff("code")).user_id == user_id
	assert await redis_store.consume_oauth_handoff("code") is None


async def test_password_and_email_tokens_enforce_current_value(redis: _FakeRedis) -> None:
	user_id = uuid.uuid4()
	redis.eval = AsyncMock(return_value=[str(user_id)])
	await redis_store.save_password_reset_token("reset", user_id, 60)
	assert redis.eval.await_count == 1
	redis.eval = AsyncMock(return_value=str(user_id))
	assert await redis_store.consume_password_reset_token("reset") == user_id

	await redis_store.replace_email_verify_token("email-one", user_id, 60)
	assert await redis_store.mark_email_verify_sent(user_id, 60)
	assert not await redis_store.mark_email_verify_sent(user_id, 60)
	assert await redis_store.consume_email_verify_token("email-one") == user_id
	assert await redis_store.consume_email_verify_token("email-one") is None


async def test_login_failures_and_rate_limit_are_hashed_and_expiring(redis: _FakeRedis) -> None:
	assert await redis_store.get_login_failure_count("user@example.com", "127.0.0.1") == 0

	first = await redis_store.incr_login_failure(" User@Example.COM ", "127.0.0.1", 60)
	second = await redis_store.incr_login_failure("user@example.com", "127.0.0.1", 60)
	assert (first, second) == (1, 2)
	assert next(key for key in redis.values if key.startswith("test:login_fail:"))
	assert await redis_store.get_login_failure_count("user@example.com", "127.0.0.1") == 2
	assert await redis_store.get_login_failure_ttl("user@example.com", "127.0.0.1") == 60

	await redis_store.reset_login_failure("user@example.com", "127.0.0.1")
	assert not [key for key in redis.values if key.startswith("test:login_fail:")]
	assert await redis_store.get_login_failure_count("user@example.com", "127.0.0.1") == 0

	assert await redis_store.check_rate_limit("register", "127.0.0.1", 2, 60) == 1
	assert await redis_store.check_rate_limit("register", "127.0.0.1", 2, 60) == 2
	assert await redis_store.check_rate_limit("register", "127.0.0.1", 2, 60) == 3
	assert await redis_store.get_rate_limit_ttl("register", "127.0.0.1") == 60


async def test_rate_limit_ttl_rounds_up_remaining_milliseconds(
	redis: _FakeRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
	monkeypatch.setattr(redis, "pttl", AsyncMock(return_value=1234))

	assert await redis_store.get_rate_limit_ttl("register", "127.0.0.1") == 2


async def test_rate_limit_ttl_uses_minimum_retry_after_when_key_is_missing(
	redis: _FakeRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
	monkeypatch.setattr(redis, "pttl", AsyncMock(return_value=-2))

	assert await redis_store.get_rate_limit_ttl("register", "127.0.0.1") == 1


async def test_rotate_refresh_token_returns_reuse_marker(redis: _FakeRedis) -> None:
	user_id = uuid.uuid4()
	redis.eval = AsyncMock(return_value=[2, str(user_id), "family"])
	result = await redis_store.rotate_refresh_token("old", "new", 60)

	assert isinstance(result, redis_store.TokenReused)
	assert result.user_id == user_id
	assert result.family_id == "family"
	redis.eval.assert_awaited_once()


async def test_ping_propagates_redis_result(redis: _FakeRedis) -> None:
	assert await redis_store.ping()
	redis.ping = AsyncMock(side_effect=ConnectionError("down"))
	with pytest.raises(ConnectionError):
		await redis_store.ping()
