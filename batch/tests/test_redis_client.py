from unittest.mock import AsyncMock, MagicMock

import pytest
from app import redis_client
from app.core.config import BatchSettings


def test_create_redis_client_uses_decoded_responses(monkeypatch: pytest.MonkeyPatch) -> None:
	settings = MagicMock(redis_url="redis://example:6379/2")
	created = MagicMock()
	monkeypatch.setattr(redis_client, "from_url", MagicMock(return_value=created))

	assert redis_client.create_redis_client(settings) is created
	redis_client.from_url.assert_called_once_with(settings.redis_url, decode_responses=True)


@pytest.mark.asyncio
async def test_close_redis_client_calls_aclose() -> None:
	client = MagicMock()
	client.aclose = AsyncMock()

	await redis_client.close_redis_client(client)

	client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_ping_redis_propagates_connection_error() -> None:
	client = MagicMock()
	client.ping = AsyncMock(side_effect=ConnectionError("down"))

	with pytest.raises(ConnectionError):
		await redis_client.ping_redis(client)


def test_batch_settings_has_shared_redis_namespace_settings() -> None:
	assert "redis_key_prefix" in BatchSettings.model_fields
	assert "redis_test_db" in BatchSettings.model_fields
