"""Issue #437: users/me系APIとhealth APIの実DB・実Redis結合テスト。

`client`フィクスチャは同ディレクトリの`tests/integration/conftest.py`（モジュールスコープ、
実app・実DB・実Redisを使う）をそのまま利用する。本ファイルでは`redis_conn`（後始末・検証用の
実Redisクライアント）と`created_user_ids`（作成したusersの後片付け）を独自に用意する。
users/me系はGET/PATCH/PUT/login-historyのいずれもログイン済みCookie/Authorizationヘッダを
前提とし、health系（`GET /api/health`）は認証不要でDB/Redisの疎通状態をそのまま反映する。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from app.core.config import get_backend_settings
from app.core.security import hash_password
from app.db import get_db_engine
from app.main import app
from app.redis_client import get_redis_client
from app.repository import login_history_repository, redis_store_auth, redis_store_session, user_repository
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

ALLOWED_ORIGIN = "http://localhost:5173"
TEST_PASSWORD = "OldPass1!"
NEW_PASSWORD = "NewPass2!"


@pytest_asyncio.fixture
async def redis_conn() -> AsyncIterator[Redis]:
	"""結合テストの検証・後始末専用の実Redisクライアント（アプリ内部のキャッシュ済みクライアントとは別）。"""
	settings = get_backend_settings()
	client = Redis.from_url(settings.redis_url, decode_responses=True)
	try:
		yield client
	finally:
		await client.aclose()


@pytest_asyncio.fixture
async def created_user_ids(db_session: AsyncSession, redis_conn: Redis) -> AsyncIterator[list[uuid.UUID]]:
	"""結合テストで作成したusersを終了後に削除し、対応するRedisの認証状態も削除する。

	テスト側でIDを積み上げて使うリストを返し、後片付けではsession/refresh tokenを実Redisから
	削除したうえでusers行をDELETEする（login_historyはFKで連鎖削除される）。
	"""
	ids: list[uuid.UUID] = []
	yield ids
	if not ids:
		return
	await db_session.rollback()
	settings = get_backend_settings()
	for user_id in ids:
		await redis_store_session.delete_all_sessions(redis_conn, settings.redis_key_prefix, user_id)
		await redis_store_auth.revoke_all_refresh_tokens(redis_conn, settings.redis_key_prefix, user_id)
	await db_session.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": ids})
	await db_session.commit()


async def _create_user(db: AsyncSession, ids: list[uuid.UUID], suffix: str) -> dict[str, Any]:
	"""実DBへメール確認済み・プロフィール入力済みのユーザーを1件作成する。

	Args:
		db: 実DBセッション。
		ids: 作成したuser_idを後片付け用に積み上げるリスト（`created_user_ids`フィクスチャの中身）。
		suffix: username衝突を避けるための識別用サフィックス。

	Returns:
		dict[str, Any]: `id`/`username`/`password`を含む、ログインに使えるユーザー情報。
	"""
	username = f"issue437_{suffix}_{uuid.uuid4().hex[:10]}"
	user_id = await user_repository.create(db, username, f"{username}@example.com", hash_password(TEST_PASSWORD))
	await user_repository.mark_email_verified(db, user_id)
	await user_repository.update_profile(db, user_id, "山田", "太郎", "ヤマダ", "タロウ", date(1995, 4, 1))
	await db.commit()
	ids.append(user_id)
	return {"id": user_id, "username": username, "password": TEST_PASSWORD}


def _login(client: TestClient, user: dict[str, Any]) -> Any:
	"""`POST /api/auth/login`で実際にログインし、AUTH_MODEに応じた成功ステータス（204/200）を確認する。

	Args:
		client: 結合テスト用TestClient。
		user: `_create_user`が返すユーザー情報。

	Returns:
		Any: ログイン成功レスポンス（Cookie/access_tokenの取得に使う）。
	"""
	response = client.post(
		"/api/auth/login",
		json={"identifier": user["username"], "password": user["password"]},
		headers={"Origin": ALLOWED_ORIGIN},
	)
	expected_status = 204 if get_backend_settings().auth_mode == "session" else 200
	assert response.status_code == expected_status, response.text
	return response


def _auth_headers(client: TestClient, login_response: Any, *, csrf: bool = False) -> dict[str, str]:
	"""ログイン後の後続リクエスト用ヘッダを組み立てる。

	Args:
		client: 結合テスト用TestClient（CSRF Cookie参照に使う）。
		login_response: `_login`が返したログイン成功レスポンス。
		csrf: TrueならX-CSRF-Tokenヘッダも付与する（PATCH/PUTなど状態変更系で必要）。

	Returns:
		dict[str, str]: Origin・（jwtモードのみ）Authorization・（csrf指定時のみ）X-CSRF-Tokenを含むヘッダ。
	"""
	headers = {"Origin": ALLOWED_ORIGIN}
	if get_backend_settings().auth_mode == "jwt":
		headers["Authorization"] = f"Bearer {login_response.json()['access_token']}"
	if csrf:
		headers["X-CSRF-Token"] = client.cookies.get(get_backend_settings().cookie_name_csrf) or ""
	return headers


async def test_users_me_endpoint_authenticated_success(
	client, db_session: AsyncSession, created_user_ids: list[uuid.UUID]
) -> None:
	"""実DBにプロフィール入力済みユーザーを作成しログイン後、`GET /api/users/me`が200で
	profile_completed=true・has_password=trueを返し、Cache-Control: no-storeが付与されることを検証する。
	"""
	user = await _create_user(db_session, created_user_ids, "profile")
	login_response = _login(client, user)
	response = client.get("/api/users/me", headers=_auth_headers(client, login_response))

	assert response.status_code == 200, response.text
	body = response.json()
	assert body["id"] == str(user["id"])
	assert body["profile_completed"] is True
	assert body["has_password"] is True
	assert "auth_mode" not in body
	assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize(
	"path,method,payload",
	[
		("/api/users/me", "GET", None),
		("/api/users/me", "PATCH", {"last_name": "鈴木"}),
		(
			"/api/users/me/password",
			"PUT",
			{"current_password": TEST_PASSWORD, "new_password": NEW_PASSWORD, "password_confirm": NEW_PASSWORD},
		),
		("/api/users/me/login-history", "GET", None),
	],
)
def test_users_me_endpoints_unauthenticated(client, path: str, method: str, payload: dict[str, str] | None) -> None:
	"""Cookie/Authorizationヘッダ無しでusers/me系4エンドポイントを呼ぶと、いずれも
	401 UNAUTHENTICATEDを返すことを検証する（ログイン状態を作らないため実DB前提は無い）。
	"""
	response = client.request(method, path, json=payload, headers={"Origin": ALLOWED_ORIGIN})

	assert response.status_code == 401, response.text
	assert response.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_users_me_endpoint_inactive_user_returns_forbidden(
	client, db_session: AsyncSession, created_user_ids: list[uuid.UUID]
) -> None:
	"""ログイン済みユーザーを実DBで`is_active = false`に更新後、`GET /api/users/me`が
	403 USER_INACTIVEを返すことを検証する。
	"""
	user = await _create_user(db_session, created_user_ids, "inactive")
	login_response = _login(client, user)
	await db_session.execute(text("UPDATE users SET is_active = false WHERE id = :user_id"), {"user_id": user["id"]})
	await db_session.commit()

	response = client.get("/api/users/me", headers=_auth_headers(client, login_response))

	assert response.status_code == 403
	assert response.json()["error"]["code"] == "USER_INACTIVE"


async def test_patch_users_me_endpoint_success(
	client, db_session: AsyncSession, created_user_ids: list[uuid.UUID]
) -> None:
	"""ログイン済みユーザーで`PATCH /api/users/me`にlast_name変更を送り、200を返したうえで
	実DBのusers行が更新後の値に書き変わっていることを検証する。
	"""
	user = await _create_user(db_session, created_user_ids, "patch")
	login_response = _login(client, user)
	response = client.patch(
		"/api/users/me", json={"last_name": "鈴木"}, headers=_auth_headers(client, login_response, csrf=True)
	)

	assert response.status_code == 200, response.text
	await db_session.rollback()
	stored = await user_repository.get_by_id(db_session, user["id"])
	assert stored is not None and stored.last_name == "鈴木"


async def test_put_users_me_password_endpoint_success(
	client, db_session: AsyncSession, created_user_ids: list[uuid.UUID]
) -> None:
	"""`PUT /api/users/me/password`で現在パスワードから新パスワードへ変更すると204を返し、
	既存の認証状態（session/refresh token）が失効し、新パスワードで再ログインできることを検証する。
	"""
	user = await _create_user(db_session, created_user_ids, "password")
	login_response = _login(client, user)
	response = client.put(
		"/api/users/me/password",
		json={"current_password": TEST_PASSWORD, "new_password": NEW_PASSWORD, "password_confirm": NEW_PASSWORD},
		headers=_auth_headers(client, login_response, csrf=True),
	)

	assert response.status_code == 204
	if get_backend_settings().auth_mode == "session":
		assert client.get("/api/users/me").status_code == 401
	else:
		refresh = client.post("/api/auth/refresh", headers=_auth_headers(client, login_response, csrf=True))
		assert refresh.status_code == 401
	new_login = client.post(
		"/api/auth/login",
		json={"identifier": user["username"], "password": NEW_PASSWORD},
		headers={"Origin": ALLOWED_ORIGIN},
	)
	expected_status = 204 if get_backend_settings().auth_mode == "session" else 200
	assert new_login.status_code == expected_status


async def test_get_users_me_login_history_endpoint_is_scoped(
	client,
	db_session: AsyncSession,
	created_user_ids: list[uuid.UUID],
) -> None:
	"""`GET /api/users/me/login-history`が、ログイン中ユーザー自身のlogin_history行のみを返し、
	別ユーザー（other）の行を含まないこと（ユーザー単位のスコープ）を実DBの件数と突合して検証する。
	"""
	user = await _create_user(db_session, created_user_ids, "history")
	other = await _create_user(db_session, created_user_ids, "other")
	login_response = _login(client, user)

	response = client.get("/api/users/me/login-history", headers=_auth_headers(client, login_response))
	rows = await login_history_repository.list_by_user_id(db_session, user["id"], limit=50)
	other_rows = await login_history_repository.list_by_user_id(db_session, other["id"], limit=50)

	assert response.status_code == 200, response.text
	assert response.json()["meta"]["count"] >= 1
	assert {item["id"] for item in response.json()["items"]} == {str(row.id) for row in rows}
	assert other_rows == []


async def test_users_me_endpoint_db_failure_returns_service_unavailable(
	client,
	db_session: AsyncSession,
	created_user_ids: list[uuid.UUID],
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""`user_repository.get_by_id`のservice層側呼び出し（2回目）でOperationalErrorを注入し、
	`GET /api/users/me`が503 SERVICE_UNAVAILABLEを返すこと（fail-close）を検証する。
	"""
	user = await _create_user(db_session, created_user_ids, "dbfailure")
	login_response = _login(client, user)

	original_get_by_id = user_repository.get_by_id
	call_count = 0

	async def fail_on_service_get_by_id(*args: Any, **kwargs: Any) -> Any:
		nonlocal call_count
		call_count += 1
		if call_count == 2:
			raise OperationalError("SELECT * FROM fn_get_user", {}, SimpleNamespace(sqlstate="08006"))
		return await original_get_by_id(*args, **kwargs)

	monkeypatch.setattr(user_repository, "get_by_id", fail_on_service_get_by_id)
	response = client.get("/api/users/me", headers=_auth_headers(client, login_response))

	assert response.status_code == 503
	assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
	assert call_count == 2


async def test_users_me_endpoint_session_redis_failure_returns_service_unavailable(
	client,
	db_session: AsyncSession,
	created_user_ids: list[uuid.UUID],
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""AUTH_MODE=session限定で、`redis_store.get_session`にConnectionErrorを注入し、
	`GET /api/users/me`が503 SERVICE_UNAVAILABLEを返すこと（fail-close）を検証する。
	"""
	if get_backend_settings().auth_mode != "session":
		pytest.skip("AUTH_MODE=sessionでのみ検証する")
	user = await _create_user(db_session, created_user_ids, "redisfailure")
	login_response = _login(client, user)

	async def fail_get_session(*_args: Any, **_kwargs: Any) -> Any:
		raise RedisConnectionError("redis down")

	monkeypatch.setattr("app.auth.session_auth.redis_store.get_session", fail_get_session)
	response = client.get("/api/users/me", headers=_auth_headers(client, login_response))

	assert response.status_code == 503
	assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


def test_get_health_endpoint_success(client) -> None:
	"""実DB・実Redisが両方疎通している状態で`GET /api/health`が200・status=ok・
	database/redis双方がstatus=okを返すことを検証する（認証不要）。
	"""
	response = client.get("/api/health")

	assert response.status_code == 200
	body = response.json()
	assert body["status"] == "ok"
	assert body["components"]["database"]["status"] == "ok"
	assert body["components"]["redis"]["status"] == "ok"
	assert "error" not in body


def test_get_health_endpoint_no_auth_required(client) -> None:
	"""`GET /api/health`が認証情報無しで200を返し、レスポンスのauth_modeが実際の
	設定値（session/jwt）と一致することを検証する。
	"""
	response = client.get("/api/health")

	assert response.status_code == 200
	assert response.json()["auth_mode"] == get_backend_settings().auth_mode
	assert "error" not in response.json()


def test_get_health_endpoint_redis_down(client) -> None:
	"""`get_redis_client`の依存性オーバーライドでping失敗を注入し、`GET /api/health`が
	503・status=degraded・redisコンポーネントのみerrorを返すことを検証する。
	"""

	class BrokenRedis:
		async def ping(self) -> bool:
			raise RedisConnectionError("redis down")

	app.dependency_overrides[get_redis_client] = lambda: BrokenRedis()
	try:
		response = client.get("/api/health")
	finally:
		app.dependency_overrides.pop(get_redis_client, None)

	assert response.status_code == 503
	body = response.json()
	assert body["status"] == "degraded"
	assert body["components"]["redis"] == {"status": "error", "latency_ms": None}
	assert "error" not in body


def test_get_health_endpoint_database_down(client) -> None:
	"""`get_db_engine`の依存性オーバーライドでconnect失敗を注入し、`GET /api/health`が
	503・status=degraded・databaseコンポーネントのみerrorを返すことを検証する。
	"""

	class BrokenConnection:
		async def __aenter__(self) -> Any:
			raise OperationalError("SELECT 1", {}, SimpleNamespace(sqlstate="08006"))

		async def __aexit__(self, *_args: Any) -> None:
			return None

	class BrokenEngine:
		def connect(self) -> BrokenConnection:
			return BrokenConnection()

	app.dependency_overrides[get_db_engine] = lambda: BrokenEngine()
	try:
		response = client.get("/api/health")
	finally:
		app.dependency_overrides.pop(get_db_engine, None)

	assert response.status_code == 503
	body = response.json()
	assert body["status"] == "degraded"
	assert body["components"]["database"] == {"status": "error", "latency_ms": None}
	assert "error" not in body
