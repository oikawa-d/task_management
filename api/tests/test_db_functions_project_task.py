from app.repository import project_repository, task_repository, user_repository
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def test_fn_is_project_member_member_returns_true(db_session: AsyncSession) -> None:
	owner_id = await user_repository.create(db_session, "alice", "alice@example.com", "hash")
	project_id = await project_repository.create(db_session, owner_id, "P", None, None, None)

	result = (
		await db_session.execute(text("SELECT fn_is_project_member(:pid, :uid)"), {"pid": project_id, "uid": owner_id})
	).scalar_one()
	assert result is True


async def test_fn_is_project_member_non_member_returns_false(db_session: AsyncSession) -> None:
	owner_id = await user_repository.create(db_session, "bob", "bob@example.com", "hash")
	stranger_id = await user_repository.create(db_session, "stranger", "stranger@example.com", "hash")
	project_id = await project_repository.create(db_session, owner_id, "P", None, None, None)

	result = (
		await db_session.execute(
			text("SELECT fn_is_project_member(:pid, :uid)"), {"pid": project_id, "uid": stranger_id}
		)
	).scalar_one()
	assert result is False


async def test_fn_is_project_member_admin_bypasses_membership(db_session: AsyncSession) -> None:
	owner_id = await user_repository.create(db_session, "carol", "carol@example.com", "hash")
	admin_id = await user_repository.create(db_session, "admin1", "admin1@example.com", "hash")
	await db_session.execute(text("UPDATE users SET role = 'admin' WHERE id = :id"), {"id": admin_id})
	project_id = await project_repository.create(db_session, owner_id, "P", None, None, None)

	result = (
		await db_session.execute(text("SELECT fn_is_project_member(:pid, :uid)"), {"pid": project_id, "uid": admin_id})
	).scalar_one()
	assert result is True


async def test_fn_is_project_member_inactive_user_returns_false(db_session: AsyncSession) -> None:
	owner_id = await user_repository.create(db_session, "dave", "dave@example.com", "hash")
	project_id = await project_repository.create(db_session, owner_id, "P", None, None, None)
	await db_session.execute(text("UPDATE users SET is_active = false WHERE id = :id"), {"id": owner_id})

	result = (
		await db_session.execute(text("SELECT fn_is_project_member(:pid, :uid)"), {"pid": project_id, "uid": owner_id})
	).scalar_one()
	assert result is False


async def test_fn_next_task_position_empty_column_returns_zero(db_session: AsyncSession) -> None:
	owner_id = await user_repository.create(db_session, "erin", "erin@example.com", "hash")
	project_id = await project_repository.create(db_session, owner_id, "P", None, None, None)

	result = (
		await db_session.execute(text("SELECT fn_next_task_position(:pid, 'todo')"), {"pid": project_id})
	).scalar_one()
	assert result == 0


async def test_fn_list_tasks_unassigned_visible_only_to_creator(db_session: AsyncSession) -> None:
	creator_id = await user_repository.create(db_session, "frank", "frank@example.com", "hash")
	other_id = await user_repository.create(db_session, "grace", "grace@example.com", "hash")
	task_id = await task_repository.create(db_session, None, creator_id, None, "unassigned", None, "todo", None, None)

	own = await task_repository.list_for_user(db_session, creator_id, None, None, False, 50, 0)
	other = await task_repository.list_for_user(db_session, other_id, None, None, False, 50, 0)

	assert task_id in {t.id for t in own}
	assert task_id not in {t.id for t in other}


async def test_fn_list_tasks_non_member_cannot_see_project_scoped_tasks(db_session: AsyncSession) -> None:
	owner_id = await user_repository.create(db_session, "heidi", "heidi@example.com", "hash")
	stranger_id = await user_repository.create(db_session, "ivan", "ivan@example.com", "hash")
	project_id = await project_repository.create(db_session, owner_id, "P", None, None, None)
	await task_repository.create(db_session, project_id, owner_id, None, "t", None, "todo", None, None)

	result = await task_repository.list_for_user(db_session, stranger_id, project_id, None, False, 50, 0)

	assert result == []
