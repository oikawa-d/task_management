"""auth_router（register/login/logout/me/config）のHTTP契約テスト。

app.mainの実アプリはDB/Redisに接続するため、auth_routerだけを載せた最小アプリを組み立て、
service層をモックしてrouterの責務（status・schema・Cookie・ヘッダ・エラー変換）のみを検証する。
参照設計書: docs/detailed_design/api/auth/01_post_auth_register.md〜05_get_auth_config.md
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from app.api.routers import auth_router as auth_router_module
from app.api.routers.auth_router import router
from app.auth.base import LoginResult
from app.auth.factory import get_auth_strategy
from app.core.config import get_backend_settings
from app.core.deps import get_current_user
from app.core.exceptions import (
	DuplicateUsernameError,
	EmailNotVerifiedError,
	InvalidCredentialsError,
	TooManyAttemptsError,
	register_error_handling,
)
from app.db import get_db_session
from app.schemas.user import UserProfileResponse
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

ALLOWED_ORIGIN = "http://localhost:5173"

_REGISTER_PAYLOAD = {
	"username": "taro",
	"email": "taro@example.com",
	"password": "Passw0rd!",
	"password_confirm": "Passw0rd!",
	"last_name": "山田",
	"first_name": "太郎",
	"last_name_kana": "ヤマダ",
	"first_name_kana": "タロウ",
	"birth_date": "1995-04-01",
}


class _StubStrategy:
	"""authenticateが常に未認証を返す最小Strategy。認証済みケースはget_current_userをoverrideする。"""

	def __init__(self, mode: str) -> None:
		self.mode = mode

	async def authenticate(self, _request: Any) -> None:
		return None


def _build_app(auth_mode: str = "session") -> FastAPI:
	app = FastAPI()
	register_error_handling(app)
	app.include_router(router)
	app.dependency_overrides[get_db_session] = lambda: SimpleNamespace()
	app.dependency_overrides[get_auth_strategy] = lambda: _StubStrategy(auth_mode)
	return app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
	monkeypatch.setenv("CORS_ALLOW_ORIGINS", ALLOWED_ORIGIN)
	get_backend_settings.cache_clear()
	app = _build_app()
	with TestClient(app) as test_client:
		yield test_client
	app.dependency_overrides.clear()


def test_auth_router_registers_all_endpoints() -> None:
	routes = {
		(route.path, method) for route in router.routes if isinstance(route, APIRoute) for method in route.methods
	}

	assert ("/api/auth/register", "POST") in routes
	assert ("/api/auth/login", "POST") in routes
	assert ("/api/auth/logout", "POST") in routes
	assert ("/api/auth/me", "GET") in routes
	assert ("/api/auth/config", "GET") in routes


def test_register_returns_201_without_auth_cookie(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	user_id = uuid4()

	async def _register(*_args: Any, **_kwargs: Any) -> SimpleNamespace:
		return SimpleNamespace(id=user_id, email="taro@example.com")

	monkeypatch.setattr(auth_router_module.auth_service, "register", _register)

	response = client.post("/api/auth/register", json=_REGISTER_PAYLOAD, headers={"Origin": ALLOWED_ORIGIN})

	assert response.status_code == 201
	assert response.json() == {
		"id": str(user_id),
		"email": "taro@example.com",
		"message": auth_router_module.REGISTER_ACCEPTED_MESSAGE,
	}
	assert "set-cookie" not in response.headers


def test_register_rejects_disallowed_origin(client: TestClient) -> None:
	response = client.post("/api/auth/register", json=_REGISTER_PAYLOAD, headers={"Origin": "http://evil.example"})

	assert response.status_code == 403
	assert response.json()["error"]["code"] == "CSRF_INVALID"


def test_register_duplicate_username_returns_409(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	async def _register(*_args: Any, **_kwargs: Any) -> SimpleNamespace:
		raise DuplicateUsernameError()

	monkeypatch.setattr(auth_router_module.auth_service, "register", _register)

	response = client.post("/api/auth/register", json=_REGISTER_PAYLOAD, headers={"Origin": ALLOWED_ORIGIN})

	assert response.status_code == 409
	assert response.json()["error"]["code"] == "DUPLICATE_USERNAME"


def test_register_validation_error_returns_422(client: TestClient) -> None:
	payload = {**_REGISTER_PAYLOAD, "password_confirm": "Different1!"}

	response = client.post("/api/auth/register", json=payload, headers={"Origin": ALLOWED_ORIGIN})

	assert response.status_code == 422
	assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_login_session_mode_returns_204_with_cookies(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setenv("CORS_ALLOW_ORIGINS", ALLOWED_ORIGIN)
	get_backend_settings.cache_clear()

	async def _login(_identifier: str, _password: str, _request: Any, response: Any, *_args: Any) -> LoginResult:
		response.set_cookie("cerberus_sid", "session-id")
		response.set_cookie("cerberus_csrf", "csrf-token")
		return LoginResult("session", csrf_token="csrf-token", expires_in=1800, session_id="session-id")

	monkeypatch.setattr(auth_router_module.auth_service, "login", _login)
	app = _build_app("session")
	with TestClient(app) as client:
		response = client.post(
			"/api/auth/login",
			json={"identifier": "taro", "password": "Passw0rd!"},
			headers={"Origin": ALLOWED_ORIGIN},
		)

	assert response.status_code == 204
	assert response.content == b""
	cookies = response.headers.get_list("set-cookie")
	assert any(cookie.startswith("cerberus_sid=") for cookie in cookies)
	assert any(cookie.startswith("cerberus_csrf=") for cookie in cookies)


def test_login_jwt_mode_returns_access_token(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setenv("CORS_ALLOW_ORIGINS", ALLOWED_ORIGIN)
	get_backend_settings.cache_clear()

	async def _login(*_args: Any, **_kwargs: Any) -> LoginResult:
		return LoginResult("jwt", "access-token", "refresh-token", "csrf-token", 900)

	monkeypatch.setattr(auth_router_module.auth_service, "login", _login)
	app = _build_app("jwt")
	with TestClient(app) as client:
		response = client.post(
			"/api/auth/login",
			json={"identifier": "taro", "password": "Passw0rd!"},
			headers={"Origin": ALLOWED_ORIGIN},
		)

	assert response.status_code == 200
	assert response.json() == {"access_token": "access-token", "token_type": "bearer", "expires_in": 900}
	assert "refresh-token" not in response.text


@pytest.mark.parametrize(
	("error", "status_code", "code"),
	[
		(InvalidCredentialsError(), 401, "INVALID_CREDENTIALS"),
		(EmailNotVerifiedError(), 403, "EMAIL_NOT_VERIFIED"),
		(TooManyAttemptsError(), 429, "TOO_MANY_ATTEMPTS"),
	],
)
def test_login_error_codes(
	client: TestClient, monkeypatch: pytest.MonkeyPatch, error: Exception, status_code: int, code: str
) -> None:
	async def _login(*_args: Any, **_kwargs: Any) -> LoginResult:
		raise error

	monkeypatch.setattr(auth_router_module.auth_service, "login", _login)

	response = client.post(
		"/api/auth/login",
		json={"identifier": "taro", "password": "Passw0rd!"},
		headers={"Origin": ALLOWED_ORIGIN},
	)

	assert response.status_code == status_code
	assert response.json()["error"]["code"] == code


def test_logout_without_cookie_returns_204(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	calls: list[str] = []

	async def _logout(*_args: Any, **_kwargs: Any) -> None:
		calls.append("logout")

	monkeypatch.setattr(auth_router_module.auth_service, "logout", _logout)

	response = client.post("/api/auth/logout", headers={"Origin": ALLOWED_ORIGIN})

	assert response.status_code == 204
	assert calls == ["logout"]


def test_logout_with_session_cookie_requires_csrf_header(client: TestClient) -> None:
	client.cookies.set("cerberus_sid", "session-id")

	response = client.post("/api/auth/logout", headers={"Origin": ALLOWED_ORIGIN})

	assert response.status_code == 403
	assert response.json()["error"]["code"] == "CSRF_INVALID"


def _profile() -> UserProfileResponse:
	return UserProfileResponse(
		id=uuid4(),
		username="taro",
		email="taro@example.com",
		last_name="山田",
		first_name="太郎",
		last_name_kana="ヤマダ",
		first_name_kana="タロウ",
		birth_date="1995-04-01",
		profile_completed=True,
		role="member",
		has_password=True,
		oauth_providers=["google"],
	)


def test_me_returns_profile_with_auth_mode(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setenv("AUTH_MODE", "jwt")
	get_backend_settings.cache_clear()
	profile = _profile()

	async def _get_profile(*_args: Any, **_kwargs: Any) -> UserProfileResponse:
		return profile

	monkeypatch.setattr(auth_router_module.user_service, "get_profile", _get_profile)
	app = _build_app("jwt")
	app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=profile.id)
	with TestClient(app) as client:
		response = client.get("/api/auth/me")

	assert response.status_code == 200
	body = response.json()
	assert body["auth_mode"] == "jwt"
	assert body["username"] == "taro"
	assert body["oauth_providers"] == ["google"]


def test_me_requires_authentication(client: TestClient) -> None:
	response = client.get("/api/auth/me")

	assert response.status_code == 401
	assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_config_returns_public_settings_without_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setenv("AUTH_MODE", "session")
	monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-client-id")
	monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "google-client-secret")
	get_backend_settings.cache_clear()
	app = _build_app()
	with TestClient(app) as client:
		response = client.get("/api/auth/config")

	assert response.status_code == 200
	assert response.json() == {
		"auth_mode": "session",
		"google_login_enabled": True,
		"csrf_cookie_name": "cerberus_csrf",
	}
	assert response.headers["cache-control"] == "no-store"
	assert "google-client-secret" not in response.text


def test_config_reports_google_login_disabled_when_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setenv("GOOGLE_CLIENT_ID", "")
	monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "")
	get_backend_settings.cache_clear()
	app = _build_app()
	with TestClient(app) as client:
		response = client.get("/api/auth/config")

	assert response.status_code == 200
	assert response.json()["google_login_enabled"] is False


def test_auth_endpoints_are_published_in_openapi() -> None:
	from app.main import app as main_app

	paths = main_app.openapi()["paths"]

	assert set(paths["/api/auth/register"]) == {"post"}
	assert set(paths["/api/auth/login"]) == {"post"}
	assert set(paths["/api/auth/logout"]) == {"post"}
	assert set(paths["/api/auth/me"]) == {"get"}
	assert set(paths["/api/auth/config"]) == {"get"}
