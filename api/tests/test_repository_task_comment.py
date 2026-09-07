from app.repository import project_repository, task_comment_repository, task_repository, user_repository
from sqlalchemy.ext.asyncio import AsyncSession


async def _setup_task(db: AsyncSession, username: str):
	owner_id = await user_repository.create(db, username, f"{username}@example.com", "hash")
	project_id = await project_repository.create(db, owner_id, "P", None, None, None)
	task_id = await task_repository.create(db, project_id, owner_id, None, "task", None, "todo", None, None)
	return owner_id, task_id


async def test_add_comment_success(db_session: AsyncSession) -> None:
	owner_id, task_id = await _setup_task(db_session, "alice")

	comment_id = await task_comment_repository.create(db_session, task_id, owner_id, "hello")

	comment = await task_comment_repository.get_by_id(db_session, comment_id)
	assert comment is not None
	assert comment.body == "hello"
	assert comment.user_id == owner_id


async def test_get_by_id_not_found_returns_none(db_session: AsyncSession) -> None:
	import uuid

	comment = await task_comment_repository.get_by_id(db_session, uuid.uuid4())
	assert comment is None


async def test_list_comments_ordered_by_created_at_asc(db_session: AsyncSession) -> None:
	owner_id, task_id = await _setup_task(db_session, "bob")
	first_id = await task_comment_repository.create(db_session, task_id, owner_id, "first")
	await db_session.commit()
	second_id = await task_comment_repository.create(db_session, task_id, owner_id, "second")

	comments = await task_comment_repository.list_by_task(db_session, task_id)

	assert [c.id for c in comments] == [first_id, second_id]


async def test_update_comment_changes_body(db_session: AsyncSession) -> None:
	owner_id, task_id = await _setup_task(db_session, "carol")
	comment_id = await task_comment_repository.create(db_session, task_id, owner_id, "original")

	await task_comment_repository.update(db_session, comment_id, owner_id, "edited")

	comment = await task_comment_repository.get_by_id(db_session, comment_id)
	assert comment is not None
	assert comment.body == "edited"


async def test_delete_comment_removes_row(db_session: AsyncSession) -> None:
	owner_id, task_id = await _setup_task(db_session, "dave")
	comment_id = await task_comment_repository.create(db_session, task_id, owner_id, "to delete")

	await task_comment_repository.delete(db_session, comment_id, owner_id)

	comment = await task_comment_repository.get_by_id(db_session, comment_id)
	assert comment is None


async def test_deactivate_task_does_not_delete_comments(db_session: AsyncSession) -> None:
	owner_id, task_id = await _setup_task(db_session, "erin")
	comment_id = await task_comment_repository.create(db_session, task_id, owner_id, "still here")

	await task_repository.set_active(db_session, task_id, False)

	comment = await task_comment_repository.get_by_id(db_session, comment_id)
	assert comment is not None
	assert comment.body == "still here"
