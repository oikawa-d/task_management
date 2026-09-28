"""`GET /api/health`エンドポイント（`app/api/routers/system_router.py`）の
DB・Redis疎通結果に応じたレスポンス内容・ステータスコードのテスト。
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.core.config import get_backend_settings
from app.db import get_db_engine
from app.main import app
from app.redis_client import get_redis_client
from fastapi.testclient import TestClient


@pytest.fixture
def client_with_mocks():
	"""DBエンジンとRedisクライアントをモックに差し替えたFastAPIの`TestClient`を用意するfixture。

	`app.dependency_overrides`で`get_db_engine`・`get_redis_client`をモックへ差し替えたうえで
	`TestClient`・DB接続モック・Redisクライアントモックの3点をタプルで提供する。
	後片付けとして、テスト終了後に`dependency_overrides`をクリアし、他テストへ影響を残さない。
	"""
	mock_connection = AsyncMock()
	mock_connect_ctx = MagicMock()
	mock_connect_ctx.__aenter__.return_value = mock_connection
	mock_connect_ctx.__aexit__.return_value = None
	mock_engine = MagicMock()
	mock_engine.connect.return_value = mock_connect_ctx
	mock_redis = AsyncMock()

	app.dependency_overrides[get_db_engine] = lambda: mock_engine
	app.dependency_overrides[get_redis_client] = lambda: mock_redis

	yield TestClient(app), mock_connection, mock_redis

	app.dependency_overrides.clear()


def test_get_health_endpoint_success(client_with_mocks):
	"""DB・Redisともに正常応答する場合、`/api/health`が200を返し、
	全体および各コンポーネントのstatusが"ok"であることを検証する。
	"""
	client, mock_connection, mock_redis = client_with_mocks
	mock_connection.execute.return_value = None
	mock_redis.ping.return_value = True

	res = client.get("/api/health")

	assert res.status_code == 200
	body = res.json()
	assert body["status"] == "ok"
	assert body["components"]["database"]["status"] == "ok"
	assert body["components"]["redis"]["status"] == "ok"


def test_get_health_endpoint_redis_down(client_with_mocks):
	"""Redisの`ping`が`ConnectionError`を送出する場合、`/api/health`が503を返し、
	全体statusが"degraded"、Redisコンポーネントのstatusが"error"になることを検証する。
	"""
	client, mock_connection, mock_redis = client_with_mocks
	mock_connection.execute.return_value = None
	mock_redis.ping.side_effect = ConnectionError("redis down")

	res = client.get("/api/health")

	assert res.status_code == 503
	body = res.json()
	assert body["status"] == "degraded"
	assert body["components"]["redis"]["status"] == "error"


def test_get_health_endpoint_no_auth_required(client_with_mocks):
	"""`/api/health`が認証無しでアクセスでき、401が返らないことを検証する。"""
	client, mock_connection, mock_redis = client_with_mocks
	mock_connection.execute.return_value = None
	mock_redis.ping.return_value = True

	res = client.get("/api/health")

	assert res.status_code != 401


def test_get_health_endpoint_excludes_secrets(client_with_mocks):
	"""`/api/health`のレスポンス本文に、設定値の`database_url`（接続文字列）が
	そのまま含まれないことを検証する。
	"""
	client, mock_connection, mock_redis = client_with_mocks
	mock_connection.execute.return_value = None
	mock_redis.ping.return_value = True
	settings = get_backend_settings()

	res = client.get("/api/health")

	assert settings.database_url not in res.text
