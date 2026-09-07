from app.repository import project_repository, task_repository, user_repository
from sqlalchemy.ext.asyncio import AsyncSession


async def test_get_task_project_is_active_false_for_inactive_project(db_session: AsyncSession) -> None:
	owner_id = await user_repository.create(db_session, "alice", "alice@example.com", "hash")
	project_id = await project_repository.create(db_session, owner_id, "P", None, None, None)
	task_id = await task_repository.create(db_session, project_id, owner_id, None, "t", None, "todo", None, None)
	await project_repository.set_active(db_session, project_id, False)

	result = await task_repository.get_by_id(db_session, task_id)

	assert result is not None
	assert result.project_is_active is False


async def test_get_task_project_is_active_true_for_active_project(db_session: AsyncSession) -> None:
	owner_id = await user_repository.create(db_session, "bob", "bob@example.com", "hash")
	project_id = await project_repository.create(db_session, owner_id, "P", None, None, None)
	task_id = await task_repository.create(db_session, project_id, owner_id, None, "t", None, "todo", None, None)

	result = await task_repository.get_by_id(db_session, task_id)

	assert result is not None
	assert result.project_is_active is True


async def test_get_task_project_is_active_null_when_unassigned(db_session: AsyncSession) -> None:
	owner_id = await user_repository.create(db_session, "carol", "carol@example.com", "hash")
	task_id = await task_repository.create(db_session, None, owner_id, None, "t", None, "todo", None, None)

	result = await task_repository.get_by_id(db_session, task_id)

	assert result is not None
	assert result.project_is_active is None


async def test_list_board_includes_project_is_active(db_session: AsyncSession) -> None:
	owner_id = await user_repository.create(db_session, "dave", "dave@example.com", "hash")
	project_id = await project_repository.create(db_session, owner_id, "P", None, None, None)
	await task_repository.create(db_session, project_id, owner_id, None, "t", None, "todo", None, None)
	await project_repository.set_active(db_session, project_id, False)

	board = await task_repository.list_board(db_session, project_id, True)

	assert len(board) == 1
	assert board[0].project_is_active is False


async def test_list_for_user_includes_project_is_active_null_when_unassigned(db_session: AsyncSession) -> None:
	owner_id = await user_repository.create(db_session, "erin", "erin@example.com", "hash")
	task_id = await task_repository.create(db_session, None, owner_id, None, "t", None, "todo", None, None)

	results = await task_repository.list_for_user(db_session, owner_id, None, None, False, 50, 0)

	target = next(r for r in results if r.task.id == task_id)
	assert target.project_is_active is None
