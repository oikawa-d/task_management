from datetime import datetime, timezone

import pytest
from app.repository import oauth_state_repository


class FakeRedis:
	def __init__(self) -> None:
		self.values: dict[str, str] = {}
		self.ttls: dict[str, int] = {}

	async def setex(self, key: str, ttl: int, value: str) -> None:
		self.values[key] = value
		self.ttls[key] = ttl

	async def getdel(self, key: str) -> str | None:
		return self.values.pop(key, None)


@pytest.mark.asyncio
async def test_save_oauth_state_stores_expected_value_and_ttl() -> None:
	redis = FakeRedis()

	await oauth_state_repository.save_oauth_state("state-1", "/dashboard", "verifier-1", "nonce-1", 600, redis=redis)

	assert redis.ttls["oauth_state:state-1"] == 600
	data = await oauth_state_repository.consume_oauth_state("state-1", redis=redis)
	assert data is not None
	assert data.redirect_to == "/dashboard"
	assert data.code_verifier == "verifier-1"
	assert data.nonce == "nonce-1"
	assert isinstance(data.created_at, datetime)
	assert data.created_at.tzinfo == timezone.utc


@pytest.mark.asyncio
async def test_consume_oauth_state_is_one_time() -> None:
	redis = FakeRedis()
	await oauth_state_repository.save_oauth_state("state-1", "/", "verifier", "nonce", 600, redis=redis)

	assert await oauth_state_repository.consume_oauth_state("state-1", redis=redis) is not None
	assert await oauth_state_repository.consume_oauth_state("state-1", redis=redis) is None


@pytest.mark.asyncio
async def test_save_oauth_state_rejects_external_redirect() -> None:
	with pytest.raises(ValueError):
		await oauth_state_repository.save_oauth_state(
			"state-1", "https://evil.example/", "verifier", "nonce", 600, redis=FakeRedis()
		)
