"""oauth_router（認可開始・callback・exchange）のHTTP契約テスト。

service層はモックし、routerの責務（302のLocation・fragment・Cookie引き継ぎ・
例外からerrorクエリへの変換・モード別のstatus）のみを検証する。
参照設計書: docs/detailed_design/api/auth/11_get_auth_oauth_google.md〜13_post_auth_oauth_exchange.md
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.api.routers import oauth_router as oauth_router_module
from app.api.routers.oauth_router import router
from app.auth.base import LoginResult
from app.auth.oauth import GoogleUserInfo, IdTokenClaims, OAuthTokenResponse
from app.core.config import get_backend_settings
from app.core.exceptions import (
	InvalidStateError,
	OAuthEmailUnverifiedError,
	OAuthHandoffInvalidError,
	TooManyAttemptsError,
	register_error_handling,
)
from app.db import get_db_session
from app.repository.redis_store_common import OAuthHandoffData, OAuthStateData
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


@pytest.fixture
def session_client(monkeypatch: pytest.MonkeyPatch):
	monkeypatch.setenv("CORS_ALLOW_ORIGINS", ALLOWED_ORIGIN)
	monkeypatch.setenv("FRONTEND_BASE_URL", FRONTEND_BASE_URL)
	monkeypatch.setenv("AUTH_MODE", "session")
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
	session_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
	async def _oauth_callback(*_args: Any, **_kwargs: Any) -> OAuthCallbackResult:
		_args[4].set_cookie("cerberus_sid", "session-id")
		_args[4].set_cookie("cerberus_csrf", "csrf-token")
		_args[4].set_cookie("cerberus_oauth_state", "", max_age=0)
		return OAuthCallbackResult(auth_mode="session", redirect_to="/dashboard")

	monkeypatch.setattr(oauth_router_module.auth_service, "oauth_callback", _oauth_callback)

	response = session_client.get(
		"/api/auth/oauth/google/callback", params={"code": "auth-code", "state": "state-value"}
	)

	assert response.status_code == 302
	assert response.headers["location"] == f"{FRONTEND_BASE_URL}/oauth/callback#redirect_to=/dashboard"
	set_cookie = response.headers.get_list("set-cookie")
	assert any(value.startswith("cerberus_sid=session-id") for value in set_cookie)
	assert any(value.startswith("cerberus_csrf=csrf-token") for value in set_cookie)
	assert any(value.startswith("cerberus_oauth_state=") and "Max-Age=0" in value for value in set_cookie)


def test_callback_session_route_establishes_authentication(
	session_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
	user_id = uuid4()
	state = OAuthStateData("/dashboard", "verifier", "nonce", None)
	user = SimpleNamespace(id=user_id, email="alice@example.com", is_active=True)

	class _Provider:
		async def exchange_code(self, _code: str, _verifier: str) -> OAuthTokenResponse:
			return OAuthTokenResponse(id_token="id-token", access_token="access-token")

		async def verify_id_token(self, _token: str, _nonce: str) -> IdTokenClaims:
			return IdTokenClaims("google-sub", "alice@example.com", True, "Alice", None)

		async def fetch_userinfo(self, _access_token: str) -> GoogleUserInfo:
			return GoogleUserInfo("google-sub", "alice@example.com", True, "Alice", None)

	class _SessionStrategy:
		async def login(self, _user: Any, _request: Any, response: Any) -> LoginResult:
			response.set_cookie("cerberus_sid", "session-id")
			response.set_cookie("cerberus_csrf", "csrf-token")
			return LoginResult(auth_mode="session", session_id="session-id")

	monkeypatch.setattr(
		oauth_router_module.auth_service.redis_store, "consume_oauth_state", AsyncMock(return_value=state)
	)
	monkeypatch.setattr(oauth_router_module.auth_service.redis_store, "check_rate_limit", AsyncMock(return_value=1))
	monkeypatch.setattr(oauth_router_module.auth_service, "GoogleOAuthProvider", lambda _settings: _Provider())
	monkeypatch.setattr(oauth_router_module.auth_service, "_resolve_or_create_user", AsyncMock(return_value=user))
	monkeypatch.setattr(
		oauth_router_module.auth_service, "_auth_strategy", lambda _settings, _strategy: _SessionStrategy()
	)
	monkeypatch.setattr(oauth_router_module.auth_service, "_record_oauth_login", AsyncMock())

	session_client.cookies.set("cerberus_oauth_state", "state-value")

	response = session_client.get(
		"/api/auth/oauth/google/callback", params={"code": "auth-code", "state": "state-value"}
	)

	assert response.status_code == 302
	assert response.headers["location"] == f"{FRONTEND_BASE_URL}/oauth/callback#redirect_to=/dashboard"
	set_cookie = response.headers.get_list("set-cookie")
	assert any(value.startswith("cerberus_sid=session-id") for value in set_cookie)
	assert any(value.startswith("cerberus_csrf=csrf-token") for value in set_cookie)
	assert any("cerberus_oauth_state=" in value and "Max-Age=0" in value for value in set_cookie)


def test_exchange_route_establishes_jwt_authentication(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	user_id = uuid4()
	user = SimpleNamespace(id=user_id, email="alice@example.com", is_active=True)
	handoff = OAuthHandoffData(user_id, "/dashboard", None)

	class _JwtStrategy:
		async def login(self, _user: Any, _request: Any, response: Any) -> LoginResult:
			response.set_cookie("cerberus_rt", "refresh-token", httponly=True, path="/api/auth")
			response.set_cookie("cerberus_csrf", "csrf-token", path="/")
			return LoginResult(
				auth_mode="jwt",
				access_token="access-token",
				refresh_token="refresh-token",
				csrf_token="csrf-token",
				expires_in=900,
			)

	monkeypatch.setattr(
		oauth_router_module.auth_service.redis_store, "consume_oauth_handoff", AsyncMock(return_value=handoff)
	)
	monkeypatch.setattr(oauth_router_module.auth_service.redis_store, "check_rate_limit", AsyncMock(return_value=1))
	monkeypatch.setattr(oauth_router_module.auth_service.user_repository, "get_by_id", AsyncMock(return_value=user))
	monkeypatch.setattr(oauth_router_module.auth_service, "_auth_strategy", lambda _settings, _strategy: _JwtStrategy())
	monkeypatch.setattr(oauth_router_module.auth_service, "_record_oauth_login", AsyncMock())

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
	assert response.headers["cache-control"] == "no-store"
	set_cookie = response.headers.get_list("set-cookie")
	assert any(value.startswith("cerberus_rt=refresh-token") for value in set_cookie)
	assert any(value.startswith("cerberus_csrf=csrf-token") for value in set_cookie)


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
	called: list[tuple[Any, ...]] = []

	async def _oauth_callback_denied(*args: Any, **_kwargs: Any) -> None:
		called.append(args)
		args[3].set_cookie("cerberus_oauth_state", "", max_age=0)

	monkeypatch.setattr(oauth_router_module.auth_service, "oauth_callback_denied", _oauth_callback_denied)
	client.cookies.set("cerberus_oauth_state", "state-value")

	response = client.get("/api/auth/oauth/google/callback", params={"error": "access_denied", "state": "state-value"})

	assert response.status_code == 302
	assert response.headers["location"] == f"{FRONTEND_BASE_URL}/login?error=oauth_denied"
	assert len(called) == 1
	assert called[0][0:2] == ("state-value", "state-value")
	assert any("Max-Age=0" in value for value in response.headers.get_list("set-cookie"))


def test_callback_rejects_inconsistent_auth_mode_result(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	async def _oauth_callback(*_args: Any, **_kwargs: Any) -> OAuthCallbackResult:
		return OAuthCallbackResult(auth_mode="session", redirect_to="/dashboard", handoff_code="unexpected")

	monkeypatch.setattr(oauth_router_module.auth_service, "oauth_callback", _oauth_callback)

	response = client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": "state-value"})

	assert response.status_code == 302
	assert response.headers["location"] == f"{FRONTEND_BASE_URL}/login?error=oauth_failed"


def test_callback_rejects_result_mode_different_from_settings(
	client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
	async def _oauth_callback(*_args: Any, **_kwargs: Any) -> OAuthCallbackResult:
		return OAuthCallbackResult(auth_mode="session", redirect_to="/dashboard")

	monkeypatch.setattr(oauth_router_module.auth_service, "oauth_callback", _oauth_callback)

	response = client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": "state-value"})

	assert response.status_code == 302
	assert response.headers["location"] == f"{FRONTEND_BASE_URL}/login?error=oauth_failed"


def test_callback_rejects_jwt_result_without_handoff(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	async def _oauth_callback(*_args: Any, **_kwargs: Any) -> OAuthCallbackResult:
		return OAuthCallbackResult(auth_mode="jwt", redirect_to="/dashboard")

	monkeypatch.setattr(oauth_router_module.auth_service, "oauth_callback", _oauth_callback)

	response = client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": "state-value"})

	assert response.status_code == 302
	assert response.headers["location"] == f"{FRONTEND_BASE_URL}/login?error=oauth_failed"


def test_callback_denied_route_consumes_state_and_deletes_cookie(
	client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
	monkeypatch.setattr(oauth_router_module.auth_service.redis_store, "check_rate_limit", AsyncMock(return_value=1))
	monkeypatch.setattr(
		oauth_router_module.auth_service.redis_store,
		"consume_oauth_state",
		AsyncMock(return_value=OAuthStateData("/dashboard", "verifier", "nonce", None)),
	)
	client.cookies.set("cerberus_oauth_state", "state-value")

	response = client.get("/api/auth/oauth/google/callback", params={"error": "access_denied", "state": "state-value"})

	assert response.status_code == 302
	assert response.headers["location"] == f"{FRONTEND_BASE_URL}/login?error=oauth_denied"
	assert any(
		"cerberus_oauth_state=" in value and "Max-Age=0" in value for value in response.headers.get_list("set-cookie")
	)


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
		_args[2].set_cookie("cerberus_rt", "refresh-token", httponly=True, path="/api/auth")
		_args[2].set_cookie("cerberus_csrf", "csrf-token", path="/")
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
	assert response.headers["cache-control"] == "no-store"
	assert any(value.startswith("cerberus_rt=refresh-token") for value in response.headers.get_list("set-cookie"))
	assert any(value.startswith("cerberus_csrf=csrf-token") for value in response.headers.get_list("set-cookie"))


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
