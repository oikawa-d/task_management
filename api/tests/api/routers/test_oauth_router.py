"""oauth_router（認可開始・callback・exchange）のHTTP契約テスト。

service層はモックし、routerの責務（302のLocation・fragment・Cookie引き継ぎ・
例外からerrorクエリへの変換・モード別のstatus）のみを検証する。
参照設計書: docs/detailed_design/api/auth/11_get_auth_oauth_google.md〜13_post_auth_oauth_exchange.md
"""

from __future__ import annotations

import json
import logging
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
	ServiceUnavailableError,
	TooManyAttemptsError,
	register_error_handling,
)
from app.core.logger import JsonFormatter
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
	"""oauth_routerのみを組み込み、DBセッションをダミーに差し替えたFastAPIアプリを組み立てる。

	Returns:
		get_db_sessionの依存関係をオーバーライド済みのFastAPIアプリ。
	"""
	app = FastAPI()
	register_error_handling(app)
	app.include_router(router)
	app.dependency_overrides[get_db_session] = lambda: SimpleNamespace()
	return app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
	"""認証モードjwt・許可オリジン・フロントエンドURLを固定した_build_appのアプリを、
	リダイレクトを自動追跡しない(follow_redirects=False)TestClientで提供する。
	後片付けとしてdependency_overridesをクリアする。
	"""
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
	"""認証モードsessionに固定した以外はclient fixtureと同様のTestClientを提供する。
	後片付けとしてdependency_overridesをクリアする。
	"""
	monkeypatch.setenv("CORS_ALLOW_ORIGINS", ALLOWED_ORIGIN)
	monkeypatch.setenv("FRONTEND_BASE_URL", FRONTEND_BASE_URL)
	monkeypatch.setenv("AUTH_MODE", "session")
	get_backend_settings.cache_clear()
	app = _build_app()
	with TestClient(app, follow_redirects=False) as test_client:
		yield test_client
	app.dependency_overrides.clear()


def test_oauth_router_registers_all_endpoints() -> None:
	"""oauth_routerが、認可開始(GET /google)・callback(GET /google/callback)・
	exchange(POST /exchange)の3エンドポイントをすべて登録していることを検証する。
	"""
	routes = {
		(route.path, method) for route in router.routes if isinstance(route, APIRoute) for method in route.methods
	}

	assert ("/api/auth/oauth/google", "GET") in routes
	assert ("/api/auth/oauth/google/callback", "GET") in routes
	assert ("/api/auth/oauth/exchange", "POST") in routes


def test_google_login_enabled_uses_auth_service_module(monkeypatch: pytest.MonkeyPatch) -> None:
	"""_is_google_login_enabledが、実装の重複を避けてauth_service.get_auth_configの
	google_login_enabled判定をそのまま利用していることを検証する。
	"""
	settings = SimpleNamespace()
	monkeypatch.setattr(
		oauth_router_module.auth_service,
		"get_auth_config",
		lambda _settings: SimpleNamespace(google_login_enabled=True),
	)

	assert oauth_router_module._is_google_login_enabled(settings) is True


def test_start_redirects_to_google_with_state_cookie(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	"""GET /api/auth/oauth/google が、service層の発行したGoogle認可URLへステータス302で
	リダイレクトし、state検証用Cookieを設定し、redirect_toクエリをservice層へ渡すことを検証する。
	"""
	captured: list[str | None] = []

	async def _oauth_start(redirect_to: str | None, _request: Any, response: Any) -> OAuthStartResult:
		"""oauth_service.oauth_startの差し替え先。redirect_toを記録しつつstate Cookieを設定する。"""
		captured.append(redirect_to)
		response.set_cookie("cerberus_oauth_state", "state-value")
		return OAuthStartResult(authorize_url=AUTHORIZE_URL, state="state-value")

	monkeypatch.setattr(oauth_router_module.oauth_service, "oauth_start", _oauth_start)

	response = client.get("/api/auth/oauth/google", params={"redirect_to": "/projects"})

	assert response.status_code == 302
	assert response.headers["location"] == AUTHORIZE_URL
	assert any(cookie.startswith("cerberus_oauth_state=") for cookie in response.headers.get_list("set-cookie"))
	assert captured == ["/projects"]


def test_start_rate_limited_returns_positive_retry_after(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	"""service層のoauth_startがTooManyAttemptsErrorを送出した場合、ステータス429・
	エラーコードTOO_MANY_ATTEMPTSで応答し、Retry-Afterヘッダーに正の秒数が設定されることを検証する。
	"""

	async def _oauth_start(*_args: Any, **_kwargs: Any) -> OAuthStartResult:
		raise TooManyAttemptsError(retry_after=42)

	monkeypatch.setattr(oauth_router_module.oauth_service, "oauth_start", _oauth_start)

	response = client.get("/api/auth/oauth/google")

	assert response.status_code == 429
	assert response.json()["error"]["code"] == "TOO_MANY_ATTEMPTS"
	assert response.headers["Retry-After"] == "42"
	assert int(response.headers["Retry-After"]) > 0


def test_start_returns_oauth_disabled_when_google_login_is_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
	"""GOOGLE_LOGIN_ENABLED=falseの場合、service層のoauth_startを呼び出す前にステータス404・
	エラーコードOAUTH_DISABLEDで応答することを検証する。
	"""
	monkeypatch.setenv("CORS_ALLOW_ORIGINS", ALLOWED_ORIGIN)
	monkeypatch.setenv("GOOGLE_LOGIN_ENABLED", "false")
	get_backend_settings.cache_clear()
	called: list[str] = []

	async def _oauth_start(*_args: Any, **_kwargs: Any) -> OAuthStartResult:
		called.append("service")
		raise AssertionError("無効時はserviceを呼ばない")

	monkeypatch.setattr(oauth_router_module.oauth_service, "oauth_start", _oauth_start)
	app = _build_app()
	with TestClient(app, follow_redirects=False) as test_client:
		response = test_client.get("/api/auth/oauth/google")

	assert response.status_code == 404
	assert response.json()["error"]["code"] == "OAUTH_DISABLED"
	assert called == []


def test_callback_session_mode_redirects_with_redirect_to_fragment(
	session_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
	"""sessionモードのcallbackが成功した場合、フロントエンドのcallbackページへ
	redirect_toをURLフラグメントに含めてステータス302でリダイレクトし、
	セッション/CSRF Cookieを設定しつつoauth state Cookieを削除(Max-Age=0)することを検証する。
	"""

	async def _oauth_callback(*_args: Any, **_kwargs: Any) -> OAuthCallbackResult:
		"""oauth_service.oauth_callbackの差し替え先。セッション系Cookieを設定し固定の成功結果を返す。"""
		_args[4].set_cookie("cerberus_sid", "session-id")
		_args[4].set_cookie("cerberus_csrf", "csrf-token")
		_args[4].set_cookie("cerberus_oauth_state", "", max_age=0)
		return OAuthCallbackResult(auth_mode="session", redirect_to="/dashboard")

	monkeypatch.setattr(oauth_router_module.oauth_service, "oauth_callback", _oauth_callback)

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
	"""oauth_service内部の各コンポーネント（Redisのstate消費・Google認可コード交換・IDトークン検証・
	ユーザー解決・SessionAuthStrategy.login）を実際にservice層の実装コードパスで通し、
	callbackがステータス302でダッシュボードへリダイレクトし、セッション/CSRF Cookieを設定しつつ
	oauth state Cookieを削除することを検証する結合的なテスト。
	"""
	user_id = uuid4()
	state = OAuthStateData("/dashboard", "verifier", "nonce", None)
	user = SimpleNamespace(id=user_id, email="alice@example.com", is_active=True)

	class _Provider:
		"""GoogleOAuthProviderの差し替え先。認可コード交換・IDトークン検証・ユーザー情報取得を固定値で模擬する。"""

		async def exchange_code(self, _code: str, _verifier: str) -> OAuthTokenResponse:
			return OAuthTokenResponse(id_token="id-token", access_token="access-token")

		async def verify_id_token(self, _token: str, _nonce: str) -> IdTokenClaims:
			return IdTokenClaims("google-sub", "alice@example.com", True, "Alice", None)

		async def fetch_userinfo(self, _access_token: str) -> GoogleUserInfo:
			return GoogleUserInfo("google-sub", "alice@example.com", True, "Alice", None)

	class _SessionStrategy:
		"""SessionAuthStrategyの差し替え先。ログイン時にセッション/CSRF Cookieを設定し固定の結果を返す。"""

		async def login(self, _user: Any, _request: Any, response: Any) -> LoginResult:
			response.set_cookie("cerberus_sid", "session-id")
			response.set_cookie("cerberus_csrf", "csrf-token")
			return LoginResult(auth_mode="session", session_id="session-id")

	monkeypatch.setattr(
		oauth_router_module.oauth_service.redis_store, "consume_oauth_state", AsyncMock(return_value=state)
	)
	monkeypatch.setattr(oauth_router_module.oauth_service.redis_store, "check_rate_limit", AsyncMock(return_value=1))
	monkeypatch.setattr(oauth_router_module.oauth_service, "GoogleOAuthProvider", lambda _settings: _Provider())
	monkeypatch.setattr(oauth_router_module.oauth_service, "_resolve_or_create_user", AsyncMock(return_value=user))
	monkeypatch.setattr(
		oauth_router_module.oauth_service, "_auth_strategy", lambda _settings, _strategy: _SessionStrategy()
	)
	monkeypatch.setattr(oauth_router_module.oauth_service, "_record_oauth_login", AsyncMock())

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
	"""oauth_service内部の各コンポーネント（Redisのhandoffコード消費・ユーザー取得・
	JwtAuthStrategy.login）を実際のservice層の実装コードパスで通し、exchangeがステータス200で
	アクセストークン・redirect_toを返し、リフレッシュ/CSRF Cookieを設定することを検証する結合的なテスト。
	"""
	user_id = uuid4()
	user = SimpleNamespace(id=user_id, email="alice@example.com", is_active=True)
	handoff = OAuthHandoffData(user_id, "/dashboard", None)

	class _JwtStrategy:
		"""JwtAuthStrategyの差し替え先。ログイン時にリフレッシュ/CSRF Cookieを設定し固定の結果を返す。"""

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
		oauth_router_module.oauth_service.redis_store, "consume_oauth_handoff", AsyncMock(return_value=handoff)
	)
	monkeypatch.setattr(oauth_router_module.oauth_service.redis_store, "check_rate_limit", AsyncMock(return_value=1))
	monkeypatch.setattr(oauth_router_module.oauth_service.user_repository, "get_by_id", AsyncMock(return_value=user))
	monkeypatch.setattr(
		oauth_router_module.oauth_service, "_auth_strategy", lambda _settings, _strategy: _JwtStrategy()
	)
	monkeypatch.setattr(oauth_router_module.oauth_service, "_record_oauth_login", AsyncMock())

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
	"""jwtモードのcallbackが成功した場合、リダイレクト先URLのフラグメントにhandoffコードと
	redirect_toの両方が含まれる（フロントエンドがこのコードでexchangeを呼べるようにする）ことを検証する。
	"""

	async def _oauth_callback(*_args: Any, **_kwargs: Any) -> OAuthCallbackResult:
		return OAuthCallbackResult(auth_mode="jwt", redirect_to="/dashboard", handoff_code="handoff-code")

	monkeypatch.setattr(oauth_router_module.oauth_service, "oauth_callback", _oauth_callback)

	response = client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": "state-value"})

	location = response.headers["location"]
	assert location.startswith(f"{FRONTEND_BASE_URL}/oauth/callback#")
	fragment = location.split("#", 1)[1]
	assert fragment == "code=handoff-code&redirect_to=/dashboard"


def test_callback_with_google_error_redirects_to_login(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	"""GoogleがcallbackへerrorクエリでOAuth拒否（access_denied）を伝えた場合、
	oauth_callback_deniedへstate値が渡されたうえでログイン画面へerror=oauth_deniedを付けて
	リダイレクトし、oauth state Cookieが削除されることを検証する。
	"""
	called: list[tuple[Any, ...]] = []

	async def _oauth_callback_denied(*args: Any, **_kwargs: Any) -> None:
		"""oauth_service.oauth_callback_deniedの差し替え先。呼び出し引数を記録しつつstate Cookieを削除する。"""
		called.append(args)
		args[3].set_cookie("cerberus_oauth_state", "", max_age=0)

	monkeypatch.setattr(oauth_router_module.oauth_service, "oauth_callback_denied", _oauth_callback_denied)
	client.cookies.set("cerberus_oauth_state", "state-value")

	response = client.get("/api/auth/oauth/google/callback", params={"error": "access_denied", "state": "state-value"})

	assert response.status_code == 302
	assert response.headers["location"] == f"{FRONTEND_BASE_URL}/login?error=oauth_denied"
	assert len(called) == 1
	assert called[0][0:2] == ("state-value", "state-value")
	assert any("Max-Age=0" in value for value in response.headers.get_list("set-cookie"))


def test_callback_rejects_inconsistent_auth_mode_result(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	"""現在の設定はjwtモードなのに、service層がauth_mode="session"の結果を返した場合
	（クライアントfixtureはjwtモード固定）、不整合として扱いログイン画面へerror=oauth_failedで
	リダイレクトすることを検証する。
	"""

	async def _oauth_callback(*_args: Any, **_kwargs: Any) -> OAuthCallbackResult:
		return OAuthCallbackResult(auth_mode="session", redirect_to="/dashboard", handoff_code="unexpected")

	monkeypatch.setattr(oauth_router_module.oauth_service, "oauth_callback", _oauth_callback)

	response = client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": "state-value"})

	assert response.status_code == 302
	assert response.headers["location"] == f"{FRONTEND_BASE_URL}/login?error=oauth_failed"


def test_callback_rejects_result_mode_different_from_settings(
	client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
	"""service層が返したOAuthCallbackResult.auth_modeが、現在の設定上の認証モード(jwt)と
	異なる（session）場合、成功として扱わずログイン画面へerror=oauth_failedでリダイレクトすることを検証する。
	"""

	async def _oauth_callback(*_args: Any, **_kwargs: Any) -> OAuthCallbackResult:
		return OAuthCallbackResult(auth_mode="session", redirect_to="/dashboard")

	monkeypatch.setattr(oauth_router_module.oauth_service, "oauth_callback", _oauth_callback)

	response = client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": "state-value"})

	assert response.status_code == 302
	assert response.headers["location"] == f"{FRONTEND_BASE_URL}/login?error=oauth_failed"


def test_callback_rejects_jwt_result_without_handoff(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	"""jwtモードなのにservice層の返したOAuthCallbackResultにhandoff_codeが含まれない
	（フロントエンドがexchangeを呼ぶ手段が無い）場合、不整合として扱いログイン画面へ
	error=oauth_failedでリダイレクトすることを検証する。
	"""

	async def _oauth_callback(*_args: Any, **_kwargs: Any) -> OAuthCallbackResult:
		return OAuthCallbackResult(auth_mode="jwt", redirect_to="/dashboard")

	monkeypatch.setattr(oauth_router_module.oauth_service, "oauth_callback", _oauth_callback)

	response = client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": "state-value"})

	assert response.status_code == 302
	assert response.headers["location"] == f"{FRONTEND_BASE_URL}/login?error=oauth_failed"


def test_callback_denied_route_consumes_state_and_deletes_cookie(
	client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
	"""実装のoauth_service.oauth_callback_deniedを通し（consume_oauth_stateのみモック）、
	OAuth拒否のcallbackがステータス302でログイン画面へerror=oauth_deniedでリダイレクトし、
	state Cookieを削除することを検証する。
	"""
	monkeypatch.setattr(oauth_router_module.oauth_service.redis_store, "check_rate_limit", AsyncMock(return_value=1))
	monkeypatch.setattr(
		oauth_router_module.oauth_service.redis_store,
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


def test_callback_route_deletes_state_cookie_on_service_failure(
	client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
	"""Google側との認可コード交換で予期しない例外（RuntimeError）が発生した場合でも、
	ログイン画面へerror=oauth_failedでリダイレクトしつつ、oauth state Cookieの削除は
	正しく行われることを検証する（例外発生パスでもCookie後片付けが漏れないことの確認）。
	"""

	class _Provider:
		"""GoogleOAuthProviderの差し替え先。認可コード交換で必ずRuntimeErrorを送出する。"""

		async def exchange_code(self, _code: str, _verifier: str) -> Any:
			raise RuntimeError("provider unavailable")

	monkeypatch.setattr(oauth_router_module.oauth_service.redis_store, "check_rate_limit", AsyncMock(return_value=1))
	monkeypatch.setattr(
		oauth_router_module.oauth_service.redis_store,
		"consume_oauth_state",
		AsyncMock(return_value=OAuthStateData("/dashboard", "verifier", "nonce", None)),
	)
	monkeypatch.setattr(oauth_router_module.oauth_service, "GoogleOAuthProvider", lambda _settings: _Provider())
	client.cookies.set("cerberus_oauth_state", "state-value")

	response = client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": "state-value"})

	assert response.status_code == 302
	assert response.headers["location"] == f"{FRONTEND_BASE_URL}/login?error=oauth_failed"
	assert any(
		"cerberus_oauth_state=" in value and "Max-Age=0" in value for value in response.headers.get_list("set-cookie")
	)


def test_callback_redirects_to_login_when_google_login_is_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
	"""GOOGLE_LOGIN_ENABLED=falseの場合、service層のoauth_callbackを呼び出す前に
	ログイン画面へerror=oauth_disabledでリダイレクトすることを検証する。
	"""
	monkeypatch.setenv("CORS_ALLOW_ORIGINS", ALLOWED_ORIGIN)
	monkeypatch.setenv("GOOGLE_LOGIN_ENABLED", "false")
	get_backend_settings.cache_clear()
	called: list[str] = []

	async def _oauth_callback(*_args: Any, **_kwargs: Any) -> OAuthCallbackResult:
		called.append("service")
		raise AssertionError("無効時はserviceを呼ばない")

	monkeypatch.setattr(oauth_router_module.oauth_service, "oauth_callback", _oauth_callback)
	app = _build_app()
	with TestClient(app, follow_redirects=False) as test_client:
		response = test_client.get(
			"/api/auth/oauth/google/callback", params={"code": "auth-code", "state": "state-value"}
		)

	assert response.status_code == 302
	assert response.headers["location"] == f"{FRONTEND_BASE_URL}/login?error=oauth_disabled"
	assert called == []


@pytest.mark.parametrize(
	("error", "expected"),
	[
		(InvalidStateError(), "invalid_state"),
		(OAuthEmailUnverifiedError(), "oauth_email_unverified"),
		(RuntimeError("redis down"), "oauth_failed"),
	],
)
def test_callback_maps_exception_to_login_error(
	client: TestClient, monkeypatch: pytest.MonkeyPatch, error: Exception, expected: str
) -> None:
	"""service層のoauth_callbackが送出する各例外（state不正・メール未確認・想定外のRuntimeError）が、
	対応するログイン画面へのerrorクエリ値へマッピングされ、リダイレクト先URLに
	例外メッセージ等の詳細が一切含まれないことを検証する。
	"""

	async def _oauth_callback(*_args: Any, **_kwargs: Any) -> OAuthCallbackResult:
		raise error

	monkeypatch.setattr(oauth_router_module.oauth_service, "oauth_callback", _oauth_callback)

	response = client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": "state-value"})

	assert response.status_code == 302
	assert response.headers["location"] == f"{FRONTEND_BASE_URL}/login?error={expected}"
	# 失敗の詳細（例外メッセージ等）はブラウザへ返さない。
	assert "redis down" not in response.headers["location"]


@pytest.mark.parametrize(
	("error", "status_code", "error_code"),
	[
		(TooManyAttemptsError(retry_after=42), 429, "TOO_MANY_ATTEMPTS"),
		(ServiceUnavailableError(), 503, "SERVICE_UNAVAILABLE"),
	],
)
def test_callback_preserves_rate_limit_and_redis_errors(
	client: TestClient, monkeypatch: pytest.MonkeyPatch, error: Exception, status_code: int, error_code: str
) -> None:
	"""service層のoauth_callbackがTooManyAttemptsError・ServiceUnavailableErrorを送出した場合、
	（ログイン画面へのリダイレクトへ丸め込まず）それぞれ対応するHTTPステータス・エラーコードで
	JSON応答することを検証する。TooManyAttemptsErrorの場合はRetry-Afterヘッダーも設定される。
	"""

	async def _oauth_callback(*_args: Any, **_kwargs: Any) -> OAuthCallbackResult:
		raise error

	monkeypatch.setattr(oauth_router_module.oauth_service, "oauth_callback", _oauth_callback)

	response = client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": "state-value"})

	assert response.status_code == status_code
	assert response.json()["error"]["code"] == error_code
	if isinstance(error, TooManyAttemptsError):
		assert response.headers["Retry-After"] == "42"


def test_denied_callback_preserves_rate_limit_error(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	"""OAuth拒否のcallback処理中にservice層のoauth_callback_deniedがTooManyAttemptsErrorを
	送出した場合、ログイン画面へのリダイレクトへ丸め込まずステータス429・エラーコード
	TOO_MANY_ATTEMPTSでJSON応答し、Retry-Afterヘッダーが設定されることを検証する。
	"""

	async def _oauth_callback_denied(*_args: Any, **_kwargs: Any) -> None:
		raise TooManyAttemptsError(retry_after=42)

	monkeypatch.setattr(oauth_router_module.oauth_service, "oauth_callback_denied", _oauth_callback_denied)

	response = client.get("/api/auth/oauth/google/callback", params={"error": "access_denied", "state": "state-value"})

	assert response.status_code == 429
	assert response.json()["error"]["code"] == "TOO_MANY_ATTEMPTS"
	assert response.headers["Retry-After"] == "42"


def test_callback_service_rate_limit_returns_429(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	"""callback処理内のレート制限チェック(redis_store.check_rate_limit)が上限超過を示す場合、
	ステータス429・エラーコードTOO_MANY_ATTEMPTSで応答し、Retry-Afterヘッダーに
	redis_store.get_rate_limit_ttlの値が設定されることを検証する。
	"""
	monkeypatch.setattr(
		oauth_router_module.oauth_service.redis_store,
		"check_rate_limit",
		AsyncMock(return_value=11),
	)
	monkeypatch.setattr(oauth_router_module.oauth_service.redis_store, "get_rate_limit_ttl", AsyncMock(return_value=42))

	response = client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": "state-value"})

	assert response.status_code == 429
	assert response.json()["error"]["code"] == "TOO_MANY_ATTEMPTS"
	assert response.headers["Retry-After"] == "42"


def test_callback_service_redis_failure_returns_503(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	"""callback処理内のレート制限チェック自体（Redis）が例外を送出する場合、
	ステータス503・エラーコードSERVICE_UNAVAILABLEでfail-closeすることを検証する。
	"""
	monkeypatch.setattr(
		oauth_router_module.oauth_service.redis_store,
		"check_rate_limit",
		AsyncMock(side_effect=RuntimeError("redis unavailable")),
	)

	response = client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": "state-value"})

	assert response.status_code == 503
	assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


def test_exchange_returns_tokens_in_jwt_mode(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	"""jwtモードでのexchange成功が、ステータス200でアクセストークン・redirect_to等をJSONで返し、
	レスポンスにCache-Control: no-storeが設定され、リフレッシュ/CSRF Cookieが設定されることを検証する。
	"""

	async def _oauth_exchange(*_args: Any, **_kwargs: Any) -> OAuthExchangeResponse:
		_args[2].set_cookie("cerberus_rt", "refresh-token", httponly=True, path="/api/auth")
		_args[2].set_cookie("cerberus_csrf", "csrf-token", path="/")
		return OAuthExchangeResponse(
			access_token="access-token", token_type="bearer", expires_in=900, redirect_to="/dashboard"
		)

	monkeypatch.setattr(oauth_router_module.oauth_service, "oauth_exchange", _oauth_exchange)

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


def test_exchange_rate_limited_returns_positive_retry_after(
	client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
	"""service層のoauth_exchangeがTooManyAttemptsErrorを送出した場合、ステータス429・
	エラーコードTOO_MANY_ATTEMPTSで応答し、Retry-Afterヘッダーに正の秒数が設定されることを検証する。
	"""

	async def _oauth_exchange(*_args: Any, **_kwargs: Any) -> OAuthExchangeResponse:
		raise TooManyAttemptsError(retry_after=42)

	monkeypatch.setattr(oauth_router_module.oauth_service, "oauth_exchange", _oauth_exchange)

	response = client.post(
		"/api/auth/oauth/exchange", json={"code": "handoff-code"}, headers={"Origin": ALLOWED_ORIGIN}
	)

	assert response.status_code == 429
	assert response.json()["error"]["code"] == "TOO_MANY_ATTEMPTS"
	assert response.headers["Retry-After"] == "42"
	assert int(response.headers["Retry-After"]) > 0


def test_exchange_in_session_mode_returns_405(monkeypatch: pytest.MonkeyPatch) -> None:
	"""sessionモードではexchange機能自体が提供されないため、service層を呼び出す前にステータス405・
	エラーコードNOT_SUPPORTED_IN_MODEで応答することを検証する。
	"""
	monkeypatch.setenv("CORS_ALLOW_ORIGINS", ALLOWED_ORIGIN)
	monkeypatch.setenv("AUTH_MODE", "session")
	get_backend_settings.cache_clear()
	called: list[str] = []

	async def _oauth_exchange(*_args: Any, **_kwargs: Any) -> OAuthExchangeResponse:
		called.append("service")
		raise AssertionError("sessionモードではserviceを呼ばない")

	monkeypatch.setattr(oauth_router_module.oauth_service, "oauth_exchange", _oauth_exchange)
	app = _build_app()
	with TestClient(app, follow_redirects=False) as test_client:
		response = test_client.post(
			"/api/auth/oauth/exchange", json={"code": "handoff-code"}, headers={"Origin": ALLOWED_ORIGIN}
		)

	assert response.status_code == 405
	assert response.json()["error"]["code"] == "NOT_SUPPORTED_IN_MODE"
	assert called == []


def test_exchange_returns_oauth_disabled_when_google_login_is_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
	"""GOOGLE_LOGIN_ENABLED=falseの場合、service層のoauth_exchangeを呼び出す前にステータス404・
	エラーコードOAUTH_DISABLEDで応答することを検証する。
	"""
	monkeypatch.setenv("CORS_ALLOW_ORIGINS", ALLOWED_ORIGIN)
	monkeypatch.setenv("AUTH_MODE", "jwt")
	monkeypatch.setenv("GOOGLE_LOGIN_ENABLED", "false")
	get_backend_settings.cache_clear()
	called: list[str] = []

	async def _oauth_exchange(*_args: Any, **_kwargs: Any) -> OAuthExchangeResponse:
		called.append("service")
		raise AssertionError("無効時はserviceを呼ばない")

	monkeypatch.setattr(oauth_router_module.oauth_service, "oauth_exchange", _oauth_exchange)
	app = _build_app()
	with TestClient(app, follow_redirects=False) as test_client:
		response = test_client.post(
			"/api/auth/oauth/exchange", json={"code": "handoff-code"}, headers={"Origin": ALLOWED_ORIGIN}
		)

	assert response.status_code == 404
	assert response.json()["error"]["code"] == "OAUTH_DISABLED"
	assert called == []


def test_exchange_rejects_disallowed_origin(client: TestClient) -> None:
	"""Originヘッダーが許可オリジンに含まれない場合、service層を呼び出す前にステータス403・
	エラーコードCSRF_INVALIDで拒否することを検証する。
	"""
	response = client.post(
		"/api/auth/oauth/exchange", json={"code": "handoff-code"}, headers={"Origin": "http://evil.example"}
	)

	assert response.status_code == 403
	assert response.json()["error"]["code"] == "CSRF_INVALID"


def test_exchange_invalid_handoff_code_returns_400(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	"""service層のoauth_exchangeがOAuthHandoffInvalidErrorを送出した場合（コード不正・期限切れ等）、
	ステータス400・エラーコードOAUTH_HANDOFF_INVALIDで応答することを検証する。
	"""

	async def _oauth_exchange(*_args: Any, **_kwargs: Any) -> OAuthExchangeResponse:
		raise OAuthHandoffInvalidError()

	monkeypatch.setattr(oauth_router_module.oauth_service, "oauth_exchange", _oauth_exchange)

	response = client.post(
		"/api/auth/oauth/exchange", json={"code": "expired-code"}, headers={"Origin": ALLOWED_ORIGIN}
	)

	assert response.status_code == 400
	assert response.json()["error"]["code"] == "OAUTH_HANDOFF_INVALID"


def test_exchange_rejects_empty_code(client: TestClient) -> None:
	"""空文字のcodeを送信した場合、service層を呼び出す前にステータス422・
	エラーコードVALIDATION_ERRORで拒否することを検証する。
	"""
	response = client.post("/api/auth/oauth/exchange", json={"code": ""}, headers={"Origin": ALLOWED_ORIGIN})

	assert response.status_code == 422
	assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_exchange_rejects_code_over_configured_limit_before_service(
	client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
	"""codeが設定上の最大長(512文字)を超える場合、service層を呼び出す前にステータス422・
	エラーコードVALIDATION_ERRORで拒否することを検証する。
	"""
	called: list[str] = []

	async def _oauth_exchange(*_args: Any, **_kwargs: Any) -> OAuthExchangeResponse:
		called.append("service")
		raise AssertionError("上限超過時はserviceを呼び出さない")

	monkeypatch.setattr(oauth_router_module.oauth_service, "oauth_exchange", _oauth_exchange)
	response = client.post("/api/auth/oauth/exchange", json={"code": "a" * 513}, headers={"Origin": ALLOWED_ORIGIN})

	assert response.status_code == 422
	assert response.json()["error"]["code"] == "VALIDATION_ERROR"
	assert called == []


def test_callback_rejects_code_over_configured_limit_before_google_service(client: TestClient) -> None:
	"""callbackのcodeクエリが設定上の最大長(512文字)を超える場合、Google側との交換処理を
	呼び出す前にステータス422・エラーコードVALIDATION_ERRORで拒否することを検証する。
	"""
	response = client.get("/api/auth/oauth/google/callback", params={"code": "a" * 513, "state": "state-value"})

	assert response.status_code == 422
	assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_oauth_endpoints_are_published_in_openapi() -> None:
	"""app.mainの実アプリのOpenAPIスキーマに、oauth_routerの全3エンドポイントが
	期待するHTTPメソッドで登録されていることを検証する。
	"""
	from app.main import app as main_app

	paths = main_app.openapi()["paths"]

	assert set(paths["/api/auth/oauth/google"]) == {"get"}
	assert set(paths["/api/auth/oauth/google/callback"]) == {"get"}
	assert set(paths["/api/auth/oauth/exchange"]) == {"post"}


def _formatted_oauth_logs(records: list[logging.LogRecord]) -> list[dict[str, Any]]:
	"""app.oauthロガーのログレコードのみを、実際の本番出力と同じJsonFormatterでフォーマットし、
	パース済みのdictリストとして返す（extraフィールドがフォーマット後も残るかを検証するため）。

	Args:
		records: caplogが捕捉したログレコードの一覧。

	Returns:
		app.oauthロガーのレコードをJSON整形してパースした辞書のリスト。
	"""
	formatter = JsonFormatter()
	return [json.loads(formatter.format(record)) for record in records if record.name == "app.oauth"]


def test_callback_failure_log_keeps_failure_reason_after_formatting(
	client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
	"""service層のoauth_callbackが例外を送出した場合、app.oauthロガーへ記録される
	失敗ログのextraフィールド（event・failure_reason）が、JsonFormatterでの整形後も
	（許可フィールド一覧_SAFE_AUDIT_FIELDSに含まれるため）失われずに残ることを検証する。
	"""

	async def _oauth_callback(*_args: Any, **_kwargs: Any) -> OAuthCallbackResult:
		raise InvalidStateError()

	monkeypatch.setattr(oauth_router_module.oauth_service, "oauth_callback", _oauth_callback)

	with caplog.at_level(logging.WARNING, logger="app.oauth"):
		response = client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": "state-value"})

	assert response.status_code == 302
	payloads = _formatted_oauth_logs(caplog.records)
	assert len(payloads) == 1
	# extraのキーは_SAFE_AUDIT_FIELDSに含まれる必要があり、含まれない場合は値が捨てられる。
	assert payloads[0]["event"] == "oauth_callback_failed"
	assert payloads[0]["failure_reason"] == "InvalidStateError"


def test_denied_callback_cleanup_failure_log_keeps_failure_reason_after_formatting(
	client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
	"""OAuth拒否のcallback後片付け処理（oauth_callback_denied）が例外を送出した場合も同様に、
	app.oauthロガーへ記録される失敗ログのfailure_reasonがJsonFormatterでの整形後も
	失われずに残ることを検証する。
	"""

	async def _oauth_callback_denied(*_args: Any, **_kwargs: Any) -> None:
		raise InvalidStateError()

	monkeypatch.setattr(oauth_router_module.oauth_service, "oauth_callback_denied", _oauth_callback_denied)

	with caplog.at_level(logging.WARNING, logger="app.oauth"):
		response = client.get(
			"/api/auth/oauth/google/callback", params={"error": "access_denied", "state": "state-value"}
		)

	assert response.status_code == 302
	payloads = _formatted_oauth_logs(caplog.records)
	assert len(payloads) == 1
	assert payloads[0]["failure_reason"] == "InvalidStateError"
