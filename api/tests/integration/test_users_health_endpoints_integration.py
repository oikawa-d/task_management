"""Issue #437: users/me系APIとhealth APIの実DB・実Redis結合テスト。"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from app.core.config import get_backend_settings
from app.core.security import hash_password
from app.db import get_db_engine
from app.main import app
from app.redis_client import get_redis_client
from app.repository import login_history_repository, redis_store_auth, redis_store_session, user_repository
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

ALLOWED_ORIGIN = "http://localhost:5173"
TEST_PASSWORD = "OldPass1!"
NEW_PASSWORD = "NewPass2!"


@pytest_asyncio.fixture
async def redis_conn() -> AsyncIterator[Redis]:
	settings = get_backend_settings()
	client = Redis.from_url(settings.redis_url, decode_responses=True)
	try:
		yield client
	finally:
		await client.aclose()


@pytest_asyncio.fixture
async def created_user_ids(db_session: AsyncSession, redis_conn: Redis) -> AsyncIterator[list[uuid.UUID]]:
	ids: list[uuid.UUID] = []
	yield ids
	if not ids:
		return
	await db_session.rollback()
	settings = get_backend_settings()
	for user_id in ids:
		await redis_store_session.delete_all_sessions(redis_conn, settings.redis_key_prefix, user_id)
		await redis_store_auth.revoke_all_refresh_tokens(redis_conn, settings.redis_key_prefix, user_id)
	await db_session.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": ids})
	await db_session.commit()


async def _create_user(db: AsyncSession, ids: list[uuid.UUID], suffix: str) -> dict[str, Any]:
	username = f"issue437_{suffix}_{uuid.uuid4().hex[:10]}"
	user_id = await user_repository.create(db, username, f"{username}@example.com", hash_password(TEST_PASSWORD))
	await user_repository.mark_email_verified(db, user_id)
	await user_repository.update_profile(db, user_id, "山田", "太郎", "ヤマダ", "タロウ", date(1995, 4, 1))
	await db.commit()
	ids.append(user_id)
	return {"id": user_id, "username": username, "password": TEST_PASSWORD}


def _login(client: TestClient, user: dict[str, Any]) -> Any:
	response = client.post(
		"/api/auth/login",
		json={"identifier": user["username"], "password": user["password"]},
		headers={"Origin": ALLOWED_ORIGIN},
	)
	expected_status = 204 if get_backend_settings().auth_mode == "session" else 200
	assert response.status_code == expected_status, response.text
	return response


def _auth_headers(client: TestClient, login_response: Any, *, csrf: bool = False) -> dict[str, str]:
	headers = {"Origin": ALLOWED_ORIGIN}
	if get_backend_settings().auth_mode == "jwt":
		headers["Authorization"] = f"Bearer {login_response.json()['access_token']}"
	if csrf:
		headers["X-CSRF-Token"] = client.cookies.get(get_backend_settings().cookie_name_csrf) or ""
	return headers


async def test_users_me_endpoint_authenticated_success(
	client, db_session: AsyncSession, created_user_ids: list[uuid.UUID]
) -> None:
	user = await _create_user(db_session, created_user_ids, "profile")
	login_response = _login(client, user)
	response = client.get("/api/users/me", headers=_auth_headers(client, login_response))

	assert response.status_code == 200, response.text
	body = response.json()
	assert body["id"] == str(user["id"])
	assert body["profile_completed"] is True
	assert body["has_password"] is True
	assert "auth_mode" not in body
	assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize(
	"path,method,payload",
	[
		("/api/users/me", "GET", None),
		("/api/users/me", "PATCH", {"last_name": "鈴木"}),
		(
			"/api/users/me/password",
			"PUT",
			{"current_password": TEST_PASSWORD, "new_password": NEW_PASSWORD, "password_confirm": NEW_PASSWORD},
		),
		("/api/users/me/login-history", "GET", None),
	],
)
def test_users_me_endpoints_unauthenticated(client, path: str, method: str, payload: dict[str, str] | None) -> None:
	response = client.request(method, path, json=payload, headers={"Origin": ALLOWED_ORIGIN})

	assert response.status_code == 401, response.text
	assert response.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_users_me_endpoint_inactive_user_returns_forbidden(
	client, db_session: AsyncSession, created_user_ids: list[uuid.UUID]
) -> None:
	user = await _create_user(db_session, created_user_ids, "inactive")
	login_response = _login(client, user)
	await db_session.execute(text("UPDATE users SET is_active = false WHERE id = :user_id"), {"user_id": user["id"]})
	await db_session.commit()

	response = client.get("/api/users/me", headers=_auth_headers(client, login_response))

	assert response.status_code == 403
	assert response.json()["error"]["code"] == "USER_INACTIVE"


async def test_patch_users_me_endpoint_success(
	client, db_session: AsyncSession, created_user_ids: list[uuid.UUID]
) -> None:
	user = await _create_user(db_session, created_user_ids, "patch")
	login_response = _login(client, user)
	response = client.patch(
		"/api/users/me", json={"last_name": "鈴木"}, headers=_auth_headers(client, login_response, csrf=True)
	)

	assert response.status_code == 200, response.text
	await db_session.rollback()
	stored = await user_repository.get_by_id(db_session, user["id"])
	assert stored is not None and stored.last_name == "鈴木"


async def test_put_users_me_password_endpoint_success(
	client, db_session: AsyncSession, created_user_ids: list[uuid.UUID]
) -> None:
	user = await _create_user(db_session, created_user_ids, "password")
	login_response = _login(client, user)
	response = client.put(
		"/api/users/me/password",
		json={"current_password": TEST_PASSWORD, "new_password": NEW_PASSWORD, "password_confirm": NEW_PASSWORD},
		headers=_auth_headers(client, login_response, csrf=True),
	)

	assert response.status_code == 204
	if get_backend_settings().auth_mode == "session":
		assert client.get("/api/users/me").status_code == 401
	else:
		refresh = client.post("/api/auth/refresh", headers=_auth_headers(client, login_response, csrf=True))
		assert refresh.status_code == 401
	new_login = client.post(
		"/api/auth/login",
		json={"identifier": user["username"], "password": NEW_PASSWORD},
		headers={"Origin": ALLOWED_ORIGIN},
	)
	expected_status = 204 if get_backend_settings().auth_mode == "session" else 200
	assert new_login.status_code == expected_status


async def test_get_users_me_login_history_endpoint_is_scoped(
	client,
	db_session: AsyncSession,
	created_user_ids: list[uuid.UUID],
) -> None:
	user = await _create_user(db_session, created_user_ids, "history")
	other = await _create_user(db_session, created_user_ids, "other")
	login_response = _login(client, user)

	response = client.get("/api/users/me/login-history", headers=_auth_headers(client, login_response))
	rows = await login_history_repository.list_by_user_id(db_session, user["id"], limit=50)
	other_rows = await login_history_repository.list_by_user_id(db_session, other["id"], limit=50)

	assert response.status_code == 200, response.text
	assert response.json()["meta"]["count"] >= 1
	assert {item["id"] for item in response.json()["items"]} == {str(row.id) for row in rows}
	assert other_rows == []


async def test_users_me_endpoint_db_failure_returns_service_unavailable(
	client,
	db_session: AsyncSession,
	created_user_ids: list[uuid.UUID],
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	user = await _create_user(db_session, created_user_ids, "dbfailure")
	login_response = _login(client, user)

	async def fail_get_by_id(*_args: Any, **_kwargs: Any) -> Any:
		raise OperationalError("SELECT * FROM fn_get_user", {}, SimpleNamespace(sqlstate="08006"))

	monkeypatch.setattr(user_repository, "get_by_id", fail_get_by_id)
	response = client.get("/api/users/me", headers=_auth_headers(client, login_response))

	assert response.status_code == 503
	assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


async def test_users_me_endpoint_session_redis_failure_returns_service_unavailable(
	client,
	db_session: AsyncSession,
	created_user_ids: list[uuid.UUID],
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	if get_backend_settings().auth_mode != "session":
		pytest.skip("AUTH_MODE=sessionでのみ検証する")
	user = await _create_user(db_session, created_user_ids, "redisfailure")
	login_response = _login(client, user)

	async def fail_get_session(*_args: Any, **_kwargs: Any) -> Any:
		raise RedisConnectionError("redis down")

	monkeypatch.setattr("app.auth.session_auth.redis_store.get_session", fail_get_session)
	response = client.get("/api/users/me", headers=_auth_headers(client, login_response))

	assert response.status_code == 503
	assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


def test_get_health_endpoint_no_auth_required(client) -> None:
	response = client.get("/api/health")

	assert response.status_code == 200
	body = response.json()
	assert body["status"] == "ok"
	assert body["auth_mode"] == get_backend_settings().auth_mode
	assert body["components"]["database"]["status"] == "ok"
	assert body["components"]["redis"]["status"] == "ok"
	assert "error" not in body


def test_get_health_endpoint_redis_down(client) -> None:
	class BrokenRedis:
		async def ping(self) -> bool:
			raise RedisConnectionError("redis down")

	app.dependency_overrides[get_redis_client] = lambda: BrokenRedis()
	try:
		response = client.get("/api/health")
	finally:
		app.dependency_overrides.pop(get_redis_client, None)

	assert response.status_code == 503
	body = response.json()
	assert body["status"] == "degraded"
	assert body["components"]["redis"] == {"status": "error", "latency_ms": None}
	assert "error" not in body


def test_get_health_endpoint_database_down(client) -> None:
	class BrokenConnection:
		async def __aenter__(self) -> Any:
			raise OperationalError("SELECT 1", {}, SimpleNamespace(sqlstate="08006"))

		async def __aexit__(self, *_args: Any) -> None:
			return None

	class BrokenEngine:
		def connect(self) -> BrokenConnection:
			return BrokenConnection()

	app.dependency_overrides[get_db_engine] = lambda: BrokenEngine()
	try:
		response = client.get("/api/health")
	finally:
		app.dependency_overrides.pop(get_db_engine, None)

	assert response.status_code == 503
	body = response.json()
	assert body["status"] == "degraded"
	assert body["components"]["database"] == {"status": "error", "latency_ms": None}
	assert "error" not in body
