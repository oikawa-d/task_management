import pytest
from app.core.exceptions import AlreadyMemberError
from app.repository import project_member_repository, project_repository, task_repository, user_repository
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession


async def test_owner_is_registered_as_member_on_project_creation(db_session: AsyncSession) -> None:
	owner_id = await user_repository.create(db_session, "alice", "alice@example.com", "hash")
	project_id = await project_repository.create(db_session, owner_id, "P", None, None, None)

	members = await project_member_repository.list_by_project(db_session, project_id)

	assert len(members) == 1
	assert members[0].user_id == owner_id
	assert members[0].invited_by is None


async def test_add_member_duplicate_raises_already_member(db_session: AsyncSession) -> None:
	owner_id = await user_repository.create(db_session, "bob", "bob@example.com", "hash")
	invitee_id = await user_repository.create(db_session, "invitee1", "invitee1@example.com", "hash")
	project_id = await project_repository.create(db_session, owner_id, "P", None, None, None)
	await project_member_repository.create(db_session, project_id, invitee_id, owner_id)

	with pytest.raises(AlreadyMemberError):
		await project_member_repository.create(db_session, project_id, invitee_id, owner_id)


async def test_exists_true_for_member_false_for_non_member(db_session: AsyncSession) -> None:
	owner_id = await user_repository.create(db_session, "carol", "carol@example.com", "hash")
	stranger_id = await user_repository.create(db_session, "stranger1", "stranger1@example.com", "hash")
	project_id = await project_repository.create(db_session, owner_id, "P", None, None, None)

	assert await project_member_repository.exists(db_session, project_id, owner_id) is True
	assert await project_member_repository.exists(db_session, project_id, stranger_id) is False


async def test_list_members_includes_inactive_members(db_session: AsyncSession) -> None:
	owner_id = await user_repository.create(db_session, "inactive_owner", "inactive-owner@example.com", "hash")
	member_id = await user_repository.create(db_session, "inactive_member", "inactive-member@example.com", "hash")
	project_id = await project_repository.create(db_session, owner_id, "P", None, None, None)
	await project_member_repository.create(db_session, project_id, member_id, owner_id)
	await db_session.execute(text("UPDATE users SET is_active = false WHERE id = :user_id"), {"user_id": member_id})

	members = await project_member_repository.list_by_project(db_session, project_id)

	assert {member.user_id for member in members} == {owner_id, member_id}


async def test_remove_owner_returns_p0004(db_session: AsyncSession) -> None:
	owner_id = await user_repository.create(db_session, "dave", "dave@example.com", "hash")
	project_id = await project_repository.create(db_session, owner_id, "P", None, None, None)

	with pytest.raises(DBAPIError) as exc_info:
		await project_member_repository.delete(db_session, project_id, owner_id)
	assert getattr(exc_info.value.orig, "sqlstate", None) == "P0004"


async def test_remove_member_nullifies_assigned_tasks(db_session: AsyncSession) -> None:
	owner_id = await user_repository.create(db_session, "erin", "erin@example.com", "hash")
	member_id = await user_repository.create(db_session, "member1", "member1@example.com", "hash")
	project_id = await project_repository.create(db_session, owner_id, "P", None, None, None)
	await project_member_repository.create(db_session, project_id, member_id, owner_id)
	task_id = await task_repository.create(
		db_session, project_id, owner_id, member_id, "task1", None, "todo", None, None
	)

	await project_member_repository.delete(db_session, project_id, member_id)

	result = await task_repository.get_by_id(db_session, task_id)
	assert result is not None
	assert result.task.assignee_id is None
	assert await project_member_repository.exists(db_session, project_id, member_id) is False


async def test_search_candidates_excludes_existing_members(db_session: AsyncSession) -> None:
	owner_id = await user_repository.create(db_session, "frank", "frank@example.com", "hash")
	candidate_id = await user_repository.create(db_session, "candidate_zzz", "candidate_zzz@example.com", "hash")
	project_id = await project_repository.create(db_session, owner_id, "P", None, None, None)

	before = await project_member_repository.search_candidates(db_session, project_id, "candidate", 10, 0)
	assert any(u.id == candidate_id for u in before)

	await project_member_repository.create(db_session, project_id, candidate_id, owner_id)

	after = await project_member_repository.search_candidates(db_session, project_id, "candidate", 10, 0)
	assert all(u.id != candidate_id for u in after)


async def test_search_candidates_excludes_inactive_users(db_session: AsyncSession) -> None:
	owner_id = await user_repository.create(db_session, "gina", "gina@example.com", "hash")
	inactive_id = await user_repository.create(db_session, "inactive_candidate", "inactive@example.com", "hash")
	project_id = await project_repository.create(db_session, owner_id, "P", None, None, None)
	await db_session.execute(text("UPDATE users SET is_active = false WHERE id = :user_id"), {"user_id": inactive_id})

	candidates = await project_member_repository.search_candidates(db_session, project_id, "inactive", 10, 0)

	assert all(user.id != inactive_id for user in candidates)


async def test_search_candidates_matches_display_name_prefix(db_session: AsyncSession) -> None:
	owner_id = await user_repository.create(db_session, "hannah", "hannah@example.com", "hash")
	candidate_id = await user_repository.create(db_session, "display_candidate", "display@example.com", "hash")
	project_id = await project_repository.create(db_session, owner_id, "P", None, None, None)
	await db_session.execute(
		text("UPDATE users SET last_name = '山田', first_name = '花子' WHERE id = :user_id"),
		{"user_id": candidate_id},
	)

	candidates = await project_member_repository.search_candidates(db_session, project_id, "山田", 10, 0)

	assert [user.id for user in candidates] == [candidate_id]
