from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from app.core.config import get_backend_settings
from app.core.security import hash_password
from app.repository import (
	project_member_repository,
	project_repository,
	task_comment_repository,
	task_repository,
	user_repository,
)
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

ALLOWED_ORIGIN = "http://localhost:5173"
PASSWORD = "Passw0rd!123"


@dataclass(frozen=True)
class CommentScenario:
	author_username: str
	peer_username: str
	outsider_username: str
	admin_username: str
	project_id: uuid.UUID
	task_id: uuid.UUID
	inactive_task_id: uuid.UUID
	unassigned_task_id: uuid.UUID
	comment_id: uuid.UUID
	inactive_comment_id: uuid.UUID


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
		test_client._transport.client = ("127.0.0.1", 50000)
		test_client.get("/api/health")
		yield test_client
	get_auth_strategy.cache_clear()
	get_db_engine.cache_clear()
	get_session_factory.cache_clear()
	get_redis_client.cache_clear()


@pytest_asyncio.fixture
async def scenario(db_session: AsyncSession) -> Iterator[CommentScenario]:
	suffix = uuid.uuid4().hex[:12]
	password_hash = hash_password(PASSWORD)
	users = {}
	for role in ("author", "peer", "outsider", "admin"):
		username = f"comment_{role}_{suffix}"
		user_id = await user_repository.create(db_session, username, f"{username}@example.com", password_hash)
		await user_repository.mark_email_verified(db_session, user_id)
		users[role] = (user_id, username)

	await db_session.execute(
		text("UPDATE users SET role = 'admin' WHERE id = :user_id"), {"user_id": users["admin"][0]}
	)
	project_id = await project_repository.create(db_session, users["author"][0], f"comment-{suffix}", None, None, None)
	await project_member_repository.create(db_session, project_id, users["peer"][0], users["author"][0])
	task_id = await task_repository.create(
		db_session, project_id, users["author"][0], None, f"comment-task-{suffix}", None, "todo", None, None
	)
	inactive_task_id = await task_repository.create(
		db_session, project_id, users["author"][0], None, f"inactive-task-{suffix}", None, "todo", None, None
	)
	inactive_comment_id = await task_comment_repository.create(
		db_session, inactive_task_id, users["author"][0], "inactive comment"
	)
	unassigned_task_id = await task_repository.create(
		db_session, None, users["author"][0], None, f"unassigned-task-{suffix}", None, "done", None, None
	)
	comment_id = await task_comment_repository.create(db_session, task_id, users["author"][0], "initial comment")
	await db_session.commit()

	value = CommentScenario(
		users["author"][1],
		users["peer"][1],
		users["outsider"][1],
		users["admin"][1],
		project_id,
		task_id,
		inactive_task_id,
		unassigned_task_id,
		comment_id,
		inactive_comment_id,
	)
	try:
		yield value
	finally:
		await db_session.execute(
			text("DELETE FROM tasks WHERE id = ANY(:ids)"),
			{"ids": [task_id, inactive_task_id, unassigned_task_id]},
		)
		await db_session.execute(text("DELETE FROM projects WHERE id = :project_id"), {"project_id": project_id})
		await db_session.execute(
			text("DELETE FROM users WHERE username LIKE :prefix"), {"prefix": f"comment_%_{suffix}"}
		)
		await db_session.commit()


@pytest.fixture
def authenticate(client: TestClient, scenario: CommentScenario):
	def _authenticate(user: str = "author") -> dict[str, str]:
		username = getattr(scenario, f"{user}_username")
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
