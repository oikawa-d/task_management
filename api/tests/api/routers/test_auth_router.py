from inspect import signature
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.api.routers import auth_router
from app.auth.base import LoginResult
from app.core.config import BackendSettings
from app.core.exceptions import InvalidStateError
from app.schemas.auth import (
	AuthConfigResponse,
	LoginRequest,
	LoginResponse,
	MeResponse,
	RegisterRequest,
	RegisterResponse,
)
from app.schemas.oauth import OAuthCallbackResult, OAuthExchangeResponse, OAuthStartResult
from fastapi import Response
from fastapi.routing import APIRoute


def _settings(**overrides: object) -> BackendSettings:
	values: dict[str, object] = {
		"database_url": "postgresql+asyncpg://test:test@localhost/test",
		"jwt_secret_key": "secret",
		"google_client_id": "client-id",
		"google_client_secret": "client-secret",
		"initial_admin_email": "admin@example.com",
		"initial_admin_username": "admin",
		"initial_admin_password": "Password1!",
	}
	values.update(overrides)
	return BackendSettings(**values)


def _routes() -> dict[tuple[str, str], APIRoute]:
	return {
		(route.path, method): route
		for route in auth_router.router.routes
		if isinstance(route, APIRoute)
		for method in route.methods
	}


def test_auth_router_registers_all_api_endpoints() -> None:
	routes = _routes()
	expected = {
		("/api/auth/register", "POST"),
		("/api/auth/login", "POST"),
		("/api/auth/logout", "POST"),
		("/api/auth/me", "GET"),
		("/api/auth/config", "GET"),
		("/api/auth/refresh", "POST"),
		("/api/auth/verify-email", "POST"),
		("/api/auth/verify-email/resend", "POST"),
		("/api/auth/password/forgot", "POST"),
		("/api/auth/password/reset", "POST"),
		("/api/auth/oauth/google", "GET"),
		("/api/auth/oauth/google/callback", "GET"),
		("/api/auth/oauth/exchange", "POST"),
	}

	assert expected <= set(routes)


@pytest.mark.asyncio
async def test_register_forwards_request_and_returns_contract(monkeypatch: pytest.MonkeyPatch) -> None:
	request = auth_router.Request({"type": "http", "method": "POST", "path": "/api/auth/register"})
	payload = RegisterRequest(
		username="taro",
		email="taro@example.com",
		password="Password1!",
		password_confirm="Password1!",
		last_name="太郎",
		first_name="太郎",
		last_name_kana="タロウ",
		first_name_kana="タロウ",
		birth_date="1990-01-01",
	)
	user = type("User", (), {"id": uuid4(), "email": payload.email})()
	service = AsyncMock(return_value=user)
	monkeypatch.setattr(auth_router.auth_service, "register", service)

	result = await auth_router.register(payload, auth_router.BackgroundTasks(), request, AsyncMock())

	assert result == RegisterResponse(id=user.id, email=payload.email, message=auth_router.REGISTER_MESSAGE)
	service.assert_awaited_once()
	assert service.await_args.args[0] is payload


@pytest.mark.asyncio
async def test_login_session_preserves_strategy_cookies_and_returns_204(monkeypatch: pytest.MonkeyPatch) -> None:
	response = Response()
	strategy = object()
	login = AsyncMock(return_value=LoginResult("session", csrf_token="csrf", expires_in=1800, session_id="sid"))
	monkeypatch.setattr(auth_router.auth_service, "login", login)

	result = await auth_router.login(
		LoginRequest(identifier="taro", password="Password1!"),
		auth_router.Request({"type": "http", "method": "POST", "path": "/api/auth/login"}),
		response,
		AsyncMock(),
		strategy,
	)

	assert result is response
	assert response.status_code == 204
	login.assert_awaited_once()


@pytest.mark.asyncio
async def test_login_jwt_maps_token_result(monkeypatch: pytest.MonkeyPatch) -> None:
	login = AsyncMock(return_value=LoginResult("jwt", access_token="access", expires_in=900))
	monkeypatch.setattr(auth_router.auth_service, "login", login)

	result = await auth_router.login(
		LoginRequest(identifier="taro", password="Password1!"),
		auth_router.Request({"type": "http", "method": "POST", "path": "/api/auth/login"}),
		Response(),
		AsyncMock(),
		object(),
	)

	assert result == LoginResponse(access_token="access", token_type="bearer", expires_in=900)


@pytest.mark.asyncio
async def test_refresh_maps_strategy_result_and_sets_no_store(monkeypatch: pytest.MonkeyPatch) -> None:
	refresh = AsyncMock(return_value=LoginResult("jwt", access_token="access", expires_in=900))
	strategy = type("Strategy", (), {"refresh": refresh})()
	response = Response()

	result = await auth_router.refresh(
		auth_router.Request({"type": "http", "method": "POST", "path": "/api/auth/refresh"}),
		response,
		strategy,
	)

	assert result.access_token == "access"
	assert response.headers["cache-control"] == "no-store"
	refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_oauth_start_returns_redirect_and_preserves_state_cookie(monkeypatch: pytest.MonkeyPatch) -> None:
	start = AsyncMock(return_value=OAuthStartResult(authorize_url="https://accounts.google.test/auth", state="state"))
	monkeypatch.setattr(auth_router.auth_service, "oauth_start", start)
	response = Response()

	result = await auth_router.oauth_google_start(
		redirect_to="/dashboard",
		request=auth_router.Request({"type": "http", "method": "GET", "path": "/api/auth/oauth/google"}),
		response=response,
	)

	assert result is response
	assert response.status_code == 302
	assert response.headers["location"] == "https://accounts.google.test/auth"
	start.assert_awaited_once()


@pytest.mark.asyncio
async def test_oauth_callback_maps_success_to_frontend_fragment(monkeypatch: pytest.MonkeyPatch) -> None:
	callback = AsyncMock(
		return_value=OAuthCallbackResult(auth_mode="jwt", redirect_to="/dashboard", handoff_code="handoff")
	)
	monkeypatch.setattr(auth_router.auth_service, "oauth_callback", callback)
	settings = _settings(frontend_base_url="https://frontend.example")
	request = auth_router.Request(
		{"type": "http", "method": "GET", "path": "/api/auth/oauth/google/callback", "headers": []}
	)
	response = Response()

	result = await auth_router.oauth_google_callback(
		request=request,
		response=response,
		db=AsyncMock(),
		settings=settings,
		code="code",
		state="state",
		error=None,
	)

	assert result is response
	assert response.status_code == 302
	assert (
		response.headers["location"] == "https://frontend.example/oauth/callback#code=handoff&redirect_to=%2Fdashboard"
	)


@pytest.mark.asyncio
async def test_oauth_callback_logs_warning_on_unexpected_exception(
	monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
	callback = AsyncMock(side_effect=InvalidStateError())
	monkeypatch.setattr(auth_router.auth_service, "oauth_callback", callback)
	settings = _settings(frontend_base_url="https://frontend.example")
	request = auth_router.Request(
		{"type": "http", "method": "GET", "path": "/api/auth/oauth/google/callback", "headers": []}
	)
	response = Response()

	with caplog.at_level("WARNING", logger="app.oauth"):
		result = await auth_router.oauth_google_callback(
			request=request,
			response=response,
			db=AsyncMock(),
			settings=settings,
			code="code",
			state="state",
			error=None,
		)

	assert result is response
	assert response.status_code == 302
	assert response.headers["location"] == "https://frontend.example/login?error=invalid_state"
	warning_records = [record for record in caplog.records if record.levelname == "WARNING"]
	assert len(warning_records) == 1
	assert warning_records[0].failure_reason == "InvalidStateError"
	assert warning_records[0].event == "oauth_callback_failed"


def test_route_response_models_cover_contracts() -> None:
	routes = _routes()
	assert routes[("/api/auth/config", "GET")].response_model is AuthConfigResponse
	assert routes[("/api/auth/me", "GET")].response_model is MeResponse
	assert routes[("/api/auth/oauth/exchange", "POST")].response_model is OAuthExchangeResponse
	assert routes[("/api/auth/register", "POST")].response_model is RegisterResponse


def test_oauth_google_callback_query_params_default_to_none() -> None:
	params = signature(auth_router.oauth_google_callback).parameters
	assert params["code"].default.default is None
	assert params["state"].default.default is None
	assert params["error"].default.default is None
