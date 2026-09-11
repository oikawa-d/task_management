"""oauth_router（認可開始・callback・exchange）のHTTP契約テスト。

service層はモックし、routerの責務（302のLocation・fragment・Cookie引き継ぎ・
例外からerrorクエリへの変換・モード別のstatus）のみを検証する。
参照設計書: docs/detailed_design/api/auth/11_get_auth_oauth_google.md〜13_post_auth_oauth_exchange.md
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from app.api.routers import oauth_router as oauth_router_module
from app.api.routers.oauth_router import router
from app.core.config import get_backend_settings
from app.core.exceptions import (
	InvalidStateError,
	OAuthEmailUnverifiedError,
	OAuthHandoffInvalidError,
	TooManyAttemptsError,
	register_error_handling,
)
from app.db import get_db_session
from app.schemas.oauth import OAuthCallbackResult, OAuthExchangeResponse, OAuthStartResult
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

ALLOWED_ORIGIN = "http://localhost:5173"
FRONTEND_BASE_URL = "http://localhost:5173"
AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth?client_id=x&state=state-value"


def _build_app() -> FastAPI:
	app = FastAPI()
	register_error_handling(app)
	app.include_router(router)
	app.dependency_overrides[get_db_session] = lambda: SimpleNamespace()
	return app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
	monkeypatch.setenv("CORS_ALLOW_ORIGINS", ALLOWED_ORIGIN)
	monkeypatch.setenv("FRONTEND_BASE_URL", FRONTEND_BASE_URL)
	monkeypatch.setenv("AUTH_MODE", "jwt")
	get_backend_settings.cache_clear()
	app = _build_app()
	with TestClient(app, follow_redirects=False) as test_client:
		yield test_client
	app.dependency_overrides.clear()


def test_oauth_router_registers_all_endpoints() -> None:
	routes = {
		(route.path, method) for route in router.routes if isinstance(route, APIRoute) for method in route.methods
	}

	assert ("/api/auth/oauth/google", "GET") in routes
	assert ("/api/auth/oauth/google/callback", "GET") in routes
	assert ("/api/auth/oauth/exchange", "POST") in routes


def test_start_redirects_to_google_with_state_cookie(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	captured: list[str | None] = []

	async def _oauth_start(redirect_to: str | None, _request: Any, response: Any) -> OAuthStartResult:
		captured.append(redirect_to)
		response.set_cookie("cerberus_oauth_state", "state-value")
		return OAuthStartResult(authorize_url=AUTHORIZE_URL, state="state-value")

	monkeypatch.setattr(oauth_router_module.auth_service, "oauth_start", _oauth_start)

	response = client.get("/api/auth/oauth/google", params={"redirect_to": "/projects"})

	assert response.status_code == 302
	assert response.headers["location"] == AUTHORIZE_URL
	assert any(cookie.startswith("cerberus_oauth_state=") for cookie in response.headers.get_list("set-cookie"))
	assert captured == ["/projects"]


def test_callback_session_mode_redirects_with_redirect_to_fragment(
	client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
	async def _oauth_callback(*_args: Any, **_kwargs: Any) -> OAuthCallbackResult:
		return OAuthCallbackResult(auth_mode="session", redirect_to="/dashboard")

	monkeypatch.setattr(oauth_router_module.auth_service, "oauth_callback", _oauth_callback)

	response = client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": "state-value"})

	assert response.status_code == 302
	assert response.headers["location"] == f"{FRONTEND_BASE_URL}/oauth/callback#redirect_to=/dashboard"


def test_callback_jwt_mode_includes_handoff_code_in_fragment(
	client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
	async def _oauth_callback(*_args: Any, **_kwargs: Any) -> OAuthCallbackResult:
		return OAuthCallbackResult(auth_mode="jwt", redirect_to="/dashboard", handoff_code="handoff-code")

	monkeypatch.setattr(oauth_router_module.auth_service, "oauth_callback", _oauth_callback)

	response = client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": "state-value"})

	location = response.headers["location"]
	assert location.startswith(f"{FRONTEND_BASE_URL}/oauth/callback#")
	fragment = location.split("#", 1)[1]
	assert fragment == "code=handoff-code&redirect_to=/dashboard"


def test_callback_with_google_error_redirects_to_login(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	called: list[str] = []

	async def _oauth_callback(*_args: Any, **_kwargs: Any) -> OAuthCallbackResult:
		called.append("service")
		raise AssertionError("errorクエリがある場合はserviceを呼ばない")

	monkeypatch.setattr(oauth_router_module.auth_service, "oauth_callback", _oauth_callback)

	response = client.get("/api/auth/oauth/google/callback", params={"error": "access_denied"})

	assert response.status_code == 302
	assert response.headers["location"] == f"{FRONTEND_BASE_URL}/login?error=oauth_denied"
	assert called == []


@pytest.mark.parametrize(
	("error", "expected"),
	[
		(InvalidStateError(), "invalid_state"),
		(OAuthEmailUnverifiedError(), "oauth_email_unverified"),
		(TooManyAttemptsError(), "too_many_attempts"),
		(RuntimeError("redis down"), "oauth_failed"),
	],
)
def test_callback_maps_exception_to_login_error(
	client: TestClient, monkeypatch: pytest.MonkeyPatch, error: Exception, expected: str
) -> None:
	async def _oauth_callback(*_args: Any, **_kwargs: Any) -> OAuthCallbackResult:
		raise error

	monkeypatch.setattr(oauth_router_module.auth_service, "oauth_callback", _oauth_callback)

	response = client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": "state-value"})

	assert response.status_code == 302
	assert response.headers["location"] == f"{FRONTEND_BASE_URL}/login?error={expected}"
	# 失敗の詳細（例外メッセージ等）はブラウザへ返さない。
	assert "redis down" not in response.headers["location"]


def test_exchange_returns_tokens_in_jwt_mode(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	async def _oauth_exchange(*_args: Any, **_kwargs: Any) -> OAuthExchangeResponse:
		return OAuthExchangeResponse(
			access_token="access-token", token_type="bearer", expires_in=900, redirect_to="/dashboard"
		)

	monkeypatch.setattr(oauth_router_module.auth_service, "oauth_exchange", _oauth_exchange)

	response = client.post(
		"/api/auth/oauth/exchange", json={"code": "handoff-code"}, headers={"Origin": ALLOWED_ORIGIN}
	)

	assert response.status_code == 200
	assert response.json() == {
		"access_token": "access-token",
		"token_type": "bearer",
		"expires_in": 900,
		"redirect_to": "/dashboard",
	}


def test_exchange_in_session_mode_returns_405(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setenv("CORS_ALLOW_ORIGINS", ALLOWED_ORIGIN)
	monkeypatch.setenv("AUTH_MODE", "session")
	get_backend_settings.cache_clear()
	called: list[str] = []

	async def _oauth_exchange(*_args: Any, **_kwargs: Any) -> OAuthExchangeResponse:
		called.append("service")
		raise AssertionError("sessionモードではserviceを呼ばない")

	monkeypatch.setattr(oauth_router_module.auth_service, "oauth_exchange", _oauth_exchange)
	app = _build_app()
	with TestClient(app, follow_redirects=False) as test_client:
		response = test_client.post(
			"/api/auth/oauth/exchange", json={"code": "handoff-code"}, headers={"Origin": ALLOWED_ORIGIN}
		)

	assert response.status_code == 405
	assert response.json()["error"]["code"] == "NOT_SUPPORTED_IN_MODE"
	assert called == []


def test_exchange_rejects_disallowed_origin(client: TestClient) -> None:
	response = client.post(
		"/api/auth/oauth/exchange", json={"code": "handoff-code"}, headers={"Origin": "http://evil.example"}
	)

	assert response.status_code == 403
	assert response.json()["error"]["code"] == "CSRF_INVALID"


def test_exchange_invalid_handoff_code_returns_400(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	async def _oauth_exchange(*_args: Any, **_kwargs: Any) -> OAuthExchangeResponse:
		raise OAuthHandoffInvalidError()

	monkeypatch.setattr(oauth_router_module.auth_service, "oauth_exchange", _oauth_exchange)

	response = client.post(
		"/api/auth/oauth/exchange", json={"code": "expired-code"}, headers={"Origin": ALLOWED_ORIGIN}
	)

	assert response.status_code == 400
	assert response.json()["error"]["code"] == "OAUTH_HANDOFF_INVALID"


def test_exchange_rejects_empty_code(client: TestClient) -> None:
	response = client.post("/api/auth/oauth/exchange", json={"code": ""}, headers={"Origin": ALLOWED_ORIGIN})

	assert response.status_code == 422
	assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_oauth_endpoints_are_published_in_openapi() -> None:
	from app.main import app as main_app

	paths = main_app.openapi()["paths"]

	assert set(paths["/api/auth/oauth/google"]) == {"get"}
	assert set(paths["/api/auth/oauth/google/callback"]) == {"get"}
	assert set(paths["/api/auth/oauth/exchange"]) == {"post"}
