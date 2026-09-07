import asyncio
import uuid

import pytest
from app.core.config import get_backend_settings
from app.repository import project_repository, task_repository, user_repository
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


async def _setup_project(db: AsyncSession, username: str) -> tuple[uuid.UUID, uuid.UUID]:
	owner_id = await user_repository.create(db, username, f"{username}@example.com", "hash")
	project_id = await project_repository.create(db, owner_id, "P", None, None, None)
	return owner_id, project_id


async def test_create_task_defaults_applied(db_session: AsyncSession) -> None:
	owner_id, project_id = await _setup_project(db_session, "alice")

	task_id = await task_repository.create(db_session, project_id, owner_id, None, "task1", None, "todo", None, None)

	result = await task_repository.get_by_id(db_session, task_id)
	assert result is not None
	assert result.task.status == "todo"
	assert result.task.position == 0
	assert result.task.version == 1
	assert result.task.is_active is True


async def test_create_task_without_project_succeeds(db_session: AsyncSession) -> None:
	owner_id = await user_repository.create(db_session, "bob", "bob@example.com", "hash")

	task_id = await task_repository.create(db_session, None, owner_id, None, "task1", None, "todo", None, None)

	result = await task_repository.get_by_id(db_session, task_id)
	assert result is not None
	assert result.task.project_id is None


async def test_create_task_position_increments_within_status(db_session: AsyncSession) -> None:
	owner_id, project_id = await _setup_project(db_session, "carol")

	id1 = await task_repository.create(db_session, project_id, owner_id, None, "t1", None, "todo", None, None)
	id2 = await task_repository.create(db_session, project_id, owner_id, None, "t2", None, "todo", None, None)

	result1 = await task_repository.get_by_id(db_session, id1)
	result2 = await task_repository.get_by_id(db_session, id2)
	assert result1 is not None and result1.task.position == 0
	assert result2 is not None and result2.task.position == 1


async def test_create_task_with_explicit_position_shifts_existing_tasks(db_session: AsyncSession) -> None:
	owner_id, project_id = await _setup_project(db_session, "carol2")
	id0 = await task_repository.create(db_session, project_id, owner_id, None, "t0", None, "todo", None, None)
	id1 = await task_repository.create(db_session, project_id, owner_id, None, "t1", None, "todo", None, None)

	# 先頭(position=0)を明示指定して作成し、既存タスクが後方へずれることを確認する
	new_id = await task_repository.create(db_session, project_id, owner_id, None, "new", None, "todo", None, 0)

	new_result = await task_repository.get_by_id(db_session, new_id)
	result0 = await task_repository.get_by_id(db_session, id0)
	result1 = await task_repository.get_by_id(db_session, id1)
	assert new_result is not None and new_result.task.position == 0
	assert result0 is not None and result0.task.position == 1
	assert result1 is not None and result1.task.position == 2


async def test_create_task_with_inactive_assignee_raises_p0006(db_session: AsyncSession) -> None:
	owner_id, project_id = await _setup_project(db_session, "dave2")
	assignee_id = await user_repository.create(db_session, "inactive-assignee1", "ia1@example.com", "hash")

	await db_session.execute(text("UPDATE users SET is_active = false WHERE id = :id"), {"id": assignee_id})

	with pytest.raises(DBAPIError) as exc_info:
		await task_repository.create(db_session, project_id, owner_id, assignee_id, "t1", None, "todo", None, None)
	assert getattr(exc_info.value.orig, "sqlstate", None) == "P0006"


async def test_update_task_with_inactive_assignee_raises_p0006(db_session: AsyncSession) -> None:
	owner_id, project_id = await _setup_project(db_session, "dave3")
	assignee_id = await user_repository.create(db_session, "inactive-assignee2", "ia2@example.com", "hash")
	task_id = await task_repository.create(db_session, project_id, owner_id, None, "t1", None, "todo", None, None)

	await db_session.execute(text("UPDATE users SET is_active = false WHERE id = :id"), {"id": assignee_id})

	with pytest.raises(DBAPIError) as exc_info:
		await task_repository.update(db_session, task_id, owner_id, 1, "t1", None, "todo", assignee_id, None, None)
	assert getattr(exc_info.value.orig, "sqlstate", None) == "P0006"


async def test_update_task_version_conflict_raises_p0005(db_session: AsyncSession) -> None:
	owner_id, project_id = await _setup_project(db_session, "dave")
	task_id = await task_repository.create(db_session, project_id, owner_id, None, "t1", None, "todo", None, None)

	with pytest.raises(DBAPIError) as exc_info:
		await task_repository.update(db_session, task_id, owner_id, 999, "renamed", None, "todo", None, None, None)
	assert getattr(exc_info.value.orig, "sqlstate", None) == "P0005"


async def test_update_task_success_increments_version(db_session: AsyncSession) -> None:
	owner_id, project_id = await _setup_project(db_session, "erin")
	task_id = await task_repository.create(db_session, project_id, owner_id, None, "t1", None, "todo", None, None)

	await task_repository.update(db_session, task_id, owner_id, 1, "renamed", "body", "todo", None, None, None)

	result = await task_repository.get_by_id(db_session, task_id)
	assert result is not None
	assert result.task.title == "renamed"
	assert result.task.version == 2


async def test_reorder_within_status_keeps_positions_contiguous(db_session: AsyncSession) -> None:
	owner_id, project_id = await _setup_project(db_session, "frank")
	id0 = await task_repository.create(db_session, project_id, owner_id, None, "t0", None, "todo", None, None)
	id1 = await task_repository.create(db_session, project_id, owner_id, None, "t1", None, "todo", None, None)
	id2 = await task_repository.create(db_session, project_id, owner_id, None, "t2", None, "todo", None, None)

	# t0(0) を末尾(position=2)へ移動
	await task_repository.update(db_session, id0, owner_id, 1, "t0", None, "todo", None, None, 2)

	positions = {}
	for tid in (id0, id1, id2):
		result = await task_repository.get_by_id(db_session, tid)
		assert result is not None
		positions[str(tid)] = result.task.position
	assert sorted(positions.values()) == [0, 1, 2]
	assert positions[str(id0)] == 2
	assert positions[str(id1)] == 0
	assert positions[str(id2)] == 1


async def test_move_status_appends_to_tail_of_new_column(db_session: AsyncSession) -> None:
	owner_id, project_id = await _setup_project(db_session, "grace")
	id0 = await task_repository.create(db_session, project_id, owner_id, None, "t0", None, "todo", None, None)
	id1 = await task_repository.create(db_session, project_id, owner_id, None, "t1", None, "todo", None, None)
	await task_repository.create(
		db_session, project_id, owner_id, None, "existing-in-progress", None, "in_progress", None, None
	)

	await task_repository.update(db_session, id0, owner_id, 1, "t0", None, "in_progress", None, None, None)

	moved = await task_repository.get_by_id(db_session, id0)
	remaining = await task_repository.get_by_id(db_session, id1)
	assert moved is not None
	assert moved.task.status == "in_progress"
	assert moved.task.position == 1
	assert remaining is not None
	assert remaining.task.status == "todo"
	assert remaining.task.position == 0


async def test_deactivate_task_does_not_compact_positions(db_session: AsyncSession) -> None:
	owner_id, project_id = await _setup_project(db_session, "heidi")
	id0 = await task_repository.create(db_session, project_id, owner_id, None, "t0", None, "todo", None, None)
	id1 = await task_repository.create(db_session, project_id, owner_id, None, "t1", None, "todo", None, None)

	await task_repository.set_active(db_session, id0, False)

	deactivated = await task_repository.get_by_id(db_session, id0)
	remaining = await task_repository.get_by_id(db_session, id1)
	assert deactivated is not None
	assert deactivated.task.is_active is False
	assert deactivated.task.position == 0
	assert remaining is not None
	assert remaining.task.position == 1


async def test_reactivate_task_restores_is_active(db_session: AsyncSession) -> None:
	owner_id, project_id = await _setup_project(db_session, "ivan")
	task_id = await task_repository.create(db_session, project_id, owner_id, None, "t0", None, "todo", None, None)
	await task_repository.set_active(db_session, task_id, False)

	await task_repository.set_active(db_session, task_id, True)

	result = await task_repository.get_by_id(db_session, task_id)
	assert result is not None
	assert result.task.is_active is True


async def test_list_board_excludes_inactive_by_default(db_session: AsyncSession) -> None:
	owner_id, project_id = await _setup_project(db_session, "judy")
	active_id = await task_repository.create(db_session, project_id, owner_id, None, "a", None, "todo", None, None)
	inactive_id = await task_repository.create(db_session, project_id, owner_id, None, "b", None, "todo", None, None)
	await task_repository.set_active(db_session, inactive_id, False)

	board_default = await task_repository.list_board(db_session, project_id, False)
	board_all = await task_repository.list_board(db_session, project_id, True)

	assert {r.task.id for r in board_default} == {active_id}
	assert {r.task.id for r in board_all} == {active_id, inactive_id}


async def test_advisory_lock_prevents_position_collision_under_concurrency(db_session: AsyncSession) -> None:
	owner_id, project_id = await _setup_project(db_session, "karen")
	await db_session.commit()

	settings = get_backend_settings()
	engine = create_async_engine(settings.database_url)
	session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

	async def _create_one(index: int) -> uuid.UUID:
		async with session_factory() as session:
			task_id = await task_repository.create(
				session, project_id, owner_id, None, f"concurrent-{index}", None, "todo", None, None
			)
			await session.commit()
			return task_id

	try:
		task_ids = await asyncio.gather(*(_create_one(i) for i in range(5)))
	finally:
		await engine.dispose()

	positions = []
	for task_id in task_ids:
		result = await task_repository.get_by_id(db_session, task_id)
		assert result is not None
		positions.append(result.task.position)

	assert sorted(positions) == [0, 1, 2, 3, 4]
