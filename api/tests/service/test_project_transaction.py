from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.core.exceptions import ServiceUnavailableError
from app.repository import project_repository, user_repository
from app.schemas.auth import CurrentUser
from app.schemas.project import ProjectCreateRequest, ProjectUpdateRequest
from app.service import project_service
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession


def _failure() -> OperationalError:
	return OperationalError("project operation", {}, SimpleNamespace(sqlstate="08006"))


async def _user(db: AsyncSession, prefix: str) -> CurrentUser:
	user_id = await user_repository.create(
		db, f"{prefix}-{uuid4().hex[:8]}", f"{prefix}-{uuid4().hex[:8]}@example.com", "hash"
	)
	return CurrentUser(id=user_id, username=prefix, role="member", is_active=True, email_verified_at=None)


async def _project(db: AsyncSession, user: CurrentUser):
	project_id = await project_repository.create(db, user.id, "before", None, None, None)
	project = await project_repository.get_by_id(db, project_id)
	assert project is not None
	return project


@pytest.mark.asyncio
async def test_create_project_rolls_back_real_db_changes_on_db_failure(
	db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
	user = await _user(db_session, "create-failure")
	await db_session.commit()
	original_create = project_repository.create

	async def create_then_fail(*args: object, **kwargs: object):
		await original_create(*args, **kwargs)
		raise _failure()

	monkeypatch.setattr(project_service.project_repository, "create", create_then_fail)
	with pytest.raises(ServiceUnavailableError):
		await project_service.create_project(user, ProjectCreateRequest(name="must rollback"), db_session)
	count = await db_session.scalar(text("SELECT count(*) FROM projects WHERE name = 'must rollback'"))
	assert count == 0


@pytest.mark.asyncio
async def test_update_project_rolls_back_real_db_changes_on_db_failure(
	db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
	user = await _user(db_session, "update-failure")
	project = await _project(db_session, user)
	project_id = project.id
	await db_session.commit()
	original_update = project_repository.update

	async def update_then_fail(*args: object, **kwargs: object):
		await original_update(*args, **kwargs)
		raise _failure()

	monkeypatch.setattr(project_service.project_repository, "update", update_then_fail)
	with pytest.raises(ServiceUnavailableError):
		await project_service.update_project(db_session, project, ProjectUpdateRequest(name="must rollback"), user)
	stored = await project_repository.get_by_id(db_session, project_id)
	assert stored is not None and stored.name == "before"


@pytest.mark.asyncio
async def test_deactivate_project_rolls_back_real_db_changes_on_db_failure(
	db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
	user = await _user(db_session, "delete-failure")
	project = await _project(db_session, user)
	project_id = project.id
	await db_session.commit()
	original_set_active = project_repository.set_active

	async def set_active_then_fail(*args: object, **kwargs: object):
		await original_set_active(*args, **kwargs)
		raise _failure()

	monkeypatch.setattr(project_service.project_repository, "set_active", set_active_then_fail)
	with pytest.raises(ServiceUnavailableError):
		await project_service.deactivate_project(db_session, project)
	stored = await project_repository.get_by_id(db_session, project_id)
	assert stored is not None and stored.is_active is True
