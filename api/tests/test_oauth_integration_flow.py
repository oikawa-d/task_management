"""OAuth開始→callback→exchange→既存session/JWT認証確立までの結合テスト。

Google token/userinfo/JWKSエンドポイントのみを境界として差し替え、Redis（state/handoff/
session/refresh）とPostgreSQL（users/oauth_accounts/login_history）は実接続を用いて、
state/PKCE/nonce/handoffの検証と消費、許可redirectのみの処理、既存session/JWT認証の確立、
外部I/O障害時のfail-closeを検証する。

db_session（実DB）とTestClient（別スレッドのイベントループ）を組み合わせるとasyncpg接続が
異なるイベントループにまたがり破綻するため、ASGITransport経由のhttpx2.AsyncClientを用いて
テスト関数と同一イベントループ上でリクエストを実行する。

参照設計書: docs/detailed_design/auth/04_google_oauth.md（4〜11章、テスト設計No.2〜11）
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
import uuid
from typing import Any
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from app import redis_client
from app.api.routers import auth_router
from app.api.routers import oauth_router as oauth_router_module
from app.auth.factory import get_auth_strategy
from app.auth.oauth import GoogleOAuthProvider
from app.core.config import get_backend_settings
from app.core.exceptions import register_error_handling
from app.db import get_db_session
from app.repository import login_history_repository, oauth_account_repository, user_repository
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient
from jwt.algorithms import RSAAlgorithm
from sqlalchemy.ext.asyncio import AsyncSession

ALLOWED_ORIGIN = "http://localhost:5173"
FRONTEND_BASE_URL = "http://localhost:5173"


@pytest.fixture(autouse=True)
async def _fresh_redis_client_per_test() -> None:
	"""get_redis_client()はlru_cacheのプロセス単位シングルトンで、テストごとに新しい
	イベントループを使うpytest-asyncioと組み合わせると前のテストの接続を別ループで
	使い回してしまう。テストごとに接続を張り直し、実Redisへの結合を健全に保つ。"""
	redis_client.get_redis_client.cache_clear()
	yield
	try:
		await redis_client.close_redis_client()
	except Exception:
		pass
	redis_client.get_redis_client.cache_clear()


def _new_identity() -> tuple[str, str]:
	"""テストごとに一意なGoogle sub/emailを発行し、DBへの実書き込みが他テストと衝突しないようにする。

	usersテーブルのemailはvarchar(50)のため、短い一意サフィックスに収める。
	"""
	unique = uuid.uuid4().hex[:10]
	return f"google-sub-{unique}", f"oauth-{unique}@example.com"


def _userinfo(sub: str, email: str) -> dict[str, Any]:
	return {"sub": sub, "email": email, "email_verified": True}


class _HttpResponse:
	def __init__(self, status_code: int, body: dict[str, Any]) -> None:
		self.status_code = status_code
		self._body = body

	def json(self) -> dict[str, Any]:
		return self._body


class _GoogleBoundary:
	"""Google token/userinfo/JWKSエンドポイントの唯一の差し替え境界（結合テスト用）。

	tokenエンドポイントへ実際に送信されたPOSTボディ（code_verifier等）を`posted`に
	記録し、開始時に発行したcode_verifierがRedis経由でcallbackのtoken交換まで
	正しく引き継がれることを検証できるようにする。
	"""

	def __init__(
		self,
		token: dict[str, Any] | None = None,
		userinfo: dict[str, Any] | None = None,
		jwks: dict[str, Any] | None = None,
		*,
		token_status: int = 200,
		userinfo_status: int = 200,
		jwks_status: int = 200,
	) -> None:
		self.token = token or {}
		self.userinfo = userinfo or {}
		self.jwks = jwks or {}
		self.token_status = token_status
		self.userinfo_status = userinfo_status
		self.jwks_status = jwks_status
		self.posted: list[dict[str, str]] = []

	async def post(self, _url: str, *, data: dict[str, str]) -> _HttpResponse:
		self.posted.append(data)
		return _HttpResponse(self.token_status, self.token)

	async def get(self, url: str, *, headers: dict[str, str] | None = None) -> _HttpResponse:
		if "certs" in url:
			return _HttpResponse(self.jwks_status, self.jwks)
		return _HttpResponse(self.userinfo_status, self.userinfo)


def _signed_id_token(
	client_id: str, nonce: str, *, sub: str, email: str, jwks_kid: str = "key-1"
) -> tuple[str, dict[str, Any]]:
	private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
	public_jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
	public_jwk["kid"] = jwks_kid
	claims: dict[str, Any] = {
		"sub": sub,
		"email": email,
		"email_verified": True,
		"iss": "https://accounts.google.com",
		"aud": client_id,
		"exp": int(time.time()) + 60,
		"nonce": nonce,
	}
	token = jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": jwks_kid})
	return token, {"keys": [public_jwk]}


def _build_app() -> FastAPI:
	app = FastAPI()
	register_error_handling(app)
	app.include_router(oauth_router_module.router)
	app.include_router(auth_router.router)
	return app


def _configure(monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession, *, auth_mode: str, jwks_uri: str) -> FastAPI:
	monkeypatch.setenv("CORS_ALLOW_ORIGINS", ALLOWED_ORIGIN)
	monkeypatch.setenv("FRONTEND_BASE_URL", FRONTEND_BASE_URL)
	monkeypatch.setenv("AUTH_MODE", auth_mode)
	monkeypatch.setenv("GOOGLE_JWKS_URI", jwks_uri)
	# レート制限自体は test_oauth_service.py で検証済みのため、実Redisに蓄積した
	# カウンタが結合テストの反復実行を阻害しないよう十分大きい上限へ緩和する。
	monkeypatch.setenv("RATE_LIMIT_OAUTH_MAX_REQUESTS", "100000")
	get_backend_settings.cache_clear()
	get_auth_strategy.cache_clear()
	app = _build_app()
	app.dependency_overrides[get_db_session] = lambda: db_session
	return app


def _client(app: FastAPI) -> AsyncClient:
	return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver", follow_redirects=False)


async def _start_and_capture_state(client: AsyncClient, redirect_to: str = "/dashboard") -> tuple[str, str, str]:
	"""開始エンドポイントを叩き、実Redisへ発行されたstate/nonce/code_challengeを取得する。"""
	response = await client.get("/api/auth/oauth/google", params={"redirect_to": redirect_to})
	assert response.status_code == 302
	query = parse_qs(urlparse(response.headers["location"]).query)
	state = query["state"][0]
	nonce = query["nonce"][0]
	assert query["code_challenge_method"] == ["S256"]
	code_challenge = query["code_challenge"][0]
	assert any(cookie.startswith("cerberus_oauth_state=") for cookie in response.headers.get_list("set-cookie"))
	return state, nonce, code_challenge


def _assert_pkce_verifier_matches_challenge(boundary: _GoogleBoundary, code_challenge: str) -> None:
	"""開始時に発行したcode_challengeと、callbackがtokenエンドポイントへ実際に送信した
	code_verifierの対応関係（S256）を検証する。開始→Redis（oauth_state）→callbackの
	token交換までPKCEの値が正しく引き継がれることの結合テストでの唯一の確認経路。
	"""
	assert len(boundary.posted) == 1
	code_verifier = boundary.posted[0].get("code_verifier")
	assert code_verifier
	expected_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).rstrip(b"=").decode()
	assert expected_challenge == code_challenge


async def test_full_session_flow_creates_user_and_establishes_authenticated_session(
	monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession
) -> None:
	app = _configure(
		monkeypatch, db_session, auth_mode="session", jwks_uri="https://jwks.example.test/certs/session-happy"
	)
	client_id = get_backend_settings().google_client_id
	sub, email = _new_identity()
	async with _client(app) as client:
		state, nonce, code_challenge = await _start_and_capture_state(client, "/projects/1")
		token, jwks = _signed_id_token(client_id, nonce, sub=sub, email=email)
		boundary = _GoogleBoundary({"id_token": token, "access_token": "access-token"}, _userinfo(sub, email), jwks)
		monkeypatch.setattr(
			oauth_router_module.auth_service,
			"GoogleOAuthProvider",
			lambda settings: GoogleOAuthProvider(settings, boundary),
		)

		callback = await client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": state})

		assert callback.status_code == 302
		assert callback.headers["location"] == f"{FRONTEND_BASE_URL}/oauth/callback#redirect_to=/projects/1"
		set_cookie = callback.headers.get_list("set-cookie")
		assert any(value.startswith("cerberus_sid=") for value in set_cookie)
		assert any("cerberus_oauth_state=" in value and "Max-Age=0" in value for value in set_cookie)
		_assert_pkce_verifier_matches_challenge(boundary, code_challenge)

		me = await client.get("/api/auth/me")
		assert me.status_code == 200
		assert me.json()["username"].startswith("google_")

	user = await user_repository.get_by_email(db_session, email)
	assert user is not None
	assert user.email_verified_at is not None
	link = await oauth_account_repository.get_by_provider_identity(db_session, "google", sub)
	assert link is not None and link.user_id == user.id
	history = await login_history_repository.list_by_user_id(db_session, user.id)
	assert any(record.login_method == "oauth_google" and record.login_identifier == user.email for record in history)


async def test_full_jwt_flow_exchanges_handoff_and_establishes_bearer_authentication(
	monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession
) -> None:
	app = _configure(monkeypatch, db_session, auth_mode="jwt", jwks_uri="https://jwks.example.test/certs/jwt-happy")
	client_id = get_backend_settings().google_client_id
	sub, email = _new_identity()
	async with _client(app) as client:
		state, nonce, code_challenge = await _start_and_capture_state(client)
		token, jwks = _signed_id_token(client_id, nonce, sub=sub, email=email)
		boundary = _GoogleBoundary({"id_token": token, "access_token": "access-token"}, _userinfo(sub, email), jwks)
		monkeypatch.setattr(
			oauth_router_module.auth_service,
			"GoogleOAuthProvider",
			lambda settings: GoogleOAuthProvider(settings, boundary),
		)

		callback = await client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": state})
		assert callback.status_code == 302
		_assert_pkce_verifier_matches_challenge(boundary, code_challenge)
		fragment = callback.headers["location"].split("#", 1)[1]
		fragment_values = dict(pair.split("=", 1) for pair in fragment.split("&"))
		handoff_code = fragment_values["code"]

		exchange = await client.post(
			"/api/auth/oauth/exchange", json={"code": handoff_code}, headers={"Origin": ALLOWED_ORIGIN}
		)
		assert exchange.status_code == 200
		access_token = exchange.json()["access_token"]

		me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {access_token}"})
		assert me.status_code == 200

		replay = await client.post(
			"/api/auth/oauth/exchange", json={"code": handoff_code}, headers={"Origin": ALLOWED_ORIGIN}
		)
		assert replay.status_code == 400
		assert replay.json()["error"]["code"] == "OAUTH_HANDOFF_INVALID"

	user = await user_repository.get_by_email(db_session, email)
	assert user is not None
	history = await login_history_repository.list_by_user_id(db_session, user.id)
	assert any(record.login_method == "oauth_google" for record in history)


async def test_callback_rejects_state_cookie_mismatch_without_creating_user(
	monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession
) -> None:
	app = _configure(
		monkeypatch, db_session, auth_mode="session", jwks_uri="https://jwks.example.test/certs/state-mismatch"
	)
	_sub, email = _new_identity()
	async with _client(app) as client:
		state, _nonce, _code_challenge = await _start_and_capture_state(client)
		client.cookies.set("cerberus_oauth_state", "tampered-state")

		callback = await client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": state})

		assert callback.status_code == 302
		assert callback.headers["location"] == f"{FRONTEND_BASE_URL}/login?error=invalid_state"

	assert await user_repository.get_by_email(db_session, email) is None


async def test_callback_rejects_nonce_mismatch_without_creating_user(
	monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession
) -> None:
	app = _configure(
		monkeypatch, db_session, auth_mode="session", jwks_uri="https://jwks.example.test/certs/nonce-mismatch"
	)
	client_id = get_backend_settings().google_client_id
	sub, email = _new_identity()
	async with _client(app) as client:
		state, _nonce, _code_challenge = await _start_and_capture_state(client)
		token, jwks = _signed_id_token(client_id, "unexpected-nonce", sub=sub, email=email)
		boundary = _GoogleBoundary({"id_token": token, "access_token": "access-token"}, _userinfo(sub, email), jwks)
		monkeypatch.setattr(
			oauth_router_module.auth_service,
			"GoogleOAuthProvider",
			lambda settings: GoogleOAuthProvider(settings, boundary),
		)

		callback = await client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": state})

		assert callback.status_code == 302
		assert callback.headers["location"] == f"{FRONTEND_BASE_URL}/login?error=oauth_failed"

	assert await user_repository.get_by_email(db_session, email) is None


async def test_callback_rejects_userinfo_sub_mismatch_without_creating_user(
	monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession
) -> None:
	app = _configure(
		monkeypatch, db_session, auth_mode="session", jwks_uri="https://jwks.example.test/certs/sub-mismatch"
	)
	client_id = get_backend_settings().google_client_id
	sub, email = _new_identity()
	wrong_sub, _wrong_email = _new_identity()
	async with _client(app) as client:
		state, nonce, _code_challenge = await _start_and_capture_state(client)
		token, jwks = _signed_id_token(client_id, nonce, sub=sub, email=email)
		boundary = _GoogleBoundary(
			{"id_token": token, "access_token": "access-token"}, _userinfo(wrong_sub, email), jwks
		)
		monkeypatch.setattr(
			oauth_router_module.auth_service,
			"GoogleOAuthProvider",
			lambda settings: GoogleOAuthProvider(settings, boundary),
		)

		callback = await client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": state})

		assert callback.status_code == 302
		assert callback.headers["location"] == f"{FRONTEND_BASE_URL}/login?error=oauth_failed"

	assert await user_repository.get_by_email(db_session, email) is None


async def test_callback_fails_closed_when_google_token_endpoint_is_unavailable(
	monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession
) -> None:
	app = _configure(
		monkeypatch, db_session, auth_mode="session", jwks_uri="https://jwks.example.test/certs/token-down"
	)
	_sub, email = _new_identity()
	async with _client(app) as client:
		state, _nonce, _code_challenge = await _start_and_capture_state(client)
		boundary = _GoogleBoundary(token_status=503)
		monkeypatch.setattr(
			oauth_router_module.auth_service,
			"GoogleOAuthProvider",
			lambda settings: GoogleOAuthProvider(settings, boundary),
		)

		callback = await client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": state})

		assert callback.status_code == 302
		assert callback.headers["location"] == f"{FRONTEND_BASE_URL}/login?error=oauth_failed"

		# stateはcallback失敗時も消費済みのため、同一stateでの再試行は成立しない。
		client.cookies.set("cerberus_oauth_state", state)
		replay = await client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": state})
		assert replay.headers["location"] == f"{FRONTEND_BASE_URL}/login?error=invalid_state"

	assert await user_repository.get_by_email(db_session, email) is None


async def test_callback_fails_closed_when_google_jwks_endpoint_is_unavailable(
	monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession
) -> None:
	app = _configure(monkeypatch, db_session, auth_mode="session", jwks_uri="https://jwks.example.test/certs/jwks-down")
	_sub, email = _new_identity()
	async with _client(app) as client:
		state, _nonce, _code_challenge = await _start_and_capture_state(client)
		boundary = _GoogleBoundary({"id_token": "irrelevant", "access_token": "access-token"}, jwks_status=503)
		monkeypatch.setattr(
			oauth_router_module.auth_service,
			"GoogleOAuthProvider",
			lambda settings: GoogleOAuthProvider(settings, boundary),
		)

		callback = await client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": state})

		assert callback.status_code == 302
		assert callback.headers["location"] == f"{FRONTEND_BASE_URL}/login?error=oauth_failed"

	assert await user_repository.get_by_email(db_session, email) is None


async def test_start_normalizes_disallowed_redirect_to_across_the_full_roundtrip(
	monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession
) -> None:
	app = _configure(
		monkeypatch, db_session, auth_mode="session", jwks_uri="https://jwks.example.test/certs/redirect-guard"
	)
	client_id = get_backend_settings().google_client_id
	sub, email = _new_identity()
	async with _client(app) as client:
		state, nonce, _code_challenge = await _start_and_capture_state(client, "https://evil.example/steal")
		token, jwks = _signed_id_token(client_id, nonce, sub=sub, email=email)
		boundary = _GoogleBoundary({"id_token": token, "access_token": "access-token"}, _userinfo(sub, email), jwks)
		monkeypatch.setattr(
			oauth_router_module.auth_service,
			"GoogleOAuthProvider",
			lambda settings: GoogleOAuthProvider(settings, boundary),
		)

		callback = await client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": state})

		assert callback.status_code == 302
		assert callback.headers["location"] == f"{FRONTEND_BASE_URL}/oauth/callback#redirect_to=/dashboard"
