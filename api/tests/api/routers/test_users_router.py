"""users_router の結合テスト。

service層(user_service, #113でテスト済み)はモックし、router層の責務
(認証・CSRF/Origin検証の配線とservice呼び出しへの委譲、エラーのHTTPステータスへの
マッピング)のみを検証する。設計書のテスト表(01〜04)の結合テストケースに対応する。

08_login_history §12 No.9「他ユーザーの履歴が混入しないこと」はservice層
(login_history_repository経由でuser_id条件を必ず付与)の責務であり、
tests/service/test_user_service.py側でカバー済みのためここでは扱わない。
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.api.routers import users_router as router_module
from app.auth.factory import get_auth_strategy
from app.core import deps
from app.core.deps import get_current_user
from app.core.exceptions import (
	InvalidCredentialsError,
	UnauthenticatedError,
	UserInactiveError,
	ValidationError,
	register_error_handling,
)
from app.db import get_db_session
from app.schemas.auth import CurrentUser
from app.schemas.user import LoginHistoryListResponse, LoginHistoryMeta, UserProfileResponse
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

ALLOWED_ORIGIN = "http://localhost:5173"
USER_ID = uuid4()


def _current_user() -> CurrentUser:
	return CurrentUser(id=USER_ID, username="taro", role="member", is_active=True, email_verified_at=None)


def _profile_response(**overrides: object) -> UserProfileResponse:
	defaults: dict[str, object] = {
		"id": USER_ID,
		"username": "taro",
		"email": "taro@example.com",
		"last_name": "山田",
		"first_name": "太郎",
		"last_name_kana": "ヤマダ",
		"first_name_kana": "タロウ",
		"birth_date": date(1995, 4, 1),
		"profile_completed": True,
		"role": "member",
		"has_password": True,
		"oauth_providers": ["google"],
	}
	defaults.update(overrides)
	return UserProfileResponse.model_validate(defaults)


def _build_app() -> FastAPI:
	app = FastAPI()
	register_error_handling(app)
	app.include_router(router_module.router)
	app.dependency_overrides[get_current_user] = _current_user
	app.dependency_overrides[get_db_session] = lambda: None
	return app


def _app_with_mode(mode: str) -> FastAPI:
	app = _build_app()
	app.dependency_overrides[get_auth_strategy] = lambda: SimpleNamespace(mode=mode)
	return app


@pytest.fixture
def app_and_mocks() -> FastAPI:
	app = _app_with_mode("jwt")
	yield app
	app.dependency_overrides.clear()


@pytest.fixture
def client(app_and_mocks: FastAPI) -> TestClient:
	with TestClient(app_and_mocks) as test_client:
		yield test_client


def _unauthenticated_client(app: FastAPI) -> TestClient:
	def _raise() -> CurrentUser:
		raise UnauthenticatedError()

	app.dependency_overrides[get_current_user] = _raise
	return TestClient(app)


def _inactive_user_client(app: FastAPI) -> TestClient:
	def _raise() -> CurrentUser:
		raise UserInactiveError()

	app.dependency_overrides[get_current_user] = _raise
	return TestClient(app)


def test_users_router_registers_users_me_endpoints() -> None:
	routes = {
		(route.path, method)
		for route in router_module.router.routes
		if isinstance(route, APIRoute)
		for method in route.methods
	}

	assert ("/api/users/me", "GET") in routes
	assert ("/api/users/me", "PATCH") in routes
	assert ("/api/users/me/password", "PUT") in routes
	assert ("/api/users/me/login-history", "GET") in routes


def test_change_my_password_route_returns_no_content_status() -> None:
	password_routes = [
		route
		for route in router_module.router.routes
		if isinstance(route, APIRoute) and route.path == "/api/users/me/password"
	]

	assert password_routes[0].status_code == 204


# --- GET /api/users/me ------------------------------------------------------


def test_get_my_profile_session_mode_success(monkeypatch: pytest.MonkeyPatch) -> None:
	app = _app_with_mode("session")
	expected = _profile_response()
	mock_get_profile = AsyncMock(return_value=expected)
	monkeypatch.setattr(router_module.user_service, "get_profile", mock_get_profile)

	with TestClient(app) as client:
		res = client.get("/api/users/me")

	assert res.status_code == 200
	assert res.json() == expected.model_dump(mode="json")
	assert res.headers["Cache-Control"] == "no-store"
	called_user, _ = mock_get_profile.call_args.args
	assert called_user.id == USER_ID
	app.dependency_overrides.clear()


def test_get_my_profile_jwt_mode_success(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	expected = _profile_response()
	monkeypatch.setattr(router_module.user_service, "get_profile", AsyncMock(return_value=expected))

	res = client.get("/api/users/me")

	assert res.status_code == 200
	assert res.json() == expected.model_dump(mode="json")


def test_get_my_profile_unauthenticated_returns_401(app_and_mocks: FastAPI) -> None:
	with _unauthenticated_client(app_and_mocks) as client:
		res = client.get("/api/users/me")

	assert res.status_code == 401
	assert res.json()["error"]["code"] == "UNAUTHENTICATED"


def test_get_my_profile_inactive_user_returns_403(app_and_mocks: FastAPI) -> None:
	with _inactive_user_client(app_and_mocks) as client:
		res = client.get("/api/users/me")

	assert res.status_code == 403
	assert res.json()["error"]["code"] == "USER_INACTIVE"


def test_get_my_profile_oauth_incomplete_profile_returns_false(
	client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
	expected = _profile_response(
		last_name=None,
		first_name=None,
		last_name_kana=None,
		first_name_kana=None,
		birth_date=None,
		profile_completed=False,
		has_password=False,
	)
	monkeypatch.setattr(router_module.user_service, "get_profile", AsyncMock(return_value=expected))

	res = client.get("/api/users/me")

	assert res.status_code == 200
	assert res.json()["profile_completed"] is False


# --- PATCH /api/users/me -----------------------------------------------------


def test_patch_my_profile_session_mode_success(monkeypatch: pytest.MonkeyPatch) -> None:
	app = _app_with_mode("session")
	monkeypatch.setattr(deps.redis_store, "get_csrf_token", AsyncMock(return_value="token-abc"))
	expected = _profile_response(last_name="鈴木")
	mock_update = AsyncMock(return_value=expected)
	monkeypatch.setattr(router_module.user_service, "update_profile", mock_update)

	with TestClient(app) as client:
		client.cookies.set("cerberus_sid", "sid-1")
		res = client.patch(
			"/api/users/me",
			json={"last_name": "鈴木"},
			headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": "token-abc"},
		)

	assert res.status_code == 200
	assert res.json()["last_name"] == "鈴木"
	assert res.headers["Cache-Control"] == "no-store"
	app.dependency_overrides.clear()


def test_patch_my_profile_jwt_mode_success(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	expected = _profile_response(last_name="鈴木")
	monkeypatch.setattr(router_module.user_service, "update_profile", AsyncMock(return_value=expected))

	res = client.patch("/api/users/me", json={"last_name": "鈴木"}, headers={"Origin": ALLOWED_ORIGIN})

	assert res.status_code == 200
	assert res.json()["last_name"] == "鈴木"


def test_patch_my_profile_csrf_missing_session_returns_403(monkeypatch: pytest.MonkeyPatch) -> None:
	app = _app_with_mode("session")
	mock_update = AsyncMock()
	monkeypatch.setattr(router_module.user_service, "update_profile", mock_update)

	with TestClient(app) as client:
		client.cookies.set("cerberus_sid", "sid-1")
		res = client.patch("/api/users/me", json={"last_name": "鈴木"}, headers={"Origin": ALLOWED_ORIGIN})

	assert res.status_code == 403
	assert res.json()["error"]["code"] == "CSRF_INVALID"
	mock_update.assert_not_called()
	app.dependency_overrides.clear()


def test_patch_my_profile_unauthenticated_returns_401(app_and_mocks: FastAPI) -> None:
	with _unauthenticated_client(app_and_mocks) as client:
		res = client.patch("/api/users/me", json={"last_name": "鈴木"}, headers={"Origin": ALLOWED_ORIGIN})

	assert res.status_code == 401
	assert res.json()["error"]["code"] == "UNAUTHENTICATED"


def test_patch_my_profile_inactive_user_returns_403(app_and_mocks: FastAPI) -> None:
	with _inactive_user_client(app_and_mocks) as client:
		res = client.patch("/api/users/me", json={"last_name": "鈴木"}, headers={"Origin": ALLOWED_ORIGIN})

	assert res.status_code == 403
	assert res.json()["error"]["code"] == "USER_INACTIVE"


def test_patch_my_profile_invalid_kana_returns_422(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	mock_update = AsyncMock()
	monkeypatch.setattr(router_module.user_service, "update_profile", mock_update)

	res = client.patch("/api/users/me", json={"last_name_kana": "山田"}, headers={"Origin": ALLOWED_ORIGIN})

	assert res.status_code == 422
	assert res.json()["error"]["code"] == "VALIDATION_ERROR"
	mock_update.assert_not_called()


def test_patch_my_profile_null_rejected_by_service_returns_422(
	client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
	"""送信済みフィールドのnull化不可(service層判定)がrouterで422として返ること。"""
	monkeypatch.setattr(
		router_module.user_service,
		"update_profile",
		AsyncMock(side_effect=ValidationError(details=[{"field": "last_name", "message": "null is not allowed"}])),
	)

	res = client.patch("/api/users/me", json={"last_name": "鈴木"}, headers={"Origin": ALLOWED_ORIGIN})

	assert res.status_code == 422
	assert res.json()["error"]["code"] == "VALIDATION_ERROR"


# --- PUT /api/users/me/password ----------------------------------------------


def _password_payload(**overrides: object) -> dict[str, object]:
	payload: dict[str, object] = {
		"current_password": "OldPass1!",
		"new_password": "NewPass1!",
		"password_confirm": "NewPass1!",
	}
	payload.update(overrides)
	return payload


def test_change_my_password_session_mode_success(monkeypatch: pytest.MonkeyPatch) -> None:
	app = _app_with_mode("session")
	monkeypatch.setattr(deps.redis_store, "get_csrf_token", AsyncMock(return_value="token-abc"))
	mock_change = AsyncMock(return_value=None)
	monkeypatch.setattr(router_module.user_service, "change_password", mock_change)

	with TestClient(app) as client:
		client.cookies.set("cerberus_sid", "sid-1")
		res = client.put(
			"/api/users/me/password",
			json=_password_payload(),
			headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": "token-abc"},
		)

	assert res.status_code == 204
	mock_change.assert_awaited_once()
	app.dependency_overrides.clear()


def test_change_my_password_jwt_mode_success(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(router_module.user_service, "change_password", AsyncMock(return_value=None))

	res = client.put("/api/users/me/password", json=_password_payload(), headers={"Origin": ALLOWED_ORIGIN})

	assert res.status_code == 204


def test_change_my_password_csrf_missing_session_returns_403(monkeypatch: pytest.MonkeyPatch) -> None:
	app = _app_with_mode("session")
	mock_change = AsyncMock()
	monkeypatch.setattr(router_module.user_service, "change_password", mock_change)

	with TestClient(app) as client:
		client.cookies.set("cerberus_sid", "sid-1")
		res = client.put("/api/users/me/password", json=_password_payload(), headers={"Origin": ALLOWED_ORIGIN})

	assert res.status_code == 403
	assert res.json()["error"]["code"] == "CSRF_INVALID"
	mock_change.assert_not_called()
	app.dependency_overrides.clear()


def test_change_my_password_unauthenticated_returns_401(app_and_mocks: FastAPI) -> None:
	with _unauthenticated_client(app_and_mocks) as client:
		res = client.put("/api/users/me/password", json=_password_payload(), headers={"Origin": ALLOWED_ORIGIN})

	assert res.status_code == 401
	assert res.json()["error"]["code"] == "UNAUTHENTICATED"


def test_change_my_password_inactive_user_returns_403(app_and_mocks: FastAPI) -> None:
	with _inactive_user_client(app_and_mocks) as client:
		res = client.put("/api/users/me/password", json=_password_payload(), headers={"Origin": ALLOWED_ORIGIN})

	assert res.status_code == 403
	assert res.json()["error"]["code"] == "USER_INACTIVE"


def test_change_my_password_policy_violation_returns_422(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	mock_change = AsyncMock()
	monkeypatch.setattr(router_module.user_service, "change_password", mock_change)

	res = client.put(
		"/api/users/me/password",
		json=_password_payload(new_password="weak", password_confirm="weak"),
		headers={"Origin": ALLOWED_ORIGIN},
	)

	assert res.status_code == 422
	assert res.json()["error"]["code"] == "VALIDATION_ERROR"
	mock_change.assert_not_called()


def test_change_my_password_wrong_current_password_returns_401(
	client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
	monkeypatch.setattr(
		router_module.user_service,
		"change_password",
		AsyncMock(side_effect=InvalidCredentialsError(message="現在のパスワードが正しくありません")),
	)

	res = client.put("/api/users/me/password", json=_password_payload(), headers={"Origin": ALLOWED_ORIGIN})

	assert res.status_code == 401
	assert res.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_change_my_password_missing_current_password_returns_422(
	client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
	"""has_password=trueなのにcurrent_password未送信(service層判定)が422として返ること。"""
	monkeypatch.setattr(
		router_module.user_service,
		"change_password",
		AsyncMock(side_effect=ValidationError(details=[{"field": "current_password", "message": "required"}])),
	)

	res = client.put(
		"/api/users/me/password",
		json=_password_payload(current_password=None),
		headers={"Origin": ALLOWED_ORIGIN},
	)

	assert res.status_code == 422
	assert res.json()["error"]["code"] == "VALIDATION_ERROR"


# --- GET /api/users/me/login-history -----------------------------------------


def test_get_my_login_history_session_mode_success(monkeypatch: pytest.MonkeyPatch) -> None:
	app = _app_with_mode("session")
	expected = LoginHistoryListResponse(items=[], meta=LoginHistoryMeta(limit=50, count=0))
	mock_get_history = AsyncMock(return_value=expected)
	monkeypatch.setattr(router_module.user_service, "get_login_history", mock_get_history)

	with TestClient(app) as client:
		res = client.get("/api/users/me/login-history")

	assert res.status_code == 200
	assert res.json() == expected.model_dump(mode="json")
	assert res.headers["Cache-Control"] == "no-store"
	app.dependency_overrides.clear()


def test_get_my_login_history_jwt_mode_success(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	expected = LoginHistoryListResponse(items=[], meta=LoginHistoryMeta(limit=50, count=0))
	monkeypatch.setattr(router_module.user_service, "get_login_history", AsyncMock(return_value=expected))

	res = client.get("/api/users/me/login-history")

	assert res.status_code == 200
	assert res.json() == expected.model_dump(mode="json")


def test_get_my_login_history_unauthenticated_returns_401(app_and_mocks: FastAPI) -> None:
	with _unauthenticated_client(app_and_mocks) as client:
		res = client.get("/api/users/me/login-history")

	assert res.status_code == 401
	assert res.json()["error"]["code"] == "UNAUTHENTICATED"


def test_get_my_login_history_inactive_user_returns_403(app_and_mocks: FastAPI) -> None:
	with _inactive_user_client(app_and_mocks) as client:
		res = client.get("/api/users/me/login-history")

	assert res.status_code == 403
	assert res.json()["error"]["code"] == "USER_INACTIVE"


def test_get_my_login_history_uses_configured_limit(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	expected = LoginHistoryListResponse(items=[], meta=LoginHistoryMeta(limit=50, count=0))
	mock_get_history = AsyncMock(return_value=expected)
	monkeypatch.setattr(router_module.user_service, "get_login_history", mock_get_history)

	client.get("/api/users/me/login-history")

	_, kwargs = mock_get_history.call_args
	assert kwargs["limit"] == 50
