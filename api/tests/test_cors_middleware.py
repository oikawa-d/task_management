"""app.main に登録した CORSMiddleware の結合テスト。

`docs/detailed_design/auth/03_csrf.md` §2, §10 の要求
(CORS_ALLOW_ORIGINSの明示的リストのみ許可・allow_credentials=Trueとの併用禁止)を
実際のCORSMiddlewareの挙動として検証する。
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.core.config import get_backend_settings
from app.db import get_db_engine
from app.main import app
from app.redis_client import get_redis_client
from fastapi.testclient import TestClient

ALLOWED_ORIGIN = "http://localhost:5173"
DISALLOWED_ORIGIN = "http://evil.example"


@pytest.fixture
def client_with_mocks():
	mock_connection = AsyncMock()
	mock_connect_ctx = MagicMock()
	mock_connect_ctx.__aenter__.return_value = mock_connection
	mock_connect_ctx.__aexit__.return_value = None
	mock_engine = MagicMock()
	mock_engine.connect.return_value = mock_connect_ctx
	mock_redis = AsyncMock()
	mock_redis.ping.return_value = True

	app.dependency_overrides[get_db_engine] = lambda: mock_engine
	app.dependency_overrides[get_redis_client] = lambda: mock_redis

	yield TestClient(app), mock_connection

	app.dependency_overrides.clear()


def test_preflight_from_allowed_origin_returns_cors_headers(client_with_mocks) -> None:
	client, _ = client_with_mocks
	settings = get_backend_settings()

	res = client.options(
		"/api/health",
		headers={
			"Origin": ALLOWED_ORIGIN,
			"Access-Control-Request-Method": "GET",
		},
	)

	assert res.status_code == 200
	assert res.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
	assert res.headers["access-control-allow-credentials"] == "true"
	assert res.headers["access-control-max-age"] == str(settings.cors_max_age_seconds)


def test_actual_request_from_allowed_origin_includes_cors_headers(client_with_mocks) -> None:
	client, mock_connection = client_with_mocks
	mock_connection.execute.return_value = None

	res = client.get("/api/health", headers={"Origin": ALLOWED_ORIGIN})

	assert res.status_code == 200
	assert res.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
	assert res.headers["access-control-allow-credentials"] == "true"


def test_preflight_from_disallowed_origin_has_no_cors_headers(client_with_mocks) -> None:
	client, _ = client_with_mocks

	res = client.options(
		"/api/health",
		headers={
			"Origin": DISALLOWED_ORIGIN,
			"Access-Control-Request-Method": "GET",
		},
	)

	assert "access-control-allow-origin" not in res.headers


def test_actual_request_from_disallowed_origin_has_no_cors_headers(client_with_mocks) -> None:
	client, mock_connection = client_with_mocks
	mock_connection.execute.return_value = None

	res = client.get("/api/health", headers={"Origin": DISALLOWED_ORIGIN})

	# StarletteのCORSMiddlewareは不許可Originでもアプリ自体は200を返すが、
	# CORSヘッダーは付与しないためブラウザ側でレスポンスが読み取れない。
	assert res.status_code == 200
	assert "access-control-allow-origin" not in res.headers
