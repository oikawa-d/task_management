from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from app.core.config import get_backend_settings
from app.core.security import hash_password
from app.repository import project_member_repository, project_repository, task_repository, user_repository
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

ALLOWED_ORIGIN = "http://localhost:5173"
PASSWORD = "Passw0rd!123"


@dataclass(frozen=True)
class TaskScenario:
	member_id: uuid.UUID
	outsider_id: uuid.UUID
	member_username: str
	outsider_username: str
	member_project_id: uuid.UUID
	shared_project_id: uuid.UUID
	private_project_id: uuid.UUID
	member_project_task_id: uuid.UUID
	shared_project_task_id: uuid.UUID
	own_unassigned_task_id: uuid.UUID
	outsider_unassigned_task_id: uuid.UUID


@pytest.fixture
def client(apply_migrations: None) -> Iterator[TestClient]:
	from app.auth.factory import get_auth_strategy
	from app.db import get_db_engine, get_session_factory
	from app.main import app
	from app.redis_client import get_redis_client

	get_backend_settings.cache_clear()
	get_auth_strategy.cache_clear()
	get_db_engine.cache_clear()
	get_session_factory.cache_clear()
	get_redis_client.cache_clear()
	with TestClient(app) as test_client:
		# PostgreSQLのINET列へ記録できるIPを、TestClientの仮想接続元として使う。
		test_client._transport.client = ("127.0.0.1", 50000)
		test_client.get("/api/health")
		yield test_client
	get_auth_strategy.cache_clear()
	get_db_engine.cache_clear()
	get_session_factory.cache_clear()
	get_redis_client.cache_clear()


@pytest_asyncio.fixture
async def scenario(db_session: AsyncSession) -> Iterator[TaskScenario]:
	suffix = uuid.uuid4().hex[:12]
	member_id = await user_repository.create(
		db_session, f"member_{suffix}", f"member_{suffix}@example.com", hash_password(PASSWORD)
	)
	outsider_id = await user_repository.create(
		db_session, f"outsider_{suffix}", f"outsider_{suffix}@example.com", hash_password(PASSWORD)
	)
	await user_repository.mark_email_verified(db_session, member_id)
	await user_repository.mark_email_verified(db_session, outsider_id)

	member_project_id = await project_repository.create(db_session, member_id, f"member-{suffix}", None, None, None)
	shared_project_id = await project_repository.create(db_session, outsider_id, f"shared-{suffix}", None, None, None)
	private_project_id = await project_repository.create(db_session, outsider_id, f"private-{suffix}", None, None, None)
	await project_member_repository.create(db_session, shared_project_id, member_id, outsider_id)

	member_project_task_id = await task_repository.create(
		db_session, member_project_id, member_id, None, f"member-task-{suffix}", None, "todo", None, None
	)
	shared_project_task_id = await task_repository.create(
		db_session, shared_project_id, outsider_id, None, f"shared-task-{suffix}", None, "in_progress", None, None
	)
	own_unassigned_task_id = await task_repository.create(
		db_session, None, member_id, None, f"own-unassigned-{suffix}", None, "done", None, None
	)
	outsider_unassigned_task_id = await task_repository.create(
		db_session, None, outsider_id, None, f"outsider-unassigned-{suffix}", None, "todo", None, None
	)
	await db_session.commit()

	value = TaskScenario(
		member_id,
		outsider_id,
		f"member_{suffix}",
		f"outsider_{suffix}",
		member_project_id,
		shared_project_id,
		private_project_id,
		member_project_task_id,
		shared_project_task_id,
		own_unassigned_task_id,
		outsider_unassigned_task_id,
	)
	try:
		yield value
	finally:
		await db_session.execute(
			text("DELETE FROM tasks WHERE created_by = ANY(:ids)"), {"ids": [member_id, outsider_id]}
		)
		await db_session.execute(
			text("DELETE FROM projects WHERE id = ANY(:ids)"),
			{"ids": [member_project_id, shared_project_id, private_project_id]},
		)
		await db_session.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": [member_id, outsider_id]})
		await db_session.commit()


@pytest.fixture
def authenticate(client: TestClient, scenario: TaskScenario):
	def _authenticate(user: str = "member") -> dict[str, str]:
		username = scenario.member_username if user == "member" else scenario.outsider_username
		response = client.post(
			"/api/auth/login",
			json={"identifier": username, "password": PASSWORD},
			headers={"Origin": ALLOWED_ORIGIN},
		)
		if get_backend_settings().auth_mode == "session":
			assert response.status_code == 204, response.text
		else:
			assert response.status_code == 200, response.text
		if get_backend_settings().auth_mode == "jwt":
			return {"Authorization": f"Bearer {response.json()['access_token']}"}
		return {}

	return _authenticate


def write_headers(client: TestClient, auth_headers: dict[str, str]) -> dict[str, str]:
	headers = {**auth_headers, "Origin": ALLOWED_ORIGIN}
	if get_backend_settings().auth_mode == "session":
		headers["X-CSRF-Token"] = client.cookies.get(get_backend_settings().cookie_name_csrf) or ""
	return headers
