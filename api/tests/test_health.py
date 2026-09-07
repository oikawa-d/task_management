from unittest.mock import AsyncMock, MagicMock

import pytest
from app.core.config import get_backend_settings
from app.db import get_db_engine
from app.main import app
from app.redis_client import get_redis_client
from fastapi.testclient import TestClient


@pytest.fixture
def client_with_mocks():
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
	client, mock_connection, mock_redis = client_with_mocks
	mock_connection.execute.return_value = None
	mock_redis.ping.side_effect = ConnectionError("redis down")

	res = client.get("/api/health")

	assert res.status_code == 503
	body = res.json()
	assert body["status"] == "degraded"
	assert body["components"]["redis"]["status"] == "error"


def test_get_health_endpoint_no_auth_required(client_with_mocks):
	client, mock_connection, mock_redis = client_with_mocks
	mock_connection.execute.return_value = None
	mock_redis.ping.return_value = True

	res = client.get("/api/health")

	assert res.status_code != 401


def test_get_health_endpoint_excludes_secrets(client_with_mocks):
	client, mock_connection, mock_redis = client_with_mocks
	mock_connection.execute.return_value = None
	mock_redis.ping.return_value = True
	settings = get_backend_settings()

	res = client.get("/api/health")

	assert settings.database_url not in res.text
