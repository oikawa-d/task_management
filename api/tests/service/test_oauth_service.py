import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import jwt
import pytest
from app.core.config import BackendSettings
from app.core.exceptions import OAuthFailedError
from app.schemas.oauth import OAuthExchangeResponse
from app.service.oauth_service import (
	GoogleOAuthProvider,
	InvalidStateError,
	OAuthService,
	OAuthUserInfo,
	normalize_redirect_to,
)
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from starlette.requests import Request
from starlette.responses import Response


def settings(**overrides: object) -> BackendSettings:
	values: dict[str, object] = {
		"database_url": "postgresql+asyncpg://test",
		"jwt_secret_key": "jwt-secret",
		"google_client_id": "client-id",
		"google_client_secret": "client-secret",
		"initial_admin_email": "admin@example.com",
		"initial_admin_username": "admin",
		"initial_admin_password": "password",
		"frontend_base_url": "http://frontend.test",
	}
	values.update(overrides)
	return BackendSettings(_env_file=None, **values)


def request() -> Request:
	return Request({"type": "http", "method": "GET", "path": "/", "headers": [], "client": ("127.0.0.1", 1)})


class FakeHttpClient:
	def __init__(self, token: dict[str, object], userinfo: dict[str, object]) -> None:
		self.token = token
		self.userinfo = userinfo

	async def post(self, url: str, *, data: dict[str, str]) -> SimpleNamespace:
		return SimpleNamespace(status_code=200, json=lambda: self.token)

	async def get(self, url: str, *, headers: dict[str, str] | None = None) -> SimpleNamespace:
		return SimpleNamespace(status_code=200, json=lambda: self.userinfo)


class JwksHttpClient:
	def __init__(self, jwks: dict[str, object]) -> None:
		self.jwks = jwks

	async def get(self, url: str, *, headers: dict[str, str] | None = None) -> SimpleNamespace:
		return SimpleNamespace(status_code=200, json=lambda: self.jwks)


def test_normalize_redirect_to_falls_back_for_external_path() -> None:
	config = settings()

	assert normalize_redirect_to("https://evil.example", config) == "/dashboard"
	assert normalize_redirect_to("//evil.example", config) == "/dashboard"
	assert normalize_redirect_to("/projects/1", config) == "/projects/1"


def test_build_authorize_url_contains_pkce_and_nonce() -> None:
	provider = GoogleOAuthProvider(settings())

	url = provider.build_authorize_url("state", "challenge", "nonce")

	assert "client_id=client-id" in url
	assert "code_challenge=challenge" in url
	assert "code_challenge_method=S256" in url
	assert "nonce=nonce" in url


@pytest.mark.asyncio
async def test_verify_id_token_checks_signature_claims_and_nonce() -> None:
	private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
	public_jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
	public_jwk["kid"] = "key-1"
	provider = GoogleOAuthProvider(settings(), JwksHttpClient({"keys": [public_jwk]}))
	token = jwt.encode(
		{
			"sub": "google-sub",
			"email": "alice@example.com",
			"email_verified": True,
			"iss": "https://accounts.google.com",
			"aud": "client-id",
			"exp": int(time.time()) + 60,
			"nonce": "nonce-1",
		},
		private_key,
		algorithm="RS256",
		headers={"kid": "key-1"},
	)

	claims = await provider.verify_id_token(token, "nonce-1")

	assert claims.sub == "google-sub"
	with pytest.raises(OAuthFailedError):
		await provider.verify_id_token(token, "wrong-nonce")


@pytest.mark.asyncio
async def test_oauth_callback_rejects_state_cookie_mismatch() -> None:
	service = OAuthService(AsyncMock(), settings=settings())

	with pytest.raises(InvalidStateError):
		await service.oauth_callback("code", "state", "different", request(), Response())


@pytest.mark.asyncio
async def test_oauth_callback_rejects_replayed_state() -> None:
	state_repository = SimpleNamespace(consume_oauth_state=AsyncMock(return_value=None))
	service = OAuthService(AsyncMock(), settings=settings(), state_repository=state_repository)

	with pytest.raises(InvalidStateError):
		await service.oauth_callback("code", "state", "state", request(), Response())
	state_repository.consume_oauth_state.assert_awaited_once()


@pytest.mark.asyncio
async def test_oauth_exchange_consumes_handoff_and_records_login_history() -> None:
	user_id = uuid4()
	user = SimpleNamespace(id=user_id, email="alice@example.com", is_active=True)
	state_repository = SimpleNamespace(
		consume_oauth_handoff=AsyncMock(return_value=SimpleNamespace(user_id=user_id, redirect_to="/dashboard"))
	)
	users = SimpleNamespace(get_by_id=AsyncMock(return_value=user))
	login_history = SimpleNamespace(create=AsyncMock())
	jwt_auth = SimpleNamespace(login=AsyncMock(return_value=SimpleNamespace(access_token="access", expires_in=900)))
	service = OAuthService(
		AsyncMock(),
		settings=settings(auth_mode="jwt"),
		handoff_repository=state_repository,
		user_repository=users,
		login_history_repository=login_history,
		jwt_auth_service=jwt_auth,
	)

	result = await service.oauth_exchange("handoff", request(), Response())

	assert isinstance(result, OAuthExchangeResponse)
	assert result.access_token == "access"
	assert result.redirect_to == "/dashboard"
	login_history.create.assert_awaited_once()


def test_oauth_userinfo_requires_verified_shape() -> None:
	userinfo = OAuthUserInfo(sub="sub", email="alice@example.com", email_verified=True)

	assert userinfo.email_verified is True
