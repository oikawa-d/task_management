from uuid import uuid4

import pytest
from app.repository import oauth_handoff_repository


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
async def test_handoff_validates_user_and_redirect_and_consumes_once() -> None:
	redis = FakeRedis()
	user_id = uuid4()

	await oauth_handoff_repository.save_oauth_handoff("handoff-1", user_id, "/projects/1", 60, redis=redis)

	assert redis.ttls["oauth_handoff:handoff-1"] == 60
	data = await oauth_handoff_repository.consume_oauth_handoff("handoff-1", redis=redis)
	assert data is not None
	assert data.user_id == user_id
	assert data.redirect_to == "/projects/1"
	assert await oauth_handoff_repository.consume_oauth_handoff("handoff-1", redis=redis) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("redirect_to", ["https://evil.example", "//evil.example", "dashboard"])
async def test_handoff_rejects_non_relative_redirect(redirect_to: str) -> None:
	with pytest.raises(ValueError):
		await oauth_handoff_repository.save_oauth_handoff("handoff-1", uuid4(), redirect_to, 60, redis=FakeRedis())
