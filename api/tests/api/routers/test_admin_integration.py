import logging
import secrets
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx2 as httpx
import pytest
import pytest_asyncio
from app.core import security
from app.core.config import get_backend_settings
from app.db import get_db_session
from app.main import app
from app.redis_client import get_redis_client
from app.repository import (
	login_history_repository,
	project_repository,
	redis_store,
	task_comment_repository,
	task_repository,
	user_repository,
)
from app.repository.redis_store_common import key, token_hash
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession

_ORIGIN = "http://localhost:5173"


@dataclass(frozen=True)
class _TestUser:
	id: UUID
	username: str


@dataclass
class _CleanupState:
	user_ids: list[UUID]
	project_ids: list[UUID]
	session_ids: list[tuple[UUID, str]]
	refresh_tokens: list[tuple[UUID, str]]


@pytest_asyncio.fixture
async def redis_conn() -> AsyncIterator[Redis]:
	settings = get_backend_settings()
	client = Redis.from_url(settings.redis_url, decode_responses=True)
	try:
		yield client
	finally:
		await client.aclose()


@pytest_asyncio.fixture
async def cleanup_state(db_session: AsyncSession, redis_conn: Redis) -> AsyncIterator[_CleanupState]:
	state = _CleanupState([], [], [], [])
	yield state
	settings = get_backend_settings()
	prefix = settings.redis_key_prefix
	pipe = redis_conn.pipeline(transaction=True)
	for user_id, session_id in state.session_ids:
		pipe.delete(key("session", prefix, session_id), key("csrf", prefix, session_id))
		pipe.srem(key("user_sessions", prefix, user_id), session_id)
	for user_id, refresh_token in state.refresh_tokens:
		hash_value = token_hash(refresh_token)
		pipe.delete(key("refresh", prefix, hash_value), key("refresh_used", prefix, hash_value))
		pipe.srem(key("user_refresh", prefix, user_id), hash_value)
	await pipe.execute()
	if state.user_ids:
		await db_session.execute(
			text(
				"DELETE FROM task_comments WHERE user_id = ANY(:user_ids) "
				"OR task_id IN (SELECT id FROM tasks WHERE created_by = ANY(:user_ids))"
			),
			{"user_ids": state.user_ids},
		)
		await db_session.execute(
			text("DELETE FROM tasks WHERE created_by = ANY(:user_ids) OR project_id = ANY(:project_ids)"),
			{"user_ids": state.user_ids, "project_ids": state.project_ids},
		)
	if state.project_ids:
		await db_session.execute(
			text("DELETE FROM projects WHERE id = ANY(:project_ids)"), {"project_ids": state.project_ids}
		)
	if state.user_ids:
		await db_session.execute(text("DELETE FROM users WHERE id = ANY(:user_ids)"), {"user_ids": state.user_ids})
	await db_session.commit()


@pytest_asyncio.fixture
async def admin_api_client(db_session: AsyncSession, caplog: pytest.LogCaptureFixture):
	audit_logger = logging.getLogger("app.audit")
	audit_logger.disabled = False
	if caplog.handler not in audit_logger.handlers:
		audit_logger.addHandler(caplog.handler)
	audit_logger.info("fixture probe")
	get_redis_client.cache_clear()
	redis_client = get_redis_client()

	async def override_db() -> AsyncSession:
		return db_session

	app.dependency_overrides[get_db_session] = override_db
	transport = httpx.ASGITransport(app=app)
	async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
		try:
			yield client
		finally:
			app.dependency_overrides.pop(get_db_session, None)
			audit_logger.removeHandler(caplog.handler)
			await redis_client.aclose()
			get_redis_client.cache_clear()


async def _create_user(db: AsyncSession, cleanup_state: _CleanupState, role: str = "member") -> _TestUser:
	suffix = secrets.token_hex(8)
	username = f"issue435_{suffix}"
	user_id = await user_repository.create(db, username, f"{username}@example.com", "unused-password-hash")
	await db.execute(
		text("UPDATE users SET role = :role, last_name = 'Issue', first_name = '435' WHERE id = :id"),
		{"role": role, "id": user_id},
	)
	await db.commit()
	cleanup_state.user_ids.append(user_id)
	return _TestUser(user_id, username)


async def _authenticate(client: httpx.AsyncClient, user_id: UUID, cleanup_state: _CleanupState) -> dict[str, str]:
	settings = get_backend_settings()
	csrf_token = secrets.token_urlsafe(24)
	client.headers["Origin"] = _ORIGIN
	client.headers["X-CSRF-Token"] = csrf_token
	client.cookies.set(settings.cookie_name_csrf, csrf_token)
	if settings.auth_mode == "session":
		session_id, csrf_token = await redis_store.create_session(user_id, "127.0.0.1", settings.session_ttl_seconds)
		client.cookies.set(settings.cookie_name_session, session_id)
		client.headers["X-CSRF-Token"] = csrf_token
		client.cookies.set(settings.cookie_name_csrf, csrf_token)
		cleanup_state.session_ids.append((user_id, session_id))
		return {"session_id": session_id, "csrf_token": csrf_token}

	now = int(datetime.now(UTC).timestamp())
	access_token = security.encode_jwt(
		{
			"sub": str(user_id),
			"iat": now,
			"exp": now + settings.access_token_ttl_seconds,
			"jti": str(uuid4()),
			"typ": "access",
		},
		settings.jwt_secret_key,
		settings.jwt_algorithm,
	)
	client.headers["Authorization"] = f"Bearer {access_token}"
	return {"access_token": access_token, "csrf_token": csrf_token}


async def _store_refresh(user_id: UUID, cleanup_state: _CleanupState) -> str:
	token = secrets.token_urlsafe(32)
	await redis_store.store_refresh_token(token, user_id, str(uuid4()), get_backend_settings().refresh_ttl_seconds)
	cleanup_state.refresh_tokens.append((user_id, token))
	return token


def _assert_error(response: httpx.Response, status_code: int, code: str | tuple[str, ...]) -> None:
	assert response.status_code == status_code
	actual_code = response.json()["error"]["code"]
	expected_codes = (code,) if isinstance(code, str) else code
	assert actual_code in expected_codes


@pytest.mark.asyncio
async def test_admin_user_role_status_and_redis_revocation_are_integrated(
	db_session: AsyncSession,
	admin_api_client: httpx.AsyncClient,
	caplog: pytest.LogCaptureFixture,
	cleanup_state: _CleanupState,
) -> None:
	admin = await _create_user(db_session, cleanup_state, "admin")
	target = await _create_user(db_session, cleanup_state)
	await _authenticate(admin_api_client, admin.id, cleanup_state)
	target_client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")
	try:
		target_auth = await _authenticate(target_client, target.id, cleanup_state)
		refresh_token = await _store_refresh(target.id, cleanup_state)
		with caplog.at_level(logging.INFO, logger="app.audit"):
			listed = await admin_api_client.get("/api/admin/users", params={"q": target.username})
			assert listed.status_code == 200
			assert [item["username"] for item in listed.json()["items"]] == [target.username]

			role_response = await admin_api_client.patch(f"/api/admin/users/{target.id}/role", json={"role": "admin"})
			assert role_response.status_code == 200
			status_response = await admin_api_client.patch(
				f"/api/admin/users/{target.id}/status", json={"is_active": False}
			)
		assert status_response.status_code == 200

		assert (
			await db_session.execute(text("SELECT role, is_active FROM users WHERE id = :id"), {"id": target.id})
		).one() == (
			"admin",
			False,
		)
		assert await redis_store.get_refresh_token(refresh_token) is None
		assert (
			await redis_store.get_csrf_token(target_auth["session_id"]) is None if "session_id" in target_auth else True
		)
		inactive_response = await target_client.get("/api/auth/me")
		_assert_error(
			inactive_response,
			401 if get_backend_settings().auth_mode == "session" else 403,
			("UNAUTHENTICATED", "SESSION_EXPIRED")
			if get_backend_settings().auth_mode == "session"
			else "USER_INACTIVE",
		)

		assert any(
			record.getMessage() == "admin changed user role"
			and record.actor_user_id == str(admin.id)
			and record.target_user_id == str(target.id)
			and record.new_role == "admin"
			for record in caplog.records
		)
		assert any(
			record.getMessage() == "admin changed user status"
			and record.actor_user_id == str(admin.id)
			and record.target_user_id == str(target.id)
			and record.new_is_active is False
			and record.session_revoked_count == (1 if get_backend_settings().auth_mode == "session" else 0)
			and record.refresh_revoked_count >= 1
			for record in caplog.records
		)
	finally:
		await target_client.aclose()


@pytest.mark.asyncio
async def test_jwt_refresh_rejects_replayed_old_token(
	db_session: AsyncSession,
	cleanup_state: _CleanupState,
) -> None:
	if get_backend_settings().auth_mode != "jwt":
		pytest.skip("refresh token rotationはJWT方式のみで検証する")
	user = await _create_user(db_session, cleanup_state)
	client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")
	try:
		refresh_auth = await _authenticate(client, user.id, cleanup_state)
		old_token = await _store_refresh(user.id, cleanup_state)
		settings = get_backend_settings()
		client.cookies.clear()
		client.cookies.set(settings.cookie_name_refresh, old_token)
		client.cookies.set(settings.cookie_name_csrf, refresh_auth["csrf_token"])
		first = await client.post("/api/auth/refresh")
		assert first.status_code == 200, first.text
		new_token = first.cookies.get(settings.cookie_name_refresh)
		assert new_token
		cleanup_state.refresh_tokens.append((user.id, new_token))

		client.cookies.clear()
		client.cookies.set(settings.cookie_name_refresh, old_token)
		client.cookies.set(settings.cookie_name_csrf, refresh_auth["csrf_token"])
		replayed = await client.post("/api/auth/refresh")
		_assert_error(replayed, 401, "TOKEN_REVOKED")
	finally:
		await client.aclose()


@pytest.mark.asyncio
async def test_admin_force_logout_revokes_all_auth_state_but_preserves_user(
	db_session: AsyncSession,
	admin_api_client: httpx.AsyncClient,
	caplog: pytest.LogCaptureFixture,
	cleanup_state: _CleanupState,
) -> None:
	admin = await _create_user(db_session, cleanup_state, "admin")
	target = await _create_user(db_session, cleanup_state)
	await _authenticate(admin_api_client, admin.id, cleanup_state)
	target_client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")
	try:
		target_auth = await _authenticate(target_client, target.id, cleanup_state)
		other_session, _ = await redis_store.create_session(
			target.id, "127.0.0.2", get_backend_settings().session_ttl_seconds
		)
		cleanup_state.session_ids.append((target.id, other_session))
		refresh_token = await _store_refresh(target.id, cleanup_state)
		with caplog.at_level(logging.INFO, logger="app.audit"):
			logging.getLogger("app.audit").info("request probe")
			response = await admin_api_client.post(f"/api/admin/users/{target.id}/force-logout")
		assert response.status_code == 204
		assert (
			await db_session.execute(text("SELECT is_active FROM users WHERE id = :id"), {"id": target.id})
		).scalar_one()
		assert await redis_store.get_session(other_session) is None
		assert await redis_store.get_refresh_token(refresh_token) is None
		if "session_id" in target_auth:
			_assert_error(await target_client.get("/api/auth/me"), 401, ("UNAUTHENTICATED", "SESSION_EXPIRED"))
		else:
			assert (await target_client.get("/api/auth/me")).status_code == 200
		assert any(
			record.getMessage() == "admin forced logout"
			and record.actor_user_id == str(admin.id)
			and record.target_user_id == str(target.id)
			and record.session_revoked_count == (2 if get_backend_settings().auth_mode == "session" else 1)
			and record.refresh_revoked_count >= 1
			for record in caplog.records
		), [(record.name, record.getMessage(), vars(record)) for record in caplog.records]
	finally:
		await target_client.aclose()


@pytest.mark.asyncio
async def test_admin_project_and_login_history_endpoints_use_real_db_contracts(
	db_session: AsyncSession,
	admin_api_client: httpx.AsyncClient,
	cleanup_state: _CleanupState,
) -> None:
	admin = await _create_user(db_session, cleanup_state, "admin")
	owner = await _create_user(db_session, cleanup_state)
	await _authenticate(admin_api_client, admin.id, cleanup_state)
	project_name = f"issue435-project-{secrets.token_hex(6)}"
	project_id = await project_repository.create(db_session, owner.id, project_name, "description", None, None)
	cleanup_state.project_ids.append(project_id)
	task_id = await task_repository.create(
		db_session, project_id, owner.id, None, "admin-invariant-task", "original body", "todo", None, None
	)
	comment_id = await task_comment_repository.create(db_session, task_id, owner.id, "original comment")
	login_prefix = f"issue435-login-{secrets.token_hex(6)}"
	for index, ip_address in enumerate(("198.51.100.4", "198.51.100.5")):
		await login_history_repository.create(
			db_session,
			owner.id,
			f"{login_prefix}-{index}@example.com",
			"jwt",
			ip_address,
			"pytest",
			True,
			None,
		)
	await db_session.commit()

	projects = await admin_api_client.get("/api/admin/projects", params={"q": project_name})
	assert projects.status_code == 200
	assert projects.json()["items"][0]["owner"]["id"] == str(owner.id)
	statements: list[str] = []

	def count_query(*_args: object, **_kwargs: object) -> None:
		statements.append(str(_args[2]))

	engine = db_session.sync_session.bind
	assert engine is not None
	event.listen(engine, "before_cursor_execute", count_query)
	try:
		history = await admin_api_client.get("/api/admin/login-history", params={"q": login_prefix})
	finally:
		event.remove(engine, "before_cursor_execute", count_query)
	assert history.status_code == 200
	assert sum("fn_admin_list_login_history" in statement for statement in statements) == 1
	assert not any("FROM login_history" in statement or "FROM users" in statement for statement in statements)
	assert len(history.json()["items"]) == 2
	assert {item["user"]["id"] for item in history.json()["items"]} == {str(owner.id)}
	assert {item["ip_address"] for item in history.json()["items"]} == {"198.51.100.4", "198.51.100.5"}

	deleted = await admin_api_client.delete(f"/api/admin/projects/{project_id}")
	assert deleted.status_code == 204
	assert not (
		await db_session.execute(text("SELECT is_active FROM projects WHERE id = :id"), {"id": project_id})
	).scalar_one()
	assert (
		await db_session.execute(
			text("SELECT count(*) FROM project_members WHERE project_id = :id"), {"id": project_id}
		)
	).scalar_one() == 1
	assert (
		await db_session.execute(
			text("SELECT title, description, status, created_by FROM tasks WHERE id = :id"), {"id": task_id}
		)
	).one() == ("admin-invariant-task", "original body", "todo", owner.id)
	assert (
		await db_session.execute(text("SELECT body, user_id FROM task_comments WHERE id = :id"), {"id": comment_id})
	).one() == ("original comment", owner.id)


@pytest.mark.asyncio
async def test_admin_guard_and_not_found_responses_hide_admin_targets(
	db_session: AsyncSession,
	admin_api_client: httpx.AsyncClient,
	cleanup_state: _CleanupState,
) -> None:
	admin = await _create_user(db_session, cleanup_state, "admin")
	member = await _create_user(db_session, cleanup_state)
	await _authenticate(admin_api_client, admin.id, cleanup_state)
	member_client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")
	try:
		await _authenticate(member_client, member.id, cleanup_state)
		member_responses = [
			await member_client.get("/api/admin/users"),
			await member_client.patch(f"/api/admin/users/{uuid4()}/role", json={"role": "admin"}),
			await member_client.patch(f"/api/admin/users/{uuid4()}/status", json={"is_active": False}),
			await member_client.post(f"/api/admin/users/{uuid4()}/force-logout"),
			await member_client.get("/api/admin/projects"),
			await member_client.delete(f"/api/admin/projects/{uuid4()}"),
			await member_client.get("/api/admin/login-history"),
		]
		for response in member_responses:
			_assert_error(response, 403, "FORBIDDEN")

		missing = uuid4()
		for response in (
			await admin_api_client.patch(f"/api/admin/users/{missing}/role", json={"role": "admin"}),
			await admin_api_client.patch(f"/api/admin/users/{missing}/status", json={"is_active": False}),
			await admin_api_client.post(f"/api/admin/users/{missing}/force-logout"),
			await admin_api_client.delete(f"/api/admin/projects/{missing}"),
		):
			_assert_error(response, 404, "NOT_FOUND")
			assert str(missing) not in response.text
	finally:
		await member_client.aclose()


@pytest.mark.asyncio
async def test_admin_status_redis_failure_returns_503_and_keeps_database_inactive(
	db_session: AsyncSession,
	admin_api_client: httpx.AsyncClient,
	monkeypatch: pytest.MonkeyPatch,
	caplog: pytest.LogCaptureFixture,
	cleanup_state: _CleanupState,
) -> None:
	admin = await _create_user(db_session, cleanup_state, "admin")
	target = await _create_user(db_session, cleanup_state)
	await _authenticate(admin_api_client, admin.id, cleanup_state)

	async def fail_revoke(_user_id: UUID) -> int:
		raise RedisError("redis unavailable")

	monkeypatch.setattr(redis_store, "delete_all_sessions", fail_revoke)
	with caplog.at_level(logging.ERROR, logger="app.audit"):
		response = await admin_api_client.patch(f"/api/admin/users/{target.id}/status", json={"is_active": False})
	_assert_error(response, 503, "SERVICE_UNAVAILABLE")
	assert not (
		await db_session.execute(text("SELECT is_active FROM users WHERE id = :id"), {"id": target.id})
	).scalar_one()
	assert any(
		record.getMessage() == "admin status change: failed to revoke sessions"
		and record.actor_user_id == str(admin.id)
		and record.target_user_id == str(target.id)
		and record.operation == "delete_all_sessions"
		for record in caplog.records
	)
