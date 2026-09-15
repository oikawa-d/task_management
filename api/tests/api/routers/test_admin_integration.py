import logging
import secrets
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
from app.repository import login_history_repository, project_repository, redis_store, user_repository
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_ORIGIN = "http://localhost:5173"


@dataclass(frozen=True)
class _TestUser:
	id: UUID
	username: str


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


async def _create_user(db: AsyncSession, role: str = "member") -> _TestUser:
	suffix = secrets.token_hex(8)
	username = f"issue435_{suffix}"
	user_id = await user_repository.create(db, username, f"{username}@example.com", "unused-password-hash")
	await db.execute(
		text("UPDATE users SET role = :role, last_name = 'Issue', first_name = '435' WHERE id = :id"),
		{"role": role, "id": user_id},
	)
	await db.commit()
	return _TestUser(user_id, username)


async def _authenticate(client: httpx.AsyncClient, user_id: UUID) -> dict[str, str]:
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


async def _store_refresh(user_id: UUID) -> str:
	token = secrets.token_urlsafe(32)
	await redis_store.store_refresh_token(token, user_id, str(uuid4()), get_backend_settings().refresh_ttl_seconds)
	return token


def _assert_error(response: httpx.Response, status_code: int, code: str) -> None:
	assert response.status_code == status_code
	assert response.json()["error"]["code"] == code


@pytest.mark.asyncio
async def test_admin_user_role_status_and_redis_revocation_are_integrated(
	db_session: AsyncSession,
	admin_api_client: httpx.AsyncClient,
	caplog: pytest.LogCaptureFixture,
) -> None:
	admin = await _create_user(db_session, "admin")
	target = await _create_user(db_session)
	await _authenticate(admin_api_client, admin.id)
	target_client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")
	try:
		target_auth = await _authenticate(target_client, target.id)
		refresh_token = await _store_refresh(target.id)
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
			"UNAUTHENTICATED" if get_backend_settings().auth_mode == "session" else "USER_INACTIVE",
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
async def test_admin_force_logout_revokes_all_auth_state_but_preserves_user(
	db_session: AsyncSession,
	admin_api_client: httpx.AsyncClient,
	caplog: pytest.LogCaptureFixture,
) -> None:
	admin = await _create_user(db_session, "admin")
	target = await _create_user(db_session)
	await _authenticate(admin_api_client, admin.id)
	target_client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")
	try:
		target_auth = await _authenticate(target_client, target.id)
		other_session, _ = await redis_store.create_session(
			target.id, "127.0.0.2", get_backend_settings().session_ttl_seconds
		)
		refresh_token = await _store_refresh(target.id)
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
			_assert_error(await target_client.get("/api/auth/me"), 401, "UNAUTHENTICATED")
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
) -> None:
	admin = await _create_user(db_session, "admin")
	owner = await _create_user(db_session)
	await _authenticate(admin_api_client, admin.id)
	project_name = f"issue435-project-{secrets.token_hex(6)}"
	project_id = await project_repository.create(db_session, owner.id, project_name, "description", None, None)
	login_identifier = f"issue435-login-{secrets.token_hex(6)}@example.com"
	await login_history_repository.create(
		db_session, owner.id, login_identifier, "jwt", "198.51.100.4", "pytest", True, None
	)
	await db_session.commit()

	projects = await admin_api_client.get("/api/admin/projects", params={"q": project_name})
	assert projects.status_code == 200
	assert projects.json()["items"][0]["owner"]["id"] == str(owner.id)
	history = await admin_api_client.get("/api/admin/login-history", params={"q": login_identifier})
	assert history.status_code == 200
	assert history.json()["items"][0]["user"]["id"] == str(owner.id)
	assert history.json()["items"][0]["login_identifier"] == login_identifier

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


@pytest.mark.asyncio
async def test_admin_guard_and_not_found_responses_hide_admin_targets(
	db_session: AsyncSession,
	admin_api_client: httpx.AsyncClient,
) -> None:
	admin = await _create_user(db_session, "admin")
	member = await _create_user(db_session)
	await _authenticate(admin_api_client, admin.id)
	member_client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")
	try:
		await _authenticate(member_client, member.id)
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
) -> None:
	admin = await _create_user(db_session, "admin")
	target = await _create_user(db_session)
	await _authenticate(admin_api_client, admin.id)

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
