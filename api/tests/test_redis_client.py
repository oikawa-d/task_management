"""`app.redis_client`のクライアント生成・クローズ・ping処理、および
Redis名前空間関連の設定フィールドのテスト。
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from app import redis_client
from app.core.config import BackendSettings


def test_get_redis_client_uses_decoded_responses(monkeypatch: pytest.MonkeyPatch) -> None:
	"""`get_redis_client`が設定の`redis_url`を用いて`Redis.from_url`を
	`decode_responses=True`付きで1回だけ呼び出し、生成したクライアントを返すことを検証する。
	"""
	settings = MagicMock(redis_url="redis://example:6379/2")
	created = MagicMock()
	monkeypatch.setattr(redis_client, "get_backend_settings", lambda: settings)
	monkeypatch.setattr(redis_client.Redis, "from_url", MagicMock(return_value=created))
	redis_client.get_redis_client.cache_clear()

	assert redis_client.get_redis_client() is created
	redis_client.Redis.from_url.assert_called_once_with(settings.redis_url, decode_responses=True)


@pytest.mark.asyncio
async def test_close_redis_client_closes_cached_client(monkeypatch: pytest.MonkeyPatch) -> None:
	"""`close_redis_client`が`get_redis_client()`が返すクライアントの`aclose()`を1回だけawaitすることを検証する。"""
	client = MagicMock()
	client.aclose = AsyncMock()
	monkeypatch.setattr(redis_client, "get_redis_client", lambda: client)

	await redis_client.close_redis_client()

	client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_ping_redis_propagates_connection_error() -> None:
	"""`ping_redis`に渡したクライアントの`ping()`が`ConnectionError`を送出した場合、
	例外を握りつぶさずそのまま呼び出し元へ伝播させることを検証する。
	"""
	client = MagicMock()
	client.ping = AsyncMock(side_effect=ConnectionError("down"))

	with pytest.raises(ConnectionError):
		await redis_client.ping_redis(client)


def test_backend_settings_has_redis_namespace_settings() -> None:
	"""`BackendSettings`にRedisキーの名前空間分離に使う`redis_key_prefix`・`redis_test_db`
	フィールドが定義されていることを検証する。
	"""
	assert "redis_key_prefix" in BackendSettings.model_fields
	assert "redis_test_db" in BackendSettings.model_fields
