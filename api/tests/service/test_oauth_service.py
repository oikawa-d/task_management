import base64
import hashlib
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import jwt
import pytest
from app.auth.base import LoginResult
from app.auth.oauth import GoogleOAuthProvider, GoogleUserInfo, IdTokenClaims, OAuthTokenResponse
from app.core.config import BackendSettings
from app.core.exceptions import (
	InvalidStateError,
	OAuthEmailUnverifiedError,
	OAuthFailedError,
	OAuthHandoffInvalidError,
	ServiceUnavailableError,
	TooManyAttemptsError,
	UserInactiveError,
)
from app.repository.redis_store_common import OAuthHandoffData, OAuthStateData
from app.schemas.oauth import OAuthExchangeResponse
from app.service import auth_service
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from starlette.requests import Request
from starlette.responses import Response


def _settings(**overrides: object) -> BackendSettings:
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


def _request() -> Request:
	return Request({"type": "http", "method": "GET", "path": "/", "headers": [], "client": ("127.0.0.1", 1)})


@pytest.fixture(autouse=True)
def _oauth_rate_limit_success(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(auth_service.redis_store, "check_rate_limit", AsyncMock(return_value=1))


class _HttpResponse:
	def __init__(self, status_code: int, body: dict[str, object]) -> None:
		self.status_code = status_code
		self._body = body

	def json(self) -> dict[str, object]:
		return self._body


class _OAuthHttpClient:
	def __init__(self, token: dict[str, object], userinfo: dict[str, object], jwks: dict[str, object]) -> None:
		self.token = token
		self.userinfo = userinfo
		self.jwks = jwks
		self.posted: list[tuple[str, dict[str, str]]] = []

	async def post(self, url: str, *, data: dict[str, str]) -> _HttpResponse:
		self.posted.append((url, data))
		return _HttpResponse(200, self.token)

	async def get(self, url: str, *, headers: dict[str, str] | None = None) -> _HttpResponse:
		if headers is not None:
			assert headers == {"Authorization": "Bearer access-token"}
		return _HttpResponse(200, self.jwks if "certs" in url else self.userinfo)


def _signed_id_token(
	settings: BackendSettings,
	nonce: str,
	*,
	audience: str | list[str] | None = None,
	azp: str | None = None,
) -> tuple[str, dict[str, object]]:
	private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
	public_jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
	public_jwk["kid"] = "key-1"
	claims: dict[str, object] = {
		"sub": "google-sub",
		"email": "alice@example.com",
		"email_verified": True,
		"iss": "https://accounts.google.com",
		"aud": settings.google_client_id if audience is None else audience,
		"exp": int(time.time()) + 60,
		"nonce": nonce,
	}
	if azp is not None:
		claims["azp"] = azp
	token = jwt.encode(
		claims,
		private_key,
		algorithm="RS256",
		headers={"kid": "key-1"},
	)
	return token, {"keys": [public_jwk]}


def test_normalize_redirect_to_rejects_external_and_protocol_relative_urls() -> None:
	settings = _settings()

	assert auth_service.normalize_redirect_to("/projects/1", settings) == "/projects/1"
	assert auth_service.normalize_redirect_to("https://evil.example", settings) == "/dashboard"
	assert auth_service.normalize_redirect_to("//evil.example", settings) == "/dashboard"
	assert auth_service.normalize_redirect_to(r"/\evil.example", settings) == "/dashboard"
	assert auth_service.normalize_redirect_to("/projects/1\nnext", settings) == "/dashboard"
	accepted = "/" + "a" * (settings.oauth_redirect_to_max_length - 1)
	too_long = "/" + "a" * settings.oauth_redirect_to_max_length
	assert auth_service.normalize_redirect_to(accepted, settings) == accepted
	assert auth_service.normalize_redirect_to(too_long, settings) == "/dashboard"


def test_build_authorize_url_contains_contract_parameters() -> None:
	provider = GoogleOAuthProvider(_settings())
	query = parse_qs(urlparse(provider.build_authorize_url("state", "challenge", "nonce")).query)

	assert query["client_id"] == ["client-id"]
	assert query["scope"] == ["openid email profile"]
	assert query["code_challenge_method"] == ["S256"]
	assert query["code_challenge"] == ["challenge"]
	assert query["nonce"] == ["nonce"]


@pytest.mark.asyncio
async def test_provider_exchanges_code_with_pkce_parameters() -> None:
	settings = _settings()
	client = _OAuthHttpClient({"id_token": "id", "access_token": "access-token"}, {}, {})
	provider = GoogleOAuthProvider(settings, client)

	result = await provider.exchange_code("code", "verifier")

	assert result.id_token == "id"
	assert client.posted == [
		(
			settings.google_token_endpoint,
			{
				"code": "code",
				"code_verifier": "verifier",
				"client_id": "client-id",
				"client_secret": "client-secret",
				"redirect_uri": settings.google_redirect_uri,
				"grant_type": "authorization_code",
			},
		)
	]


@pytest.mark.asyncio
async def test_provider_logs_token_exchange_failure_without_sensitive_values(caplog: pytest.LogCaptureFixture) -> None:
	client = SimpleNamespace(post=AsyncMock(return_value=_HttpResponse(400, {})))
	provider = GoogleOAuthProvider(_settings(), client)

	with caplog.at_level("WARNING", logger="app.oauth"), pytest.raises(OAuthFailedError):
		await provider.exchange_code("secret-code", "secret-verifier")

	assert any(record.operation == "token_exchange" and record.event == "oauth_failure" for record in caplog.records)
	assert "secret-code" not in caplog.text
	assert "secret-verifier" not in caplog.text


@pytest.mark.asyncio
async def test_provider_logs_userinfo_failure_without_sensitive_values(caplog: pytest.LogCaptureFixture) -> None:
	client = SimpleNamespace(get=AsyncMock(return_value=_HttpResponse(500, {})))
	provider = GoogleOAuthProvider(_settings(), client)

	with caplog.at_level("WARNING", logger="app.oauth"), pytest.raises(OAuthFailedError):
		await provider.fetch_userinfo("secret-access-token")

	assert any(record.operation == "userinfo" and record.event == "oauth_failure" for record in caplog.records)
	assert "secret-access-token" not in caplog.text


@pytest.mark.asyncio
async def test_provider_rejects_id_token_with_wrong_nonce() -> None:
	settings = _settings()
	token, jwks = _signed_id_token(settings, "expected")
	client = _OAuthHttpClient({}, {}, jwks)
	provider = GoogleOAuthProvider(settings, client)

	with pytest.raises(OAuthFailedError):
		await provider.verify_id_token(token, "wrong")


@pytest.mark.asyncio
async def test_provider_logs_id_token_verification_failure_without_sensitive_values(
	caplog: pytest.LogCaptureFixture,
) -> None:
	settings = _settings()
	token, jwks = _signed_id_token(settings, "expected")
	provider = GoogleOAuthProvider(settings, _OAuthHttpClient({}, {}, jwks))

	with caplog.at_level("WARNING", logger="app.oauth"), pytest.raises(OAuthFailedError):
		await provider.verify_id_token(token, "wrong")

	assert any(record.operation == "id_token_verify" and record.event == "oauth_failure" for record in caplog.records)
	assert token not in caplog.text


@pytest.mark.asyncio
async def test_provider_logs_jwks_failure_without_sensitive_values(caplog: pytest.LogCaptureFixture) -> None:
	settings = _settings(google_jwks_uri="https://jwks.example.test/unique")
	client = SimpleNamespace(get=AsyncMock(return_value=_HttpResponse(500, {})))
	provider = GoogleOAuthProvider(settings, client)

	with caplog.at_level("WARNING", logger="app.oauth"), pytest.raises(OAuthFailedError):
		await provider._get_jwks()

	assert any(record.operation == "jwks" and record.event == "oauth_failure" for record in caplog.records)


@pytest.mark.asyncio
async def test_provider_rejects_id_token_with_wrong_audience() -> None:
	settings = _settings()
	token, jwks = _signed_id_token(settings, "nonce", audience="other-client")
	provider = GoogleOAuthProvider(settings, _OAuthHttpClient({}, {}, jwks))

	with pytest.raises(OAuthFailedError):
		await provider.verify_id_token(token, "nonce")


@pytest.mark.asyncio
async def test_provider_rejects_multiple_audience_with_wrong_azp() -> None:
	settings = _settings()
	token, jwks = _signed_id_token(
		settings,
		"nonce",
		audience=[settings.google_client_id, "other-client"],
		azp="other-client",
	)
	provider = GoogleOAuthProvider(settings, _OAuthHttpClient({}, {}, jwks))

	with pytest.raises(OAuthFailedError):
		await provider.verify_id_token(token, "nonce")


@pytest.mark.asyncio
async def test_provider_accepts_multiple_audience_with_matching_azp() -> None:
	settings = _settings(google_jwks_uri="https://jwks.example.test/certs/matching")
	token, jwks = _signed_id_token(
		settings,
		"nonce",
		audience=[settings.google_client_id, "other-client"],
		azp=settings.google_client_id,
	)
	provider = GoogleOAuthProvider(settings, _OAuthHttpClient({}, {}, jwks))

	claims = await provider.verify_id_token(token, "nonce")

	assert claims.sub == "google-sub"


@pytest.mark.asyncio
async def test_oauth_start_saves_state_and_pkce_cookie(monkeypatch: pytest.MonkeyPatch) -> None:
	settings = _settings()
	save_state = AsyncMock()
	monkeypatch.setattr(auth_service.redis_store, "save_oauth_state", save_state)
	response = Response()

	result = await auth_service.oauth_start("/projects/1", response=response, settings=settings)

	save_state.assert_awaited_once()
	state, redirect, verifier, nonce, ttl = save_state.await_args.args
	assert state == result.state
	assert redirect == "/projects/1"
	assert ttl == settings.oauth_state_ttl_seconds
	query = parse_qs(urlparse(result.authorize_url).query)
	expected_challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
	assert query["code_challenge"] == [expected_challenge]
	assert query["nonce"] == [nonce]
	assert any(
		settings.cookie_name_oauth_state.encode() in value
		for key, value in response.raw_headers
		if key == b"set-cookie"
	)


@pytest.mark.asyncio
async def test_oauth_start_applies_rate_limit_to_request_ip(monkeypatch: pytest.MonkeyPatch) -> None:
	settings = _settings()
	check_rate_limit = AsyncMock(return_value=1)
	monkeypatch.setattr(auth_service.redis_store, "check_rate_limit", check_rate_limit)
	monkeypatch.setattr(auth_service.redis_store, "save_oauth_state", AsyncMock())

	await auth_service.oauth_start("/dashboard", request=_request(), response=Response(), settings=settings)

	check_rate_limit.assert_awaited_once_with(
		"oauth_start", "127.0.0.1", settings.rate_limit_oauth_max_requests, settings.rate_limit_oauth_window_seconds
	)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["start", "callback", "exchange"])
async def test_oauth_rate_limit_rejects_excess_requests(operation: str, monkeypatch: pytest.MonkeyPatch) -> None:
	settings = _settings(auth_mode="jwt")
	monkeypatch.setattr(
		auth_service.redis_store, "check_rate_limit", AsyncMock(return_value=settings.rate_limit_oauth_max_requests + 1)
	)

	with pytest.raises(TooManyAttemptsError):
		if operation == "start":
			await auth_service.oauth_start("/dashboard", request=_request(), response=Response(), settings=settings)
		elif operation == "callback":
			await auth_service.oauth_callback("code", "state", "state", _request(), Response(), settings=settings)
		else:
			await auth_service.oauth_exchange("code", _request(), Response(), settings=settings)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["start", "callback", "exchange"])
async def test_oauth_rate_limit_redis_failure_returns_service_unavailable(
	operation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
	settings = _settings(auth_mode="jwt")
	monkeypatch.setattr(
		auth_service.redis_store, "check_rate_limit", AsyncMock(side_effect=RuntimeError("redis unavailable"))
	)

	with pytest.raises(ServiceUnavailableError):
		if operation == "start":
			await auth_service.oauth_start("/dashboard", request=_request(), response=Response(), settings=settings)
		elif operation == "callback":
			await auth_service.oauth_callback("code", "state", "state", _request(), Response(), settings=settings)
		else:
			await auth_service.oauth_exchange("code", _request(), Response(), settings=settings)


@pytest.mark.asyncio
async def test_oauth_callback_rejects_state_cookie_mismatch() -> None:
	with pytest.raises(InvalidStateError):
		await auth_service.oauth_callback("code", "state", "different", _request(), Response())


@pytest.mark.asyncio
async def test_oauth_callback_consumes_state_before_rejecting_missing_code(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	consume_state = AsyncMock(return_value=OAuthStateData("/dashboard", "verifier", "nonce", None))
	monkeypatch.setattr(auth_service.redis_store, "consume_oauth_state", consume_state)

	with pytest.raises(OAuthFailedError):
		await auth_service.oauth_callback(None, "state", "state", _request(), Response(), db=object())

	consume_state.assert_awaited_once_with("state")


@pytest.mark.asyncio
async def test_oauth_callback_session_logs_success_and_deletes_state_cookie(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	user = SimpleNamespace(id=uuid4(), email="alice@example.com", is_active=True)
	provider = SimpleNamespace(
		exchange_code=AsyncMock(return_value=OAuthTokenResponse("id", "access")),
		verify_id_token=AsyncMock(return_value=IdTokenClaims("sub", "alice@example.com", True, None, None)),
		fetch_userinfo=AsyncMock(return_value=GoogleUserInfo("sub", "alice@example.com", True)),
	)
	monkeypatch.setattr(
		auth_service.redis_store,
		"consume_oauth_state",
		AsyncMock(return_value=OAuthStateData("/dashboard", "verifier", "nonce", None)),
	)
	monkeypatch.setattr(auth_service, "_resolve_or_create_user", AsyncMock(return_value=user))
	login_history = AsyncMock()
	monkeypatch.setattr(auth_service.login_history_repository, "create", login_history)
	db = SimpleNamespace(commit=AsyncMock())
	login = AsyncMock()
	strategy = SimpleNamespace(mode="session", login=login)
	response = Response()

	result = await auth_service.oauth_callback(
		"code",
		"state",
		"state",
		_request(),
		response,
		db=db,
		settings=_settings(auth_mode="session"),
		provider=provider,
		strategy=strategy,
	)

	assert result.auth_mode == "session"
	assert result.redirect_to == "/dashboard"
	login.assert_awaited_once()
	login_history.assert_awaited_once()
	assert any(
		b"cerberus_oauth_state=" in value and b"Max-Age=0" in value
		for key, value in response.raw_headers
		if key == b"set-cookie"
	)


@pytest.mark.asyncio
async def test_oauth_callback_rejects_inactive_resolved_user(monkeypatch: pytest.MonkeyPatch) -> None:
	user = SimpleNamespace(id=uuid4(), email="alice@example.com", is_active=False)
	provider = SimpleNamespace(
		exchange_code=AsyncMock(return_value=OAuthTokenResponse("id", "access")),
		verify_id_token=AsyncMock(return_value=IdTokenClaims("sub", user.email, True, None, None)),
		fetch_userinfo=AsyncMock(return_value=GoogleUserInfo("sub", user.email, True)),
	)
	monkeypatch.setattr(
		auth_service.redis_store,
		"consume_oauth_state",
		AsyncMock(return_value=OAuthStateData("/dashboard", "verifier", "nonce", None)),
	)
	monkeypatch.setattr(auth_service, "_resolve_or_create_user", AsyncMock(return_value=user))
	login = AsyncMock()

	with pytest.raises(UserInactiveError):
		await auth_service.oauth_callback(
			"code",
			"state",
			"state",
			_request(),
			Response(),
			db=SimpleNamespace(commit=AsyncMock()),
			settings=_settings(),
			provider=provider,
			strategy=SimpleNamespace(mode="session", login=login),
		)
	login.assert_not_awaited()


@pytest.mark.asyncio
async def test_oauth_callback_rolls_back_login_when_history_recording_fails(monkeypatch: pytest.MonkeyPatch) -> None:
	user = SimpleNamespace(id=uuid4(), email="alice@example.com", is_active=True)
	provider = SimpleNamespace(
		exchange_code=AsyncMock(return_value=OAuthTokenResponse("id", "access")),
		verify_id_token=AsyncMock(return_value=IdTokenClaims("sub", user.email, True, None, None)),
		fetch_userinfo=AsyncMock(return_value=GoogleUserInfo("sub", user.email, True)),
	)
	monkeypatch.setattr(
		auth_service.redis_store,
		"consume_oauth_state",
		AsyncMock(return_value=OAuthStateData("/dashboard", "verifier", "nonce", None)),
	)
	monkeypatch.setattr(auth_service, "_resolve_or_create_user", AsyncMock(return_value=user))
	monkeypatch.setattr(
		auth_service.login_history_repository,
		"create",
		AsyncMock(side_effect=RuntimeError("history unavailable")),
	)
	login_result = LoginResult("session", csrf_token="csrf", expires_in=900, session_id="session-id")
	login = AsyncMock(return_value=login_result)
	rollback = AsyncMock()
	response = Response()

	with pytest.raises(ServiceUnavailableError):
		await auth_service.oauth_callback(
			"code",
			"state",
			"state",
			_request(),
			response,
			db=SimpleNamespace(commit=AsyncMock()),
			settings=_settings(auth_mode="session"),
			provider=provider,
			strategy=SimpleNamespace(mode="session", login=login, rollback_login=rollback),
		)
	rollback.assert_awaited_once_with(user, login_result, response)
	assert any(b"cerberus_oauth_state=" in value and b"Max-Age=0" in value for key, value in response.raw_headers)


@pytest.mark.asyncio
async def test_oauth_callback_jwt_issues_handoff_without_recording_history(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	user = SimpleNamespace(id=uuid4(), email="alice@example.com", is_active=True)
	provider = SimpleNamespace(
		exchange_code=AsyncMock(return_value=OAuthTokenResponse("id", "access")),
		verify_id_token=AsyncMock(return_value=IdTokenClaims("sub", "alice@example.com", True, None, None)),
		fetch_userinfo=AsyncMock(return_value=GoogleUserInfo("sub", "alice@example.com", True)),
	)
	monkeypatch.setattr(
		auth_service.redis_store,
		"consume_oauth_state",
		AsyncMock(return_value=OAuthStateData("/projects/1", "verifier", "nonce", None)),
	)
	save_handoff = AsyncMock()
	monkeypatch.setattr(auth_service.redis_store, "save_oauth_handoff", save_handoff)
	monkeypatch.setattr(auth_service, "_resolve_or_create_user", AsyncMock(return_value=user))
	login_history = AsyncMock()
	monkeypatch.setattr(auth_service.login_history_repository, "create", login_history)
	db = SimpleNamespace(commit=AsyncMock())

	result = await auth_service.oauth_callback(
		"code",
		"state",
		"state",
		_request(),
		Response(),
		db=db,
		settings=_settings(auth_mode="jwt"),
		provider=provider,
	)

	assert result.auth_mode == "jwt"
	assert result.handoff_code
	save_handoff.assert_awaited_once_with(
		result.handoff_code, user.id, "/projects/1", _settings(auth_mode="jwt").oauth_handoff_ttl_seconds
	)
	login_history.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_user_rejects_unverified_email_link(monkeypatch: pytest.MonkeyPatch) -> None:
	existing = SimpleNamespace(id=uuid4(), email="alice@example.com", email_verified_at=None, is_active=True)
	monkeypatch.setattr(auth_service.oauth_account_repository, "get_by_provider_identity", AsyncMock(return_value=None))
	monkeypatch.setattr(auth_service.user_repository, "get_by_email", AsyncMock(return_value=existing))

	with pytest.raises(OAuthEmailUnverifiedError):
		await auth_service._resolve_or_create_user(
			object(), auth_service.GoogleUserInfo("sub", "alice@example.com", False)
		)


@pytest.mark.asyncio
async def test_resolve_user_links_verified_existing_email(monkeypatch: pytest.MonkeyPatch) -> None:
	user = SimpleNamespace(id=uuid4(), email="alice@example.com", email_verified_at=None, is_active=True)
	upsert = AsyncMock()
	mark_email_verified = AsyncMock()
	commit = AsyncMock()
	monkeypatch.setattr(auth_service.oauth_account_repository, "get_by_provider_identity", AsyncMock(return_value=None))
	monkeypatch.setattr(auth_service.user_repository, "get_by_email", AsyncMock(return_value=user))
	monkeypatch.setattr(auth_service.oauth_account_repository, "upsert", upsert)
	monkeypatch.setattr(auth_service.user_repository, "mark_email_verified", mark_email_verified)
	db = SimpleNamespace(commit=commit)

	result = await auth_service._resolve_or_create_user(db, GoogleUserInfo("google-sub", user.email, True))

	assert result is user
	assert upsert.await_args.args[1:] == (user.id, "google", "google-sub")
	mark_email_verified.assert_awaited_once_with(db, user.id)
	commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolve_user_does_not_update_already_verified_email(monkeypatch: pytest.MonkeyPatch) -> None:
	user = SimpleNamespace(id=uuid4(), email="alice@example.com", email_verified_at="verified", is_active=True)
	upsert = AsyncMock()
	mark_email_verified = AsyncMock()
	monkeypatch.setattr(auth_service.oauth_account_repository, "get_by_provider_identity", AsyncMock(return_value=None))
	monkeypatch.setattr(auth_service.user_repository, "get_by_email", AsyncMock(return_value=user))
	monkeypatch.setattr(auth_service.oauth_account_repository, "upsert", upsert)
	monkeypatch.setattr(auth_service.user_repository, "mark_email_verified", mark_email_verified)
	db = SimpleNamespace(commit=AsyncMock())

	result = await auth_service._resolve_or_create_user(db, GoogleUserInfo("google-sub", user.email, True))

	assert result is user
	mark_email_verified.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_user_rejects_inactive_oauth_account_user(monkeypatch: pytest.MonkeyPatch) -> None:
	user = SimpleNamespace(id=uuid4(), email="alice@example.com", is_active=False)
	account = SimpleNamespace(user=user, user_id=user.id)
	monkeypatch.setattr(
		auth_service.oauth_account_repository, "get_by_provider_identity", AsyncMock(return_value=account)
	)

	with pytest.raises(UserInactiveError):
		await auth_service._resolve_or_create_user(object(), GoogleUserInfo("google-sub", user.email, True))


@pytest.mark.asyncio
async def test_resolve_user_rejects_inactive_existing_email(monkeypatch: pytest.MonkeyPatch) -> None:
	user = SimpleNamespace(id=uuid4(), email="alice@example.com", is_active=False)
	monkeypatch.setattr(auth_service.oauth_account_repository, "get_by_provider_identity", AsyncMock(return_value=None))
	monkeypatch.setattr(auth_service.user_repository, "get_by_email", AsyncMock(return_value=user))

	with pytest.raises(UserInactiveError):
		await auth_service._resolve_or_create_user(object(), GoogleUserInfo("google-sub", user.email, True))


@pytest.mark.asyncio
async def test_resolve_user_rejects_inactive_newly_created_user(monkeypatch: pytest.MonkeyPatch) -> None:
	db = SimpleNamespace(commit=AsyncMock())
	user_id = uuid4()
	created_user = SimpleNamespace(id=user_id, email="new@example.com", is_active=False)
	monkeypatch.setattr(auth_service.oauth_account_repository, "get_by_provider_identity", AsyncMock(return_value=None))
	monkeypatch.setattr(auth_service.user_repository, "get_by_email", AsyncMock(return_value=None))
	monkeypatch.setattr(auth_service.user_repository, "create", AsyncMock(return_value=user_id))
	monkeypatch.setattr(auth_service.oauth_account_repository, "upsert", AsyncMock())
	monkeypatch.setattr(auth_service.user_repository, "mark_email_verified", AsyncMock())
	monkeypatch.setattr(auth_service.user_repository, "get_by_id", AsyncMock(return_value=created_user))

	with pytest.raises(UserInactiveError):
		await auth_service._resolve_or_create_user(db, GoogleUserInfo("google-sub", created_user.email, True))


@pytest.mark.asyncio
async def test_resolve_user_creates_google_user_and_profile(monkeypatch: pytest.MonkeyPatch) -> None:
	db = SimpleNamespace(commit=AsyncMock())
	user_id = uuid4()
	created_user = SimpleNamespace(id=user_id, email="new@example.com", is_active=True)
	create = AsyncMock(return_value=user_id)
	upsert = AsyncMock()
	mark_email_verified = AsyncMock()
	update_profile = AsyncMock()
	monkeypatch.setattr(auth_service.oauth_account_repository, "get_by_provider_identity", AsyncMock(return_value=None))
	monkeypatch.setattr(auth_service.user_repository, "get_by_email", AsyncMock(return_value=None))
	monkeypatch.setattr(auth_service.user_repository, "create", create)
	monkeypatch.setattr(auth_service.oauth_account_repository, "upsert", upsert)
	monkeypatch.setattr(auth_service.user_repository, "mark_email_verified", mark_email_verified)
	monkeypatch.setattr(auth_service.user_repository, "update_profile", update_profile)
	monkeypatch.setattr(auth_service.user_repository, "get_by_id", AsyncMock(return_value=created_user))

	result = await auth_service._resolve_or_create_user(
		db, GoogleUserInfo("google-sub", "new@example.com", True, "Alice", "Family")
	)

	assert result is created_user
	assert create.await_args.args[1].startswith("google_")
	create.assert_awaited_once_with(db, create.await_args.args[1], "new@example.com", None)
	upsert.assert_awaited_once_with(db, user_id, "google", "google-sub")
	mark_email_verified.assert_awaited_once_with(db, user_id)
	update_profile.assert_awaited_once_with(db, user_id, "Family", "Alice", None, None, None)
	db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_oauth_exchange_rejects_unknown_handoff() -> None:
	monkey = pytest.MonkeyPatch()
	monkey.setattr(auth_service.redis_store, "consume_oauth_handoff", AsyncMock(return_value=None))
	try:
		with pytest.raises(OAuthHandoffInvalidError):
			await auth_service.oauth_exchange(
				"code", _request(), Response(), db=object(), settings=_settings(auth_mode="jwt")
			)
	finally:
		monkey.undo()


@pytest.mark.asyncio
async def test_oauth_exchange_returns_token_and_records_login_history(monkeypatch: pytest.MonkeyPatch) -> None:
	user_id = uuid4()
	user = SimpleNamespace(id=user_id, email="alice@example.com", is_active=True)
	monkeypatch.setattr(
		auth_service.redis_store,
		"consume_oauth_handoff",
		AsyncMock(return_value=OAuthHandoffData(user_id, "/dashboard", None)),
	)
	monkeypatch.setattr(auth_service.user_repository, "get_by_id", AsyncMock(return_value=user))
	monkeypatch.setattr(
		auth_service,
		"get_auth_strategy",
		lambda: SimpleNamespace(
			mode="jwt", login=AsyncMock(return_value=SimpleNamespace(access_token="access", expires_in=900))
		),
	)
	login_history = AsyncMock()
	monkeypatch.setattr(auth_service.login_history_repository, "create", login_history)
	db = SimpleNamespace(commit=AsyncMock())

	result = await auth_service.oauth_exchange(
		"code", _request(), Response(), db=db, settings=_settings(auth_mode="jwt")
	)

	assert isinstance(result, OAuthExchangeResponse)
	assert result.access_token == "access"
	assert result.redirect_to == "/dashboard"
	login_history.assert_awaited_once()
	assert login_history.await_args.kwargs["login_identifier"] == user.email


@pytest.mark.asyncio
async def test_oauth_exchange_rolls_back_login_when_history_recording_fails(monkeypatch: pytest.MonkeyPatch) -> None:
	user_id = uuid4()
	user = SimpleNamespace(id=user_id, email="alice@example.com", is_active=True)
	monkeypatch.setattr(
		auth_service.redis_store,
		"consume_oauth_handoff",
		AsyncMock(return_value=OAuthHandoffData(user_id, "/dashboard", None)),
	)
	monkeypatch.setattr(auth_service.user_repository, "get_by_id", AsyncMock(return_value=user))
	monkeypatch.setattr(
		auth_service.login_history_repository,
		"create",
		AsyncMock(side_effect=RuntimeError("history unavailable")),
	)
	login_result = LoginResult("jwt", "access", "refresh", "csrf", 900)
	login = AsyncMock(return_value=login_result)
	rollback = AsyncMock()
	response = Response()

	with pytest.raises(ServiceUnavailableError):
		await auth_service.oauth_exchange(
			"code",
			_request(),
			response,
			db=SimpleNamespace(commit=AsyncMock()),
			settings=_settings(auth_mode="jwt"),
			strategy=SimpleNamespace(mode="jwt", login=login, rollback_login=rollback),
		)
	rollback.assert_awaited_once_with(user, login_result, response)
