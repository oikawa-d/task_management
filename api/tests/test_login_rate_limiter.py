from typing import Any

import pytest
from app.core.config import BackendSettings
from app.core.exceptions import ServiceUnavailableError, TooManyAttemptsError
from app.service.login_rate_limiter import (
	build_login_failure_key,
	check_login_allowed,
	record_login_failure,
	reset_login_failure,
)


class FakeRedis:
	def __init__(self) -> None:
		self.values: dict[str, int] = {}
		self.expire_calls: list[tuple[str, int]] = []
		self.delete_calls: list[str] = []

	async def get(self, key: str) -> str | None:
		value = self.values.get(key)
		return None if value is None else str(value)

	async def incr(self, key: str) -> int:
		self.values[key] = self.values.get(key, 0) + 1
		return self.values[key]

	async def expire(self, key: str, seconds: int) -> bool:
		self.expire_calls.append((key, seconds))
		return True

	async def delete(self, key: str) -> int:
		self.delete_calls.append(key)
		self.values.pop(key, None)
		return 1


class BrokenRedis:
	async def get(self, key: str) -> Any:
		raise ConnectionError("redis unavailable")


def _settings(**overrides: object) -> BackendSettings:
	values = {
		"database_url": "postgresql+asyncpg://user:pass@localhost/db",
		"jwt_secret_key": "test-secret",
		"google_client_id": "client",
		"google_client_secret": "secret",
		"initial_admin_email": "admin@example.com",
		"initial_admin_username": "admin",
		"initial_admin_password": "password",
		"login_max_attempts": 3,
		"login_lock_window_seconds": 60,
	}
	values.update(overrides)
	return BackendSettings(_env_file=None, **values)


@pytest.mark.asyncio
async def test_build_login_failure_key_normalizes_identifier() -> None:
	assert build_login_failure_key(" User@Example.com ", "127.0.0.1") == build_login_failure_key(
		"user@example.com", "127.0.0.1"
	)
	assert "user@example.com" not in build_login_failure_key("user@example.com", "127.0.0.1")


@pytest.mark.asyncio
async def test_login_failure_ttl_is_set_only_on_first_failure() -> None:
	redis = FakeRedis()
	settings = _settings()

	assert await record_login_failure("user@example.com", "127.0.0.1", redis, settings) == 1
	assert await record_login_failure("user@example.com", "127.0.0.1", redis, settings) == 2

	assert len(redis.expire_calls) == 1
	assert redis.expire_calls[0][1] == settings.login_lock_window_seconds


@pytest.mark.asyncio
async def test_login_is_rejected_after_max_attempts_and_reset_allows_retry() -> None:
	redis = FakeRedis()
	settings = _settings()
	for _ in range(settings.login_max_attempts):
		await record_login_failure("user@example.com", "127.0.0.1", redis, settings)

	with pytest.raises(TooManyAttemptsError):
		await check_login_allowed("user@example.com", "127.0.0.1", redis, settings)

	await reset_login_failure("user@example.com", "127.0.0.1", redis, settings)
	assert await check_login_allowed("user@example.com", "127.0.0.1", redis, settings) is None


@pytest.mark.asyncio
async def test_redis_failure_is_fail_closed() -> None:
	with pytest.raises(ServiceUnavailableError):
		await check_login_allowed("user@example.com", "127.0.0.1", BrokenRedis(), _settings())
