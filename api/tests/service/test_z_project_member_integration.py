import pytest
from app.core.exceptions import OwnerCannotBeRemovedError
from app.repository import project_member_repository, project_repository, user_repository
from app.service import member_service
from sqlalchemy.ext.asyncio import AsyncSession


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
