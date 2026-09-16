from unittest.mock import AsyncMock, MagicMock

import pytest
from app import redis_client
from app.core.config import BackendSettings


def test_get_redis_client_uses_decoded_responses(monkeypatch: pytest.MonkeyPatch) -> None:
	settings = MagicMock(redis_url="redis://example:6379/2")
	created = MagicMock()
	monkeypatch.setattr(redis_client, "get_backend_settings", lambda: settings)
	monkeypatch.setattr(redis_client.Redis, "from_url", MagicMock(return_value=created))
	redis_client.get_redis_client.cache_clear()

	assert redis_client.get_redis_client() is created
	redis_client.Redis.from_url.assert_called_once_with(settings.redis_url, decode_responses=True)


@pytest.mark.asyncio
async def test_close_redis_client_closes_cached_client(monkeypatch: pytest.MonkeyPatch) -> None:
	client = MagicMock()
	client.aclose = AsyncMock()
	monkeypatch.setattr(redis_client, "get_redis_client", lambda: client)

	await redis_client.close_redis_client()

	client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_ping_redis_propagates_connection_error() -> None:
	client = MagicMock()
	client.ping = AsyncMock(side_effect=ConnectionError("down"))

	with pytest.raises(ConnectionError):
		await redis_client.ping_redis(client)


def test_backend_settings_has_redis_namespace_settings() -> None:
	assert "redis_key_prefix" in BackendSettings.model_fields
	assert "redis_test_db" in BackendSettings.model_fields
