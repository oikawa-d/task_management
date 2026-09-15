import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.auth.factory import get_auth_strategy
from app.core.config import get_backend_settings
from app.main import app
from app.repository import redis_store, user_repository
from app.repository.redis_store_common import key, token_hash
from app.service import email_verification_service
from fastapi.testclient import TestClient
from redis import Redis as SyncRedis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import OperationalError

ORIGIN = "http://localhost:5173"


@pytest.fixture(scope="module")
def auth_client(apply_migrations: None) -> TestClient:
	get_auth_strategy.cache_clear()
	with TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 50000)) as client:
		yield client
	get_auth_strategy.cache_clear()


@pytest.fixture(autouse=True)
def clean_auth_state(auth_client: TestClient) -> None:
	settings = get_backend_settings()
	redis = SyncRedis.from_url(settings.redis_url)
	redis.flushdb()
	auth_client.cookies.clear()
	yield
	redis.flushdb()
	redis.close()


@pytest.fixture
def mail_outbox(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, str]]:
	outbox: list[tuple[str, str, str]] = []

	async def record_verification(to: str, token: str, _expires_hours: int) -> None:
		outbox.append(("verification", to, token))

	async def record_password_reset(to: str, token: str, _expires_minutes: int) -> None:
		outbox.append(("password_reset", to, token))

	monkeypatch.setattr(email_verification_service.mail_service, "send_email_verification_mail", record_verification)
	monkeypatch.setattr(email_verification_service.mail_service, "send_password_reset_mail", record_password_reset)
	return outbox


def _register(client: TestClient, outbox: list[tuple[str, str, str]]) -> tuple[str, str, str]:
	identifier = uuid4().hex[:12]
	email = f"issue425-{identifier}@example.com"
	response = client.post(
		"/api/auth/register",
		headers={"Origin": ORIGIN},
		json={
			"username": f"u{identifier}",
			"email": email,
			"password": "OldPassw0rd!",
			"password_confirm": "OldPassw0rd!",
			"last_name": "山田",
			"first_name": "太郎",
			"last_name_kana": "ヤマダ",
			"first_name_kana": "タロウ",
			"birth_date": "1995-04-01",
		},
	)
	assert response.status_code == 201, response.text
	assert outbox and outbox[-1][0] == "verification"
	return response.json()["id"], email, outbox[-1][2]


def _error_code(response: object) -> str:
	return response.json()["error"]["code"]  # type: ignore[union-attr]


def _redis() -> SyncRedis:
	return SyncRedis.from_url(get_backend_settings().redis_url)


def _post_with_cookies(client: TestClient, path: str, headers: dict[str, str], cookies: dict[str, str]) -> object:
	request_headers = {**headers, "Cookie": "; ".join(f"{name}={value}" for name, value in cookies.items())}
	return client.post(path, headers=request_headers)


def test_email_verification_flow_is_one_time_and_enables_login(
	auth_client: TestClient, mail_outbox: list[tuple[str, str, str]]
) -> None:
	_, email, token = _register(auth_client, mail_outbox)

	verified = auth_client.post("/api/auth/verify-email", json={"token": token})
	assert verified.status_code == 204

	reused = auth_client.post("/api/auth/verify-email", json={"token": token})
	assert reused.status_code == 400
	assert _error_code(reused) == "INVALID_VERIFY_TOKEN"

	login = auth_client.post(
		"/api/auth/login",
		headers={"Origin": ORIGIN},
		json={"identifier": email, "password": "OldPassw0rd!"},
	)
	assert login.status_code in (200, 204), login.text


def test_email_verification_expiry_is_rejected_at_api_boundary(
	auth_client: TestClient, mail_outbox: list[tuple[str, str, str]]
) -> None:
	_, _, token = _register(auth_client, mail_outbox)
	redis = _redis()
	try:
		settings = get_backend_settings()
		redis.expire(key("emailverify", settings.redis_key_prefix, token_hash(token)), 1)
		time.sleep(1.2)
	finally:
		redis.close()

	response = auth_client.post("/api/auth/verify-email", json={"token": token})
	assert response.status_code == 400
	assert _error_code(response) == "INVALID_VERIFY_TOKEN"


def test_resend_replaces_old_token_and_new_token_verifies(
	auth_client: TestClient, mail_outbox: list[tuple[str, str, str]]
) -> None:
	user_id, _, old_token = _register(auth_client, mail_outbox)
	settings = get_backend_settings()
	redis = _redis()
	try:
		redis.delete(key("emailverify_sent", settings.redis_key_prefix, user_id))
	finally:
		redis.close()

	resend = auth_client.post(
		"/api/auth/verify-email/resend",
		json={"email": mail_outbox[0][1]},
	)
	assert resend.status_code == 202
	assert len(mail_outbox) == 2
	new_token = mail_outbox[-1][2]

	old_response = auth_client.post("/api/auth/verify-email", json={"token": old_token})
	assert old_response.status_code == 400
	assert _error_code(old_response) == "INVALID_VERIFY_TOKEN"
	new_response = auth_client.post("/api/auth/verify-email", json={"token": new_token})
	assert new_response.status_code == 204


def test_password_forgot_reset_flow_consumes_token_and_revokes_auth_state(
	auth_client: TestClient, mail_outbox: list[tuple[str, str, str]]
) -> None:
	_, email, verification_token = _register(auth_client, mail_outbox)
	auth_client.post("/api/auth/verify-email", json={"token": verification_token})
	login = auth_client.post(
		"/api/auth/login",
		headers={"Origin": ORIGIN},
		json={"identifier": email, "password": "OldPassw0rd!"},
	)
	assert login.status_code in (200, 204), login.text
	old_refresh = auth_client.cookies.get(get_backend_settings().cookie_name_refresh)
	old_csrf = auth_client.cookies.get(get_backend_settings().cookie_name_csrf)

	forgot = auth_client.post("/api/auth/password/forgot", json={"email": email})
	assert forgot.status_code == 202
	reset_token = mail_outbox[-1][2]
	redis = _redis()
	try:
		redis.expire(key("pwreset", get_backend_settings().redis_key_prefix, token_hash(reset_token)), 1)
		time.sleep(1.2)
	finally:
		redis.close()
	expired = auth_client.post(
		"/api/auth/password/reset",
		json={"token": reset_token, "new_password": "NewPassw0rd!", "password_confirm": "NewPassw0rd!"},
	)
	assert expired.status_code == 400
	assert _error_code(expired) == "INVALID_RESET_TOKEN"

	forgot = auth_client.post("/api/auth/password/forgot", json={"email": email})
	assert forgot.status_code == 202
	reset_token = mail_outbox[-1][2]

	reset = auth_client.post(
		"/api/auth/password/reset",
		json={"token": reset_token, "new_password": "NewPassw0rd!", "password_confirm": "NewPassw0rd!"},
	)
	assert reset.status_code == 204
	assert (
		auth_client.post(
			"/api/auth/password/reset",
			json={"token": reset_token, "new_password": "OtherPassw0rd!", "password_confirm": "OtherPassw0rd!"},
		).status_code
		== 400
	)

	settings = get_backend_settings()
	if settings.auth_mode == "jwt":
		assert old_refresh is not None and old_csrf is not None
		revoked = _post_with_cookies(
			auth_client,
			"/api/auth/refresh",
			headers={"Origin": ORIGIN, "X-CSRF-Token": old_csrf},
			cookies={settings.cookie_name_refresh: old_refresh, settings.cookie_name_csrf: old_csrf},
		)
		assert revoked.status_code == 401
		assert _error_code(revoked) == "TOKEN_REVOKED"
	else:
		assert auth_client.get("/api/auth/me").status_code == 401

	assert (
		auth_client.post(
			"/api/auth/login",
			headers={"Origin": ORIGIN},
			json={"identifier": email, "password": "OldPassw0rd!"},
		).status_code
		== 401
	)
	new_login = auth_client.post(
		"/api/auth/login",
		headers={"Origin": ORIGIN},
		json={"identifier": email, "password": "NewPassw0rd!"},
	)
	assert new_login.status_code in (200, 204), new_login.text


def test_jwt_refresh_rotation_rejects_missing_and_reused_tokens(
	auth_client: TestClient, mail_outbox: list[tuple[str, str, str]]
) -> None:
	settings = get_backend_settings()
	if settings.auth_mode != "jwt":
		pytest.skip("refreshはjwtモードのみのAPI")
	_, email, verification_token = _register(auth_client, mail_outbox)
	auth_client.post("/api/auth/verify-email", json={"token": verification_token})
	auth_client.post(
		"/api/auth/login",
		headers={"Origin": ORIGIN},
		json={"identifier": email, "password": "OldPassw0rd!"},
	)
	old_refresh = auth_client.cookies.get(settings.cookie_name_refresh)
	old_csrf = auth_client.cookies.get(settings.cookie_name_csrf)
	assert old_refresh is not None and old_csrf is not None

	missing = _post_with_cookies(
		auth_client,
		"/api/auth/refresh",
		headers={"Origin": ORIGIN, "X-CSRF-Token": "csrf-for-no-cookie"},
		cookies={settings.cookie_name_csrf: "csrf-for-no-cookie"},
	)
	assert missing.status_code == 401
	assert _error_code(missing) == "TOKEN_INVALID"

	rotated = auth_client.post(
		"/api/auth/refresh",
		headers={"Origin": ORIGIN, "X-CSRF-Token": old_csrf},
	)
	assert rotated.status_code == 200
	new_refresh = auth_client.cookies.get(settings.cookie_name_refresh)
	new_csrf = auth_client.cookies.get(settings.cookie_name_csrf)
	assert new_refresh and new_refresh != old_refresh
	assert new_csrf and new_csrf != old_csrf

	redis = _redis()
	try:
		assert redis.get(key("refresh", settings.redis_key_prefix, token_hash(old_refresh))) is None
		assert redis.get(key("refresh_used", settings.redis_key_prefix, token_hash(old_refresh))) is not None
	finally:
		redis.close()

	reused = _post_with_cookies(
		auth_client,
		"/api/auth/refresh",
		headers={"Origin": ORIGIN, "X-CSRF-Token": old_csrf},
		cookies={settings.cookie_name_refresh: old_refresh, settings.cookie_name_csrf: old_csrf},
	)
	assert reused.status_code == 401
	assert _error_code(reused) == "TOKEN_REVOKED"
	family_revoked = _post_with_cookies(
		auth_client,
		"/api/auth/refresh",
		headers={"Origin": ORIGIN, "X-CSRF-Token": new_csrf},
		cookies={settings.cookie_name_refresh: new_refresh, settings.cookie_name_csrf: new_csrf},
	)
	assert family_revoked.status_code == 401
	assert _error_code(family_revoked) == "TOKEN_REVOKED"


def test_verify_email_redis_failure_is_fail_closed(auth_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	async def fail_consume(_token: str) -> None:
		raise RedisConnectionError("redis unavailable")

	monkeypatch.setattr(redis_store, "consume_email_verify_token", fail_consume)
	response = auth_client.post("/api/auth/verify-email", json={"token": "valid-looking-token"})
	assert response.status_code == 503
	assert _error_code(response) == "SERVICE_UNAVAILABLE"


def test_verify_email_db_failure_is_fail_closed(
	auth_client: TestClient, mail_outbox: list[tuple[str, str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
	_, _, token = _register(auth_client, mail_outbox)

	async def fail_update(*_args: object, **_kwargs: object) -> None:
		raise OperationalError("CALL sp_verify_user_email", {}, SimpleNamespace(sqlstate="08006"))

	monkeypatch.setattr(user_repository, "mark_email_verified", fail_update)
	response = auth_client.post("/api/auth/verify-email", json={"token": token})
	assert response.status_code == 503
	assert _error_code(response) == "SERVICE_UNAVAILABLE"


def test_password_reset_redis_failure_is_fail_closed(
	auth_client: TestClient, mail_outbox: list[tuple[str, str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
	_, email, verification_token = _register(auth_client, mail_outbox)
	auth_client.post("/api/auth/verify-email", json={"token": verification_token})
	auth_client.post("/api/auth/password/forgot", json={"email": email})
	reset_token = next(token for kind, _, token in mail_outbox if kind == "password_reset")
	update_mock = AsyncMock()

	async def fail_revoke(_user_id: object) -> int:
		raise RedisConnectionError("redis unavailable")

	monkeypatch.setattr(redis_store, "revoke_all_refresh_tokens", fail_revoke)
	monkeypatch.setattr(user_repository, "update_password", update_mock)
	response = auth_client.post(
		"/api/auth/password/reset",
		json={"token": reset_token, "new_password": "NewPassw0rd!", "password_confirm": "NewPassw0rd!"},
	)
	assert response.status_code == 503
	assert _error_code(response) == "SERVICE_UNAVAILABLE"
	assert not update_mock.called
