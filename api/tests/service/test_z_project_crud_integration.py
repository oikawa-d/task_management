from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.api.routers.projects_router import router
from app.auth.factory import get_auth_strategy
from app.auth.jwt_auth import JwtAuthStrategy
from app.core.config import get_backend_settings
from app.core.exceptions import register_error_handling
from app.core.security import encode_jwt
from app.db import get_db_session
from app.repository import project_member_repository, user_repository
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _build_app() -> FastAPI:
	app = FastAPI()
	register_error_handling(app)
	app.include_router(router)
	app.dependency_overrides[get_auth_strategy] = lambda: JwtAuthStrategy(get_backend_settings())
	return app


def _token(user_id: UUID) -> str:
	now = datetime.now(UTC)
	settings = get_backend_settings()
	return encode_jwt(
		{
			"sub": str(user_id),
			"iat": now,
			"exp": int(now.timestamp()) + 900,
			"jti": str(uuid4()),
			"typ": "access",
		},
		settings.jwt_secret_key,
		settings.jwt_algorithm,
	)


def _authorization(user_id: UUID) -> dict[str, str]:
	return {"Authorization": f"Bearer {_token(user_id)}"}


def _error_code(response: Any) -> str:
	return response.json()["error"]["code"]


async def _create_user(db: AsyncSession, username: str) -> UUID:
	return await user_repository.create(db, username, f"{username}@example.com", "hash")


@pytest.mark.asyncio
async def test_project_crud_router_enforces_authz_and_hides_non_member(db_session: AsyncSession) -> None:
	suffix = uuid4().hex[:8]
	owner_id = await _create_user(db_session, f"crud-owner-{suffix}")
	member_id = await _create_user(db_session, f"crud-member-{suffix}")
	admin_id = await _create_user(db_session, f"crud-admin-{suffix}")
	outsider_id = await _create_user(db_session, f"crud-outsider-{suffix}")
	await db_session.execute(text("UPDATE users SET role = 'admin' WHERE id = :id"), {"id": admin_id})
	await db_session.commit()

	app = _build_app()
	app.dependency_overrides[get_db_session] = _db_session_for_request
	try:
		with TestClient(app) as client:
			created = client.post(
				"/api/projects",
				json={"name": "router integration project"},
				headers=_authorization(owner_id),
			)
			assert created.status_code == 201, created.text
			project_id = UUID(created.json()["id"])
			owner_detail = client.get(f"/api/projects/{project_id}", headers=_authorization(owner_id))
			assert owner_detail.status_code == 200
			owner_delete = client.post(
				"/api/projects",
				json={"name": "owner delete project"},
				headers=_authorization(owner_id),
			)
			assert owner_delete.status_code == 201
			owner_delete_id = UUID(owner_delete.json()["id"])

		await project_member_repository.create(db_session, project_id, member_id, owner_id)
		await db_session.commit()

		with TestClient(app) as client:
			owner_list = client.get("/api/projects", headers=_authorization(owner_id))
			assert owner_list.status_code == 200, owner_list.text
			member_list = client.get("/api/projects", headers=_authorization(member_id))
			assert member_list.status_code == 200
			assert [item["id"] for item in member_list.json()["items"]] == [str(project_id)]
			admin_list = client.get("/api/projects", headers=_authorization(admin_id))
			assert admin_list.status_code == 200
			assert str(project_id) in [item["id"] for item in admin_list.json()["items"]]
			member_detail = client.get(f"/api/projects/{project_id}", headers=_authorization(member_id))
			assert member_detail.status_code == 200
			admin_detail = client.get(f"/api/projects/{project_id}", headers=_authorization(admin_id))
			assert admin_detail.status_code == 200
			outsider_list = client.get("/api/projects", headers=_authorization(outsider_id))
			outsider_detail = client.get(f"/api/projects/{project_id}", headers=_authorization(outsider_id))
			assert outsider_list.json()["items"] == []
			assert outsider_detail.status_code == 404 and _error_code(outsider_detail) == "NOT_FOUND"
			owner_update = client.patch(
				f"/api/projects/{project_id}",
				json={"name": "owner updated"},
				headers=_authorization(owner_id),
			)
			assert owner_update.status_code == 200

			member_update = client.patch(
				f"/api/projects/{project_id}",
				json={"name": "member must not update"},
				headers=_authorization(member_id),
			)
			assert member_update.status_code == 403 and _error_code(member_update) == "FORBIDDEN"
			outsider_update = client.patch(
				f"/api/projects/{project_id}",
				json={"name": "outsider must not update"},
				headers=_authorization(outsider_id),
			)
			assert outsider_update.status_code == 404 and _error_code(outsider_update) == "NOT_FOUND"
			admin_update = client.patch(
				f"/api/projects/{project_id}",
				json={"name": "admin updated"},
				headers=_authorization(admin_id),
			)
			assert admin_update.status_code == 200
			member_delete = client.delete(f"/api/projects/{project_id}", headers=_authorization(member_id))
			assert member_delete.status_code == 403 and _error_code(member_delete) == "FORBIDDEN"
			outsider_delete = client.delete(f"/api/projects/{project_id}", headers=_authorization(outsider_id))
			assert outsider_delete.status_code == 404 and _error_code(outsider_delete) == "NOT_FOUND"
			owner_delete_response = client.delete(f"/api/projects/{owner_delete_id}", headers=_authorization(owner_id))
			assert owner_delete_response.status_code == 204, owner_delete_response.text
			assert client.delete(f"/api/projects/{project_id}", headers=_authorization(admin_id)).status_code == 204

			unauthenticated = client.get("/api/projects")
			assert unauthenticated.status_code == 401 and _error_code(unauthenticated) == "UNAUTHENTICATED"
			invalid_token = client.get("/api/projects", headers={"Authorization": "Bearer invalid"})
			assert invalid_token.status_code == 401 and _error_code(invalid_token) == "UNAUTHENTICATED"
			unauthenticated_create = client.post("/api/projects", json={"name": "unauthenticated"})
			assert unauthenticated_create.status_code == 401
			assert _error_code(unauthenticated_create) == "UNAUTHENTICATED"
	finally:
		app.dependency_overrides.clear()

	state = await db_session.execute(
		text("SELECT name, is_active FROM projects WHERE id IN (:project_id, :owner_delete_id) ORDER BY name"),
		{"project_id": project_id, "owner_delete_id": owner_delete_id},
	)
	assert state.all() == [("admin updated", False), ("owner delete project", False)]


async def _db_session_for_request():
	from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

	engine = create_async_engine(get_backend_settings().database_url)
	try:
		async with async_sessionmaker(bind=engine, expire_on_commit=False)() as session:
			yield session
	finally:
		await engine.dispose()
