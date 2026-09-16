"""タスクAPIの書き込み経路がcommit/rollbackを正しく行うことを実DBで検証する。

`db_session` フィクスチャとは別のengine/コネクションで `api_client` がリクエストを
処理するため、同一セッションの読み戻しでは検出できないcommit漏れ・
「検証取得が失敗しても既に書き込みがcommit済み」という順序バグを検出できる。
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from app.auth.factory import get_auth_strategy
from app.auth.jwt_auth import JwtAuthStrategy
from app.core import security
from app.core.config import get_backend_settings
from app.db import get_db_session
from app.main import app
from app.repository import project_repository, task_repository, user_repository
from app.service import task_service
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


async def _create_user(db: AsyncSession, username: str) -> UUID:
	return await user_repository.create(db, username, f"{username}@example.com", "hash")


def _access_token(user_id: UUID) -> str:
	settings = get_backend_settings()
	now = datetime.now(UTC)
	return security.encode_jwt(
		{"sub": str(user_id), "iat": now, "exp": int(now.timestamp()) + 900, "jti": str(uuid4()), "typ": "access"},
		settings.jwt_secret_key,
		settings.jwt_algorithm,
	)


def _auth(user_id: UUID) -> dict[str, str]:
	return {"Authorization": f"Bearer {_access_token(user_id)}"}


@pytest.fixture
def api_client():
	async def override_db_session():
		engine = create_async_engine(get_backend_settings().database_url)
		factory = async_sessionmaker(bind=engine, expire_on_commit=False)
		try:
			async with factory() as session:
				yield session
		finally:
			await engine.dispose()

	app.dependency_overrides[get_db_session] = override_db_session
	app.dependency_overrides[get_auth_strategy] = lambda: JwtAuthStrategy(get_backend_settings())
	with TestClient(app, raise_server_exceptions=False) as client:
		yield client
	app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_task_api_persists_writes_after_http_response(db_session: AsyncSession, api_client: TestClient) -> None:
	owner_id = await _create_user(db_session, f"task-http-owner-{uuid4().hex[:8]}")
	project_id = await project_repository.create(db_session, owner_id, "Task HTTP persistence", None, None, None)
	await db_session.commit()

	created = api_client.post(
		f"/api/projects/{project_id}/tasks", json={"title": "HTTP persisted task"}, headers=_auth(owner_id)
	)
	assert created.status_code == 201, created.text
	task_id = created.json()["id"]

	await db_session.rollback()
	created_row = await task_repository.get_by_id(db_session, task_id)
	assert created_row is not None
	assert created_row.task.title == "HTTP persisted task"

	updated = api_client.patch(
		f"/api/tasks/{task_id}",
		json={"version": created_row.task.version, "title": "HTTP updated task"},
		headers=_auth(owner_id),
	)
	assert updated.status_code == 200, updated.text

	await db_session.rollback()
	updated_row = await task_repository.get_by_id(db_session, task_id)
	assert updated_row is not None
	assert updated_row.task.title == "HTTP updated task"
	assert updated_row.task.version == created_row.task.version + 1

	deleted = api_client.delete(f"/api/tasks/{task_id}", headers=_auth(owner_id))
	assert deleted.status_code == 204, deleted.text

	await db_session.rollback()
	deleted_row = await task_repository.get_by_id(db_session, task_id)
	assert deleted_row is not None
	assert deleted_row.task.is_active is False


@pytest.mark.asyncio
async def test_task_creation_rolls_back_when_post_write_verification_fails(
	db_session: AsyncSession, api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
	owner_id = await _create_user(db_session, f"task-create-rollback-{uuid4().hex[:8]}")
	project_id = await project_repository.create(db_session, owner_id, "Task create rollback", None, None, None)
	await db_session.commit()

	async def failing_get_by_id(*_args: object, **_kwargs: object) -> None:
		raise DBAPIError("forced task create verification failure", {}, RuntimeError("forced"))

	monkeypatch.setattr(task_service.task_repository, "get_by_id", failing_get_by_id)

	response = api_client.post(
		f"/api/projects/{project_id}/tasks", json={"title": "Should not persist"}, headers=_auth(owner_id)
	)
	assert response.status_code == 500, response.text

	await db_session.rollback()
	count = await db_session.scalar(
		text("SELECT COUNT(*) FROM tasks WHERE project_id = :project_id"), {"project_id": project_id}
	)
	assert count == 0


@pytest.mark.asyncio
async def test_task_update_rolls_back_when_post_write_verification_fails(
	db_session: AsyncSession, api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
	owner_id = await _create_user(db_session, f"task-update-rollback-{uuid4().hex[:8]}")
	project_id = await project_repository.create(db_session, owner_id, "Task update rollback", None, None, None)
	task_id = await task_repository.create(
		db_session, project_id, owner_id, None, "Original title", None, "todo", None, None
	)
	await db_session.commit()

	original_get_by_id = task_repository.get_by_id
	calls = {"count": 0}

	async def flaky_get_by_id(db_: AsyncSession, task_id_: UUID) -> object:
		calls["count"] += 1
		if calls["count"] == 1:
			return await original_get_by_id(db_, task_id_)
		raise DBAPIError("forced task update verification failure", {}, RuntimeError("forced"))

	monkeypatch.setattr(task_service.task_repository, "get_by_id", flaky_get_by_id)

	response = api_client.patch(
		f"/api/tasks/{task_id}",
		json={"version": 1, "title": "Should not persist"},
		headers=_auth(owner_id),
	)
	assert response.status_code == 500, response.text

	await db_session.rollback()
	row = (
		await db_session.execute(text("SELECT title, version FROM tasks WHERE id = :task_id"), {"task_id": task_id})
	).one()
	assert row.title == "Original title"
	assert row.version == 1
