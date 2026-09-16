"""Issue #429: register/login/logout/me のrouter→service→repository→DB/Redis結合テスト。

参照設計書:
- docs/detailed_design/api/auth/01_post_auth_register.md §12（結合テスト6〜8・10相当）
- docs/detailed_design/api/auth/02_post_auth_login.md §12（結合テスト7〜12相当）
- docs/detailed_design/api/auth/03_post_auth_logout.md §12（結合テスト6〜10相当）
- docs/detailed_design/api/auth/04_get_auth_me.md §12（結合テスト7〜10相当）

`api/tests/api/routers/test_auth_router.py`はservice層をモックしたrouter契約テストのため、
本ファイルは`app.main.app`をそのまま使い、DB/Redisをモックせずに検証する。
AUTH_MODEはCI（`.github/workflows/ci.yml`のbackend-testマトリクス）と同様、プロセス起動時の
環境変数で固定されるため、モード固有の検証は`get_backend_settings().auth_mode`で分岐する。

GET /api/auth/config は実DB/Redisへ依存しないAPIであり、
`api/tests/api/routers/test_auth_router.py`の`test_config_*`群が既に実設定・実レスポンスで
結合検証済みのため、本ファイルには追加しない（設計書§9・§13にも外部ストア依存なしと明記）。

4エンドポイントを1ファイルにまとめているのは、`api/tests/conftest.py`の`apply_migrations`
（モジュールスコープでスキーマの作成・全downgradeを行う）とTestClientの専用ポータルに
紐づく`app.db.get_db_engine()`のキャッシュ済み接続を、同一プロセス内で複数モジュールに
分割すると、後続モジュールのスキーマ再作成中に前段モジュールの接続がOID不整合で壊れるため
（`tests/integration/conftest.py`のイベントループに関する注意も参照）。

テスト関数はすべて`async def`とし、DB検証は`db_session`・Redis検証は`redis_conn`を使う。
"""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from app.core.config import get_backend_settings
from app.repository import (
	login_history_repository,
	redis_store,
	redis_store_auth,
	redis_store_session,
	user_repository,
)
from app.repository.redis_store_common import token_hash
from app.service import email_verification_service, mail_service
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from tests.integration.conftest import ALLOWED_ORIGIN, register_payload, register_verified_user, unique_suffix


def _login_body(identifier: str, password: str) -> dict[str, str]:
	return {"identifier": identifier, "password": password}


def _login(client: TestClient, username: str, password: str) -> Any:
	response = client.post("/api/auth/login", json=_login_body(username, password), headers={"Origin": ALLOWED_ORIGIN})
	assert response.status_code in (200, 204), response.text
	return response


def _auth_headers_for(response: Any) -> dict[str, str]:
	if get_backend_settings().auth_mode == "jwt":
		return {"Authorization": f"Bearer {response.json()['access_token']}"}
	return {}


def _csrf_header(client: TestClient, settings: Any) -> dict[str, str]:
	"""logoutのCSRF検証用ヘッダを、実際にCookieへ保存されたcerberus_csrf値から組み立てる。"""
	csrf_value = client.cookies.get(settings.cookie_name_csrf)
	return {} if csrf_value is None else {"X-CSRF-Token": csrf_value}


# --- register -----------------------------------------------------------------


async def test_register_endpoint_returns_201_without_auth_cookie(
	client: TestClient, created_user_ids: list[uuid.UUID], db_session: AsyncSession
) -> None:
	"""結合6: 実DBへINSERTし、Cookie/トークンを発行せず、email_verified_atがNULLのまま201を返す。"""
	suffix = unique_suffix()
	username = f"it{suffix}"
	email = f"{username}@example.com"

	response = client.post(
		"/api/auth/register", json=register_payload(username, email), headers={"Origin": ALLOWED_ORIGIN}
	)

	assert response.status_code == 201, response.text
	body = response.json()
	assert body["email"] == email
	assert "set-cookie" not in response.headers
	created_user_ids.append(uuid.UUID(body["id"]))

	user = await user_repository.get_by_login_identifier(db_session, username)
	assert user is not None
	assert user.email_verified_at is None


async def test_register_endpoint_sends_verification_mail(
	client: TestClient,
	created_user_ids: list[uuid.UUID],
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""結合9: register経由で確認メールの予約・実行とSMTP送信が各1回行われる。"""
	suffix = unique_suffix()
	username = f"it{suffix}"
	email = f"{username}@example.com"
	send_mail_mock = AsyncMock(wraps=mail_service.send_email_verification_mail)
	smtp_send_mock = AsyncMock()
	monkeypatch.setattr(email_verification_service.mail_service, "send_email_verification_mail", send_mail_mock)
	monkeypatch.setattr(mail_service.aiosmtplib, "send", smtp_send_mock)

	response = client.post(
		"/api/auth/register", json=register_payload(username, email), headers={"Origin": ALLOWED_ORIGIN}
	)

	assert response.status_code == 201, response.text
	created_user_ids.append(uuid.UUID(response.json()["id"]))
	send_mail_mock.assert_awaited_once()
	smtp_send_mock.assert_awaited_once()
	mail_call = send_mail_mock.await_args
	smtp_call = smtp_send_mock.await_args
	assert mail_call is not None
	assert smtp_call is not None
	assert mail_call.args[0] == email
	assert mail_call.args[1]
	assert mail_call.args[2] == get_backend_settings().email_verify_ttl_seconds // 3600
	assert smtp_call.args[0]["To"] == email


async def test_register_endpoint_invalid_origin_creates_no_row(client: TestClient, db_session: AsyncSession) -> None:
	"""結合7: Origin不一致は403を返し、DBへ行を作成しない。"""
	suffix = unique_suffix()
	username = f"it{suffix}"

	response = client.post(
		"/api/auth/register",
		json=register_payload(username, f"{username}@example.com"),
		headers={"Origin": "http://evil.example"},
	)

	assert response.status_code == 403
	assert response.json()["error"]["code"] == "CSRF_INVALID"
	assert await user_repository.get_by_login_identifier(db_session, username) is None


async def test_register_endpoint_duplicate_username_returns_409(
	client: TestClient, created_user_ids: list[uuid.UUID]
) -> None:
	"""結合8: 同一usernameでの再登録は409 DUPLICATE_USERNAMEとなり、行は1件のみ。"""
	suffix = unique_suffix()
	username = f"it{suffix}"
	first = client.post(
		"/api/auth/register",
		json=register_payload(username, f"{username}@example.com"),
		headers={"Origin": ALLOWED_ORIGIN},
	)
	assert first.status_code == 201
	created_user_ids.append(uuid.UUID(first.json()["id"]))

	second = client.post(
		"/api/auth/register",
		json=register_payload(username, f"{username}-2@example.com"),
		headers={"Origin": ALLOWED_ORIGIN},
	)

	assert second.status_code == 409
	assert second.json()["error"]["code"] == "DUPLICATE_USERNAME"


async def test_register_endpoint_stores_email_verify_token_in_redis(
	client: TestClient, created_user_ids: list[uuid.UUID], redis_conn: Redis
) -> None:
	"""結合10: 実Redisに`emailverify:{hash}`・`emailverify_current:{uid}`がTTL付きで作成される。"""
	suffix = unique_suffix()
	username = f"it{suffix}"

	response = client.post(
		"/api/auth/register",
		json=register_payload(username, f"{username}@example.com"),
		headers={"Origin": ALLOWED_ORIGIN},
	)
	assert response.status_code == 201
	user_id = uuid.UUID(response.json()["id"])
	created_user_ids.append(user_id)

	prefix = get_backend_settings().redis_key_prefix
	current_key = f"{prefix}emailverify_current:{user_id}"
	token_hash = await redis_conn.get(current_key)
	assert token_hash is not None
	token_key = f"{prefix}emailverify:{token_hash}"
	assert bool(await redis_conn.exists(token_key)) is True
	assert await redis_conn.ttl(token_key) > 0


async def test_password_reset_initial_concurrent_issue_has_one_winner(redis_conn: Redis) -> None:
	"""初回の同時発行はLua内CASで1件だけ成功し、勝者のtokenだけを保持する。"""
	user_id = uuid.uuid4()
	settings = get_backend_settings()
	prefix = settings.redis_key_prefix
	tokens = (f"reset-a-{uuid.uuid4().hex}", f"reset-b-{uuid.uuid4().hex}")
	try:
		results = await asyncio.gather(
			*(redis_store_auth.save_password_reset_token(redis_conn, prefix, token, user_id, 60) for token in tokens)
		)

		assert sorted(results) == [False, True]
		current_hash = await redis_conn.get(f"{prefix}pwreset_current:{user_id}")
		assert current_hash in {token_hash(token) for token in tokens}
		stored_tokens = [await redis_conn.exists(f"{prefix}pwreset:{token_hash(token)}") for token in tokens]
		assert stored_tokens.count(1) == 1
	finally:
		await redis_conn.delete(
			f"{prefix}pwreset_current:{user_id}",
			*(f"{prefix}pwreset:{token_hash(token)}" for token in tokens),
		)


async def test_register_endpoint_db_failure_creates_no_partial_row(
	client: TestClient, monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession
) -> None:
	"""結合（DB障害・部分更新なし）: PostgreSQL接続不能時は503を返し、usersへ行を残さない（fail-close）。"""
	suffix = unique_suffix()
	username = f"it{suffix}"

	async def _boom(*_args: Any, **_kwargs: Any) -> Any:
		raise OperationalError("CALL sp_register_user", {}, SimpleNamespace(sqlstate="08006"))

	monkeypatch.setattr(user_repository, "create", _boom)

	response = client.post(
		"/api/auth/register",
		json=register_payload(username, f"{username}@example.com"),
		headers={"Origin": ALLOWED_ORIGIN},
	)

	assert response.status_code == 503
	assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
	assert await user_repository.get_by_login_identifier(db_session, username) is None


# --- login ----------------------------------------------------------------------


async def test_login_endpoint_session_mode_success(
	client: TestClient, created_user_ids: list[uuid.UUID], db_session: AsyncSession, redis_conn: Redis
) -> None:
	"""結合7: AUTH_MODE=sessionの正常系。204・Set-Cookie(cerberus_sid/cerberus_csrf)・login_history成功行。"""
	if get_backend_settings().auth_mode != "session":
		pytest.skip("AUTH_MODE=sessionでのみ検証する（jwtはtest_login_endpoint_jwt_mode_successで検証）")

	user = await register_verified_user(client, created_user_ids, db_session)

	response = client.post(
		"/api/auth/login", json=_login_body(user["username"], user["password"]), headers={"Origin": ALLOWED_ORIGIN}
	)

	assert response.status_code == 204
	cookies = response.headers.get_list("set-cookie")
	assert any(cookie.startswith("cerberus_sid=") for cookie in cookies)
	assert any(cookie.startswith("cerberus_csrf=") for cookie in cookies)

	sid = response.cookies.get("cerberus_sid")
	assert sid is not None
	prefix = get_backend_settings().redis_key_prefix
	session = await redis_store_session.get_session(redis_conn, prefix, sid)
	assert session is not None
	assert str(session.user_id) == user["id"]

	rows = await login_history_repository.list_by_user_id(db_session, uuid.UUID(user["id"]), limit=10)
	assert any(row.success is True for row in rows)


async def test_login_endpoint_jwt_mode_success(
	client: TestClient, created_user_ids: list[uuid.UUID], db_session: AsyncSession, redis_conn: Redis
) -> None:
	"""結合8: AUTH_MODE=jwtの正常系。200 access_token・Set-Cookie(cerberus_rt/cerberus_csrf)・login_history成功行。"""
	if get_backend_settings().auth_mode != "jwt":
		pytest.skip("AUTH_MODE=jwtでのみ検証する（sessionはtest_login_endpoint_session_mode_successで検証）")

	user = await register_verified_user(client, created_user_ids, db_session)

	response = client.post(
		"/api/auth/login", json=_login_body(user["username"], user["password"]), headers={"Origin": ALLOWED_ORIGIN}
	)

	assert response.status_code == 200
	body = response.json()
	assert body["token_type"] == "bearer"
	assert body["access_token"]
	cookies = response.headers.get_list("set-cookie")
	assert any(cookie.startswith("cerberus_rt=") for cookie in cookies)
	assert any(cookie.startswith("cerberus_csrf=") for cookie in cookies)

	refresh_token = response.cookies.get("cerberus_rt")
	assert refresh_token is not None
	prefix = get_backend_settings().redis_key_prefix
	refresh_data = await redis_store_auth.get_refresh_token(redis_conn, prefix, refresh_token)
	assert refresh_data is not None
	assert str(refresh_data.user_id) == user["id"]

	rows = await login_history_repository.list_by_user_id(db_session, uuid.UUID(user["id"]), limit=10)
	assert any(row.success is True for row in rows)


async def test_login_endpoint_rate_limited_after_max_attempts(
	client: TestClient, created_user_ids: list[uuid.UUID], db_session: AsyncSession, redis_conn: Redis
) -> None:
	"""結合9: LOGIN_MAX_ATTEMPTS（既定5）回失敗すると429 TOO_MANY_ATTEMPTSを返す（実Redisでカウント）。"""
	user = await register_verified_user(client, created_user_ids, db_session)
	settings = get_backend_settings()

	for _ in range(settings.login_max_attempts):
		failed = client.post(
			"/api/auth/login",
			json=_login_body(user["username"], "WrongPassw0rd!"),
			headers={"Origin": ALLOWED_ORIGIN},
		)
		assert failed.status_code == 401

	locked = client.post(
		"/api/auth/login", json=_login_body(user["username"], user["password"]), headers={"Origin": ALLOWED_ORIGIN}
	)

	assert locked.status_code == 429
	assert locked.json()["error"]["code"] == "TOO_MANY_ATTEMPTS"
	assert "retry-after" in locked.headers

	prefix = get_backend_settings().redis_key_prefix
	async for key in redis_conn.scan_iter(match=f"{prefix}login_fail:*"):
		await redis_conn.delete(key)


async def test_login_endpoint_email_not_verified_rejected(
	client: TestClient, created_user_ids: list[uuid.UUID], db_session: AsyncSession
) -> None:
	"""結合10: email_verified_at IS NULLのユーザーは403 EMAIL_NOT_VERIFIEDとなり、login_historyに失敗理由が残る。"""
	suffix = unique_suffix()
	username = f"it{suffix}"
	register_response = client.post(
		"/api/auth/register",
		json=register_payload(username, f"{username}@example.com"),
		headers={"Origin": ALLOWED_ORIGIN},
	)
	assert register_response.status_code == 201
	user_id = uuid.UUID(register_response.json()["id"])
	created_user_ids.append(user_id)

	response = client.post(
		"/api/auth/login", json=_login_body(username, "Passw0rd!123"), headers={"Origin": ALLOWED_ORIGIN}
	)

	assert response.status_code == 403
	assert response.json()["error"]["code"] == "EMAIL_NOT_VERIFIED"

	rows = await login_history_repository.list_by_user_id(db_session, user_id, limit=10)
	assert any(row.success is False and row.failure_reason == "email_not_verified" for row in rows)


async def test_login_endpoint_user_inactive_rejected(
	client: TestClient, created_user_ids: list[uuid.UUID], db_session: AsyncSession
) -> None:
	"""結合11: is_active=falseのユーザーは403 USER_INACTIVEとなる。"""
	user = await register_verified_user(client, created_user_ids, db_session)
	await db_session.execute(text("UPDATE users SET is_active = false WHERE id = :id"), {"id": uuid.UUID(user["id"])})
	await db_session.commit()

	response = client.post(
		"/api/auth/login", json=_login_body(user["username"], user["password"]), headers={"Origin": ALLOWED_ORIGIN}
	)

	assert response.status_code == 403
	assert response.json()["error"]["code"] == "USER_INACTIVE"

	rows = await login_history_repository.list_by_user_id(db_session, uuid.UUID(user["id"]), limit=10)
	assert any(row.success is False and row.failure_reason == "user_inactive" for row in rows)


async def test_login_endpoint_invalid_origin_rejected(
	client: TestClient, created_user_ids: list[uuid.UUID], db_session: AsyncSession
) -> None:
	"""結合12: Origin不一致は403 CSRF_INVALIDとなり、認証状態を確立しない。"""
	user = await register_verified_user(client, created_user_ids, db_session)

	response = client.post(
		"/api/auth/login",
		json=_login_body(user["username"], user["password"]),
		headers={"Origin": "http://evil.example"},
	)

	assert response.status_code == 403
	assert response.json()["error"]["code"] == "CSRF_INVALID"
	assert "set-cookie" not in response.headers


async def test_login_endpoint_history_failure_rolls_back_auth_state(
	client: TestClient,
	monkeypatch: pytest.MonkeyPatch,
	created_user_ids: list[uuid.UUID],
	db_session: AsyncSession,
	redis_conn: Redis,
) -> None:
	"""結合（部分更新なし）: login_history INSERT失敗時はStrategyのRedis状態をrollback_loginで取り消す。

	auth_service.loginはstrategy.loginで認証状態（session/refresh）を確立した後にlogin_history
	INSERTを行う。INSERT失敗時は`rollback_login`で確立済みの認証状態を取り消してから503を返す設計
	（02_post_auth_login.md §6.2）であり、Redisに認証済みセッション/リフレッシュトークンが
	取り残されないことを確認する。
	"""
	user = await register_verified_user(client, created_user_ids, db_session)

	async def _boom(*_args: Any, **_kwargs: Any) -> None:
		raise OperationalError("CALL sp_record_login_history", {}, SimpleNamespace(sqlstate="08006"))

	monkeypatch.setattr(login_history_repository, "create", _boom)

	response = client.post(
		"/api/auth/login", json=_login_body(user["username"], user["password"]), headers={"Origin": ALLOWED_ORIGIN}
	)

	assert response.status_code == 503
	assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"

	# エラーハンドラは新規Responseを組み立てて返すため、失敗応答のSet-Cookieの有無ではなく、
	# rollback_loginが取り消すはずの実Redis側の集合キーを直接確認する（user_id起点）。
	settings = get_backend_settings()
	prefix = settings.redis_key_prefix
	set_name = (
		f"{prefix}user_sessions:{user['id']}"
		if settings.auth_mode == "session"
		else f"{prefix}user_refresh:{user['id']}"
	)
	assert await redis_conn.smembers(set_name) in (set(), frozenset())


# --- logout -----------------------------------------------------------------------


async def test_logout_endpoint_success_removes_auth_state(
	client: TestClient, created_user_ids: list[uuid.UUID], db_session: AsyncSession, redis_conn: Redis
) -> None:
	"""結合6・7: ログイン済み状態からのログアウトは204を返し、実Redisの認証状態を削除する。"""
	user = await register_verified_user(client, created_user_ids, db_session)
	login_response = _login(client, user["username"], user["password"])
	settings = get_backend_settings()
	prefix = settings.redis_key_prefix

	response = client.post("/api/auth/logout", headers={"Origin": ALLOWED_ORIGIN, **_csrf_header(client, settings)})

	assert response.status_code == 204
	if settings.auth_mode == "session":
		sid = login_response.cookies.get("cerberus_sid")
		assert sid is not None
		assert await redis_store_session.get_session(redis_conn, prefix, sid) is None
	else:
		rt = login_response.cookies.get("cerberus_rt")
		assert rt is not None
		assert await redis_store_auth.get_refresh_token(redis_conn, prefix, rt) is None


async def test_logout_endpoint_idempotent_without_cookie(client: TestClient) -> None:
	"""結合8: 未ログイン状態（Cookie無し）でも204を返す（冪等設計）。"""
	response = client.post("/api/auth/logout", headers={"Origin": ALLOWED_ORIGIN})

	assert response.status_code == 204


async def test_logout_endpoint_missing_csrf_header_rejected(
	client: TestClient, created_user_ids: list[uuid.UUID], db_session: AsyncSession
) -> None:
	"""結合9: 対象Cookieが存在するのにX-CSRF-Tokenが無い場合は403 CSRF_INVALIDとなる。"""
	settings = get_backend_settings()
	user = await register_verified_user(client, created_user_ids, db_session)
	_login(client, user["username"], user["password"])

	response = client.post("/api/auth/logout", headers={"Origin": ALLOWED_ORIGIN})

	assert response.status_code == 403
	assert response.json()["error"]["code"] == "CSRF_INVALID"

	# 検証に失敗しても実Redis側の認証状態は残り続けるため、後始末として明示的にログアウトする。
	client.post("/api/auth/logout", headers={"Origin": ALLOWED_ORIGIN, **_csrf_header(client, settings)})


async def test_logout_endpoint_invalid_origin_rejected(
	client: TestClient, created_user_ids: list[uuid.UUID], db_session: AsyncSession
) -> None:
	"""結合10: Origin不一致は403 CSRF_INVALIDとなる。"""
	settings = get_backend_settings()
	user = await register_verified_user(client, created_user_ids, db_session)
	_login(client, user["username"], user["password"])

	response = client.post("/api/auth/logout", headers={"Origin": "http://evil.example"})

	assert response.status_code == 403
	assert response.json()["error"]["code"] == "CSRF_INVALID"

	client.post("/api/auth/logout", headers={"Origin": ALLOWED_ORIGIN, **_csrf_header(client, settings)})


# --- me -----------------------------------------------------------------------------


async def test_me_endpoint_success_returns_profile_with_auth_mode(
	client: TestClient, created_user_ids: list[uuid.UUID], db_session: AsyncSession, redis_conn: Redis
) -> None:
	"""結合7・8: ログイン済み状態でGET /api/auth/meが200・現在のauth_modeを含むプロフィールを返す。"""
	settings = get_backend_settings()
	user = await register_verified_user(client, created_user_ids, db_session)
	login_response = _login(client, user["username"], user["password"])

	response = client.get("/api/auth/me", headers=_auth_headers_for(login_response))

	assert response.status_code == 200
	body = response.json()
	assert body["username"] == user["username"]
	assert body["auth_mode"] == settings.auth_mode
	assert body["has_password"] is True

	if settings.auth_mode == "session":
		sid = login_response.cookies.get("cerberus_sid")
		assert sid is not None
		prefix = settings.redis_key_prefix
		session = await redis_store_session.get_session(redis_conn, prefix, sid)
		assert session is not None  # TTL延長（EXPIRE）後も存在し続けることを確認する


async def test_me_endpoint_unauthenticated_returns_401(client: TestClient) -> None:
	"""結合9: Cookie/Authorizationヘッダが無い場合は401 UNAUTHENTICATEDとなる。"""
	response = client.get("/api/auth/me")

	assert response.status_code == 401
	assert response.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_me_endpoint_inactive_user_returns_403(
	client: TestClient, created_user_ids: list[uuid.UUID], db_session: AsyncSession
) -> None:
	"""結合10: ログイン済み後にis_active=falseへ変わったユーザーは403 USER_INACTIVEとなる。"""
	user = await register_verified_user(client, created_user_ids, db_session)
	login_response = _login(client, user["username"], user["password"])

	await db_session.execute(text("UPDATE users SET is_active = false WHERE id = :id"), {"id": uuid.UUID(user["id"])})
	await db_session.commit()

	response = client.get("/api/auth/me", headers=_auth_headers_for(login_response))

	assert response.status_code == 403
	assert response.json()["error"]["code"] == "USER_INACTIVE"


async def test_me_endpoint_session_expired_returns_session_expired(
	client: TestClient, created_user_ids: list[uuid.UUID], db_session: AsyncSession, redis_conn: Redis
) -> None:
	"""結合（session固有の異常系）: CookieありでRedisのsessionが失効済みだとSESSION_EXPIREDとなる。"""
	settings = get_backend_settings()
	if settings.auth_mode != "session":
		pytest.skip("sessionモード固有の検証(jwtはtoken_expiredで別途検証される設計)")

	user = await register_verified_user(client, created_user_ids, db_session)
	login_response = _login(client, user["username"], user["password"])
	sid = login_response.cookies.get("cerberus_sid")
	assert sid is not None
	prefix = settings.redis_key_prefix
	await redis_store_session.delete_session(redis_conn, prefix, sid, uuid.UUID(user["id"]))

	response = client.get("/api/auth/me")

	assert response.status_code == 401
	assert response.json()["error"]["code"] == "SESSION_EXPIRED"


async def test_me_endpoint_redis_failure_returns_503(
	client: TestClient,
	monkeypatch: pytest.MonkeyPatch,
	created_user_ids: list[uuid.UUID],
	db_session: AsyncSession,
	redis_conn: Redis,
) -> None:
	"""結合（Redis障害）: sessionモードでRedis接続不能時は503 SERVICE_UNAVAILABLEを返す（fail-close）。"""
	settings = get_backend_settings()
	if settings.auth_mode != "session":
		pytest.skip("Redisに依存するのはsessionモードのみ(jwtはRedisアクセスなし)")

	user = await register_verified_user(client, created_user_ids, db_session)
	login_response = _login(client, user["username"], user["password"])

	async def _boom(*_args: Any, **_kwargs: Any) -> Any:
		raise RedisConnectionError("redis down")

	# session_auth.pyが実際に呼び出す`redis_store`モジュール属性を差し替える障害注入。
	# アプリはTestClient専用ポータル内でこれを実行するため、テスト側のイベントループには影響しない。
	monkeypatch.setattr(redis_store, "get_session", _boom)
	response = client.get("/api/auth/me")

	assert response.status_code == 503
	assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"

	monkeypatch.undo()
	sid = login_response.cookies.get("cerberus_sid")
	assert sid is not None
	prefix = settings.redis_key_prefix
	assert (
		await redis_store_session.get_session(redis_conn, prefix, sid) is not None
	)  # 障害時も既存セッションは破棄されない
	await redis_store_session.delete_session(redis_conn, prefix, sid, uuid.UUID(user["id"]))
