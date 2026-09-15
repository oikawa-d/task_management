from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from app.api.routers import projects_router
from app.auth.factory import get_auth_strategy
from app.auth.jwt_auth import JwtAuthStrategy
from app.core import security
from app.core.config import get_backend_settings
from app.core.exceptions import OwnerCannotBeRemovedError
from app.db import get_db_session
from app.main import app
from app.repository import project_member_repository, project_repository, task_repository, user_repository
from app.service import member_service
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


async def test_project_member_lifecycle_uses_database_contract(db_session: AsyncSession) -> None:
	owner_id = await user_repository.create(db_session, "member-lifecycle-owner", "member-owner@example.com", "hash")
	member_id = await user_repository.create(db_session, "member-lifecycle-user", "member-user@example.com", "hash")
	candidate_id = await user_repository.create(
		db_session, "member-lifecycle-candidate", "member-candidate@example.com", "hash"
	)
	project_id = await project_repository.create(db_session, owner_id, "Member lifecycle", None, None, None)
	project = await project_repository.get_by_id(db_session, project_id)
	assert project is not None

	candidates = await member_service.search_candidates(project, "member-lifecycle-candidate", db_session)
	assert [item.user_id for item in candidates.items] == [candidate_id]

	added = await member_service.add_member(project, member_id, owner_id, db_session)
	assert added.user_id == member_id
	assert added.is_owner is False

	members = await member_service.list_members(project, db_session)
	assert {item.user_id for item in members.items} == {owner_id, member_id}

	await member_service.remove_member(project, member_id, db_session)
	assert await project_member_repository.exists(db_session, project_id, member_id) is False

	with pytest.raises(OwnerCannotBeRemovedError):
		await member_service.remove_member(project, owner_id, db_session)


async def _create_router_user(db: AsyncSession, username: str, role: str = "member") -> UUID:
	user_id = await user_repository.create(db, username, f"{username}@example.com", "hash")
	if role != "member":
		await db.execute(text("UPDATE users SET role = :role WHERE id = :user_id"), {"role": role, "user_id": user_id})
	return user_id


def _access_token(user_id: UUID) -> str:
	settings = get_backend_settings()
	now = datetime.now(UTC)
	return security.encode_jwt(
		{"sub": str(user_id), "iat": now, "exp": int(now.timestamp()) + 900, "jti": str(uuid4()), "typ": "access"},
		settings.jwt_secret_key,
		settings.jwt_algorithm,
	)


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


def _auth(user_id: UUID) -> dict[str, str]:
	return {"Authorization": f"Bearer {_access_token(user_id)}"}


@pytest.mark.asyncio
async def test_project_member_api_enforces_authentication_and_role_boundaries(
	db_session: AsyncSession, api_client: TestClient
) -> None:
	owner_id = await _create_router_user(db_session, "router-member-owner")
	member_id = await _create_router_user(db_session, "router-member-member")
	admin_id = await _create_router_user(db_session, "router-member-admin", "admin")
	outsider_id = await _create_router_user(db_session, "router-member-outsider")
	candidate_id = await _create_router_user(db_session, "router-member-candidate")
	admin_target_id = await _create_router_user(db_session, "router-member-admin-target")
	project_id = await project_repository.create(db_session, owner_id, "Router member project", None, None, None)
	await project_member_repository.create(db_session, project_id, member_id, owner_id)
	await db_session.commit()

	for user_id in (owner_id, member_id, admin_id):
		response = api_client.get(f"/api/projects/{project_id}/members", headers=_auth(user_id))
		assert response.status_code == 200

	assert api_client.get(f"/api/projects/{project_id}/members").json()["error"]["code"] == "UNAUTHENTICATED"
	outsider_response = api_client.get(f"/api/projects/{project_id}/members", headers=_auth(outsider_id))
	assert outsider_response.status_code == 404

	owner_candidates = api_client.get(
		f"/api/projects/{project_id}/member-candidates",
		params={"q": "router-member-candidate"},
		headers=_auth(owner_id),
	)
	assert owner_candidates.status_code == 200
	assert [item["user_id"] for item in owner_candidates.json()["items"]] == [str(candidate_id)]

	admin_candidates = api_client.get(
		f"/api/projects/{project_id}/member-candidates",
		params={"q": "router-member-candidate"},
		headers=_auth(admin_id),
	)
	assert admin_candidates.status_code == 200
	member_candidates = api_client.get(
		f"/api/projects/{project_id}/member-candidates",
		params={"q": "router-member-candidate"},
		headers=_auth(member_id),
	)
	assert member_candidates.status_code == 403
	outsider_candidates = api_client.get(
		f"/api/projects/{project_id}/member-candidates",
		params={"q": "router-member-candidate"},
		headers=_auth(outsider_id),
	)
	assert outsider_candidates.status_code == 404

	added = api_client.post(
		f"/api/projects/{project_id}/members", json={"user_id": str(candidate_id)}, headers=_auth(owner_id)
	)
	assert added.status_code == 201
	duplicate = api_client.post(
		f"/api/projects/{project_id}/members", json={"user_id": str(candidate_id)}, headers=_auth(owner_id)
	)
	assert duplicate.status_code == 409
	assert duplicate.json()["error"]["code"] == "ALREADY_MEMBER"

	member_add = api_client.post(
		f"/api/projects/{project_id}/members", json={"user_id": str(outsider_id)}, headers=_auth(member_id)
	)
	assert member_add.status_code == 403
	admin_add = api_client.post(
		f"/api/projects/{project_id}/members", json={"user_id": str(admin_target_id)}, headers=_auth(admin_id)
	)
	assert admin_add.status_code == 201
	removed = api_client.delete(f"/api/projects/{project_id}/members/{candidate_id}", headers=_auth(owner_id))
	assert removed.status_code == 204
	admin_removed = api_client.delete(f"/api/projects/{project_id}/members/{admin_target_id}", headers=_auth(admin_id))
	assert admin_removed.status_code == 204
	member_remove = api_client.delete(f"/api/projects/{project_id}/members/{member_id}", headers=_auth(member_id))
	assert member_remove.status_code == 403
	owner_remove = api_client.delete(f"/api/projects/{project_id}/members/{owner_id}", headers=_auth(owner_id))
	assert owner_remove.status_code == 409
	assert owner_remove.json()["error"]["code"] == "OWNER_CANNOT_BE_REMOVED"


@pytest.mark.asyncio
async def test_project_member_api_rolls_back_real_insert_on_database_failure(
	db_session: AsyncSession, api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
	owner_id = await _create_router_user(db_session, "router-member-rollback-owner")
	target_id = await _create_router_user(db_session, "router-member-rollback-target")
	project_id = await project_repository.create(db_session, owner_id, "Rollback project", None, None, None)
	await db_session.commit()
	original_create = project_member_repository.create

	async def create_then_fail(*args: object, **kwargs: object) -> None:
		await original_create(*args, **kwargs)  # type: ignore[arg-type]
		raise DBAPIError("forced member failure", {}, RuntimeError("forced"))

	monkeypatch.setattr(projects_router.member_service.project_member_repository, "create", create_then_fail)
	response = api_client.post(
		f"/api/projects/{project_id}/members", json={"user_id": str(target_id)}, headers=_auth(owner_id)
	)

	assert response.status_code == 500, response.text
	await db_session.rollback()
	assert await project_member_repository.exists(db_session, project_id, target_id) is False


@pytest.mark.asyncio
async def test_project_member_api_rolls_back_real_delete_on_database_failure(
	db_session: AsyncSession, api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
	owner_id = await _create_router_user(db_session, "router-member-delete-owner")
	target_id = await _create_router_user(db_session, "router-member-delete-target")
	project_id = await project_repository.create(db_session, owner_id, "Delete rollback project", None, None, None)
	await project_member_repository.create(db_session, project_id, target_id, owner_id)
	task_id = await task_repository.create(
		db_session, project_id, owner_id, target_id, "assigned task", None, "todo", None, None
	)
	await db_session.commit()
	original_delete = project_member_repository.delete

	async def delete_then_fail(*args: object, **kwargs: object) -> None:
		await original_delete(*args, **kwargs)  # type: ignore[arg-type]
		raise DBAPIError("forced member delete failure", {}, RuntimeError("forced"))

	monkeypatch.setattr(projects_router.member_service.project_member_repository, "delete", delete_then_fail)
	response = api_client.delete(f"/api/projects/{project_id}/members/{target_id}", headers=_auth(owner_id))

	assert response.status_code == 500, response.text
	await db_session.rollback()
	assert await project_member_repository.exists(db_session, project_id, target_id) is True
	task = await task_repository.get_by_id(db_session, task_id)
	assert task is not None and task.task.assignee_id == target_id
