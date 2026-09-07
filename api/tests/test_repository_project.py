import uuid
from datetime import datetime, timezone

import pytest
from app.repository import project_repository, user_repository
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession


async def _create_owner(db: AsyncSession, username: str) -> uuid.UUID:
	return await user_repository.create(db, username, f"{username}@example.com", "hash")


async def test_create_project_registers_owner_as_member(db_session: AsyncSession) -> None:
	from app.repository import project_member_repository

	owner_id = await _create_owner(db_session, "alice")

	project_id = await project_repository.create(db_session, owner_id, "Project A", "desc", None, None)

	project = await project_repository.get_by_id(db_session, project_id)
	assert project is not None
	assert project.name == "Project A"
	assert project.owner_id == owner_id
	assert project.is_active is True

	is_member = await project_member_repository.exists(db_session, project_id, owner_id)
	assert is_member is True


async def test_get_by_id_not_found_returns_none(db_session: AsyncSession) -> None:
	project = await project_repository.get_by_id(db_session, uuid.uuid4())
	assert project is None


async def test_create_project_invalid_period_raises_p0009(db_session: AsyncSession) -> None:
	owner_id = await _create_owner(db_session, "bob")
	start = datetime(2026, 2, 1, tzinfo=timezone.utc)
	end = datetime(2026, 1, 1, tzinfo=timezone.utc)

	with pytest.raises(DBAPIError) as exc_info:
		await project_repository.create(db_session, owner_id, "Project B", None, start, end)
	assert getattr(exc_info.value.orig, "sqlstate", None) == "P0009"


async def test_update_project_changes_fields(db_session: AsyncSession) -> None:
	owner_id = await _create_owner(db_session, "carol")
	project_id = await project_repository.create(db_session, owner_id, "Project C", "old", None, None)

	await project_repository.update(db_session, project_id, "Project C2", "new", None, None)

	project = await project_repository.get_by_id(db_session, project_id)
	assert project is not None
	assert project.name == "Project C2"
	assert project.description == "new"


async def test_update_project_invalid_period_raises_p0009(db_session: AsyncSession) -> None:
	owner_id = await _create_owner(db_session, "dave")
	project_id = await project_repository.create(db_session, owner_id, "Project D", None, None, None)
	start = datetime(2026, 2, 1, tzinfo=timezone.utc)
	end = datetime(2026, 1, 1, tzinfo=timezone.utc)

	with pytest.raises(DBAPIError) as exc_info:
		await project_repository.update(db_session, project_id, "Project D", None, start, end)
	assert getattr(exc_info.value.orig, "sqlstate", None) == "P0009"


async def test_set_active_deactivates_and_reactivates_project(db_session: AsyncSession) -> None:
	owner_id = await _create_owner(db_session, "erin")
	project_id = await project_repository.create(db_session, owner_id, "Project E", None, None, None)

	await project_repository.set_active(db_session, project_id, False)
	deactivated = await project_repository.get_by_id(db_session, project_id)
	assert deactivated is not None
	assert deactivated.is_active is False

	await project_repository.set_active(db_session, project_id, True)
	reactivated = await project_repository.get_by_id(db_session, project_id)
	assert reactivated is not None
	assert reactivated.is_active is True


async def test_list_for_user_scoped_to_membership_with_counts(db_session: AsyncSession) -> None:
	from app.repository import task_repository

	owner_id = await _create_owner(db_session, "frank")
	other_id = await _create_owner(db_session, "grace")
	project_id = await project_repository.create(db_session, owner_id, "Project F", None, None, None)
	await project_repository.create(db_session, other_id, "Project G (not mine)", None, None, None)

	await task_repository.create(db_session, project_id, owner_id, None, "task1", None, "todo", None, None)
	await task_repository.create(db_session, project_id, owner_id, None, "task2", None, "in_progress", None, None)

	items = await project_repository.list_for_user(db_session, owner_id, False, 10, 0)

	assert len(items) == 1
	item = items[0]
	assert item.project.id == project_id
	assert item.member_count == 1
	assert item.task_count_todo == 1
	assert item.task_count_in_progress == 1
	assert item.task_count_done == 0
	assert item.total_count == 1


async def test_list_for_user_include_inactive(db_session: AsyncSession) -> None:
	owner_id = await _create_owner(db_session, "heidi")
	project_id = await project_repository.create(db_session, owner_id, "Project H", None, None, None)
	await project_repository.set_active(db_session, project_id, False)

	active_only = await project_repository.list_for_user(db_session, owner_id, False, 10, 0)
	with_inactive = await project_repository.list_for_user(db_session, owner_id, True, 10, 0)

	assert len(active_only) == 0
	assert len(with_inactive) == 1
	assert with_inactive[0].project.is_active is False


async def test_list_for_user_admin_sees_all_projects(db_session: AsyncSession) -> None:
	owner_id = await _create_owner(db_session, "ivan")
	await project_repository.create(db_session, owner_id, "Project I", None, None, None)

	admin_id = await user_repository.create(db_session, "admin-user", "admin-user@example.com", "hash")
	await db_session.execute(text("UPDATE users SET role = 'admin' WHERE id = :id"), {"id": admin_id})

	items = await project_repository.list_for_user(db_session, admin_id, False, 10, 0)

	assert len(items) == 1
