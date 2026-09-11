"""notifications_router の結合テスト。

service層(#143でテスト済み)はモックし、router層の責務(認証・CSRF・レート制限の配線と
service呼び出しへの委譲、本人スコープを侵すクエリ/ボディを持たないこと)のみを検証する。
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.api.routers import notifications_router as router_module
from app.auth.factory import get_auth_strategy
from app.core import deps
from app.core.deps import get_current_user
from app.core.exceptions import NotFoundError, UnauthenticatedError, register_error_handling
from app.db import get_db_session
from app.schemas.auth import CurrentUser
from app.schemas.notification import (
	NotificationListResponse,
	NotificationMeta,
	NotificationReadAllResponse,
	NotificationReadResponse,
	UnreadCountResponse,
)
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

ALLOWED_ORIGIN = "http://localhost:5173"
USER_ID = uuid4()


def _current_user() -> CurrentUser:
	return CurrentUser(id=USER_ID, username="alice", role="member", is_active=True, email_verified_at=None)


def _build_app() -> FastAPI:
	app = FastAPI()
	register_error_handling(app)
	app.include_router(router_module.router)
	app.dependency_overrides[get_current_user] = _current_user
	app.dependency_overrides[get_db_session] = lambda: None
	return app


@pytest.fixture
def app_and_mocks(monkeypatch: pytest.MonkeyPatch):
	app = _build_app()
	app.dependency_overrides[get_auth_strategy] = lambda: SimpleNamespace(mode="jwt")
	monkeypatch.setattr(deps.redis_store, "check_rate_limit", AsyncMock(return_value=1))
	monkeypatch.setattr(deps.redis_store, "get_rate_limit_ttl", AsyncMock(return_value=60))
	yield app
	app.dependency_overrides.clear()


@pytest.fixture
def client(app_and_mocks: FastAPI) -> TestClient:
	with TestClient(app_and_mocks) as test_client:
		yield test_client


def test_notifications_router_registers_expected_paths() -> None:
	routes = {
		(route.path, method)
		for route in router_module.router.routes
		if isinstance(route, APIRoute)
		for method in route.methods
	}

	assert ("/api/notifications", "GET") in routes
	assert ("/api/notifications/unread-count", "GET") in routes
	assert ("/api/notifications/{notification_id}/read", "PATCH") in routes
	assert ("/api/notifications/read-all", "POST") in routes


def test_list_notifications_returns_service_result(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	expected = NotificationListResponse(
		items=[], meta=NotificationMeta(page=1, per_page=20, total=0, total_pages=0), unread_count=0
	)
	mock_list = AsyncMock(return_value=expected)
	monkeypatch.setattr(router_module.notification_service, "list_notifications", mock_list)

	res = client.get("/api/notifications")

	assert res.status_code == 200
	assert res.json() == expected.model_dump(mode="json")
	_, called_user, called_page, called_per_page, called_unread_only = mock_list.call_args.args
	assert called_user.id == USER_ID
	assert (called_page, called_per_page, called_unread_only) == (1, 20, False)


def test_list_notifications_forwards_paging_and_unread_only(
	client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
	expected = NotificationListResponse(
		items=[], meta=NotificationMeta(page=2, per_page=5, total=0, total_pages=0), unread_count=0
	)
	mock_list = AsyncMock(return_value=expected)
	monkeypatch.setattr(router_module.notification_service, "list_notifications", mock_list)

	res = client.get("/api/notifications", params={"page": 2, "per_page": 5, "unread_only": True})

	assert res.status_code == 200
	_, _, called_page, called_per_page, called_unread_only = mock_list.call_args.args
	assert (called_page, called_per_page, called_unread_only) == (2, 5, True)


def test_list_notifications_rejects_per_page_over_limit(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	mock_list = AsyncMock()
	monkeypatch.setattr(router_module.notification_service, "list_notifications", mock_list)

	res = client.get("/api/notifications", params={"per_page": 101})

	assert res.status_code == 422
	assert res.json()["error"]["code"] == "VALIDATION_ERROR"
	mock_list.assert_not_called()


def test_list_notifications_unauthenticated_returns_401(app_and_mocks: FastAPI) -> None:
	def _raise() -> CurrentUser:
		raise UnauthenticatedError()

	app_and_mocks.dependency_overrides[get_current_user] = _raise
	with TestClient(app_and_mocks) as client:
		res = client.get("/api/notifications")

	assert res.status_code == 401
	assert res.json()["error"]["code"] == "UNAUTHENTICATED"


def test_list_notifications_rate_limited_returns_429(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(deps.redis_store, "check_rate_limit", AsyncMock(return_value=121))
	mock_list = AsyncMock()
	monkeypatch.setattr(router_module.notification_service, "list_notifications", mock_list)

	res = client.get("/api/notifications")

	assert res.status_code == 429
	assert res.json()["error"]["code"] == "TOO_MANY_ATTEMPTS"
	assert res.headers["retry-after"] == "60"
	mock_list.assert_not_called()


def test_get_unread_count_returns_service_result(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	mock_count = AsyncMock(return_value=UnreadCountResponse(unread_count=3))
	monkeypatch.setattr(router_module.notification_service, "get_unread_count", mock_count)

	res = client.get("/api/notifications/unread-count")

	assert res.status_code == 200
	assert res.json() == {"unread_count": 3}


def test_mark_notification_read_returns_service_result(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	notification_id = uuid4()
	expected = NotificationReadResponse(id=notification_id, read_at=datetime.now(timezone.utc), unread_count=2)
	mock_mark = AsyncMock(return_value=expected)
	monkeypatch.setattr(router_module.notification_service, "mark_notification_read", mock_mark)

	res = client.patch(
		f"/api/notifications/{notification_id}/read",
	)

	assert res.status_code == 200
	_, called_notification_id, called_user = mock_mark.call_args.args
	assert called_notification_id == notification_id
	assert called_user.id == USER_ID


def test_mark_notification_read_other_users_notification_returns_404(
	client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
	mock_mark = AsyncMock(side_effect=NotFoundError())
	monkeypatch.setattr(router_module.notification_service, "mark_notification_read", mock_mark)

	res = client.patch(
		f"/api/notifications/{uuid4()}/read",
		headers={"Origin": ALLOWED_ORIGIN},
	)

	assert res.status_code == 404
	assert res.json()["error"]["code"] == "NOT_FOUND"


def test_mark_notification_read_rejects_disallowed_origin(monkeypatch: pytest.MonkeyPatch) -> None:
	app = _build_app()
	app.dependency_overrides[get_auth_strategy] = lambda: SimpleNamespace(mode="session")
	monkeypatch.setattr(deps.redis_store, "check_rate_limit", AsyncMock(return_value=1))
	mock_mark = AsyncMock()
	monkeypatch.setattr(router_module.notification_service, "mark_notification_read", mock_mark)

	with TestClient(app) as client:
		res = client.patch(
			f"/api/notifications/{uuid4()}/read",
			headers={"Origin": "http://evil.example"},
		)

	assert res.status_code == 403
	assert res.json()["error"]["code"] == "CSRF_INVALID"
	mock_mark.assert_not_called()
	app.dependency_overrides.clear()


def test_mark_notification_read_session_mode_requires_csrf_header(monkeypatch: pytest.MonkeyPatch) -> None:
	app = _build_app()
	app.dependency_overrides[get_auth_strategy] = lambda: SimpleNamespace(mode="session")
	monkeypatch.setattr(deps.redis_store, "check_rate_limit", AsyncMock(return_value=1))
	mock_mark = AsyncMock()
	monkeypatch.setattr(router_module.notification_service, "mark_notification_read", mock_mark)

	with TestClient(app) as client:
		client.cookies.set("cerberus_sid", "sid-1")
		res = client.patch(
			f"/api/notifications/{uuid4()}/read",
			headers={"Origin": ALLOWED_ORIGIN},
		)

	assert res.status_code == 403
	assert res.json()["error"]["code"] == "CSRF_INVALID"
	mock_mark.assert_not_called()
	app.dependency_overrides.clear()


def test_mark_notification_read_session_mode_passes_with_matching_csrf(monkeypatch: pytest.MonkeyPatch) -> None:
	app = _build_app()
	app.dependency_overrides[get_auth_strategy] = lambda: SimpleNamespace(mode="session")
	monkeypatch.setattr(deps.redis_store, "check_rate_limit", AsyncMock(return_value=1))
	monkeypatch.setattr(deps.redis_store, "get_csrf_token", AsyncMock(return_value="token-abc"))
	notification_id = uuid4()
	expected = NotificationReadResponse(id=notification_id, read_at=datetime.now(timezone.utc), unread_count=0)
	mock_mark = AsyncMock(return_value=expected)
	monkeypatch.setattr(router_module.notification_service, "mark_notification_read", mock_mark)

	with TestClient(app) as client:
		client.cookies.set("cerberus_sid", "sid-1")
		res = client.patch(
			f"/api/notifications/{notification_id}/read",
			headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": "token-abc"},
		)

	assert res.status_code == 200
	app.dependency_overrides.clear()


def test_mark_notification_read_jwt_mode_does_not_require_csrf_header(
	client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
	notification_id = uuid4()
	expected = NotificationReadResponse(id=notification_id, read_at=datetime.now(timezone.utc), unread_count=0)
	mock_mark = AsyncMock(return_value=expected)
	monkeypatch.setattr(router_module.notification_service, "mark_notification_read", mock_mark)

	res = client.patch(
		f"/api/notifications/{notification_id}/read",
		headers={"Origin": ALLOWED_ORIGIN},
	)

	assert res.status_code == 200


def test_mark_all_notifications_read_returns_service_result(
	client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
	expected = NotificationReadAllResponse(updated_count=3, unread_count=0)
	mock_mark_all = AsyncMock(return_value=expected)
	monkeypatch.setattr(router_module.notification_service, "mark_all_notifications_read", mock_mark_all)

	res = client.post("/api/notifications/read-all", headers={"Origin": ALLOWED_ORIGIN})

	assert res.status_code == 200
	assert res.json() == {"updated_count": 3, "unread_count": 0}
	_, called_user = mock_mark_all.call_args.args
	assert called_user.id == USER_ID


def test_mark_all_notifications_read_write_rate_limited_returns_429(
	client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
	monkeypatch.setattr(deps.redis_store, "check_rate_limit", AsyncMock(return_value=61))
	mock_mark_all = AsyncMock()
	monkeypatch.setattr(router_module.notification_service, "mark_all_notifications_read", mock_mark_all)

	res = client.post("/api/notifications/read-all", headers={"Origin": ALLOWED_ORIGIN})

	assert res.status_code == 429
	assert res.json()["error"]["code"] == "TOO_MANY_ATTEMPTS"
	assert res.headers["retry-after"] == "60"
	mock_mark_all.assert_not_called()
