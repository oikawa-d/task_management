from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_backend_settings
from app.core.exceptions import AlreadyMemberError, NotFoundError, OwnerCannotBeRemovedError
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.repository import project_member_repository, user_repository
from app.schemas.project_member import (
	CandidateListResponse,
	CandidateSummary,
	MemberListMeta,
	MemberListResponse,
	MemberResponse,
	MemberSummary,
)


def _display_name(member: ProjectMember) -> str | None:
	parts = (member.user.last_name, member.user.first_name)
	return " ".join(part for part in parts if part) or None


def _member_summary(member: ProjectMember, owner_id: UUID) -> MemberSummary:
	return MemberSummary(
		user_id=member.user_id,
		username=member.user.username,
		display_name=_display_name(member),
		role=member.user.role,
		is_owner=member.user_id == owner_id,
		is_active=member.user.is_active,
		joined_at=member.joined_at,
	)


async def list_members(project: Project, db: AsyncSession) -> MemberListResponse:
	members = await project_member_repository.list_by_project(db, project.id)
	return MemberListResponse(
		items=[_member_summary(member, project.owner_id) for member in members],
		meta=MemberListMeta(total=len(members)),
	)


async def add_member(project: Project, user_id: UUID, invited_by: UUID, db: AsyncSession) -> MemberResponse:
	user = await user_repository.get_by_id(db, user_id)
	if user is None:
		raise NotFoundError()
	if await project_member_repository.exists(db, project.id, user_id):
		raise AlreadyMemberError()
	await project_member_repository.create(db, project.id, user_id, invited_by)
	members = await project_member_repository.list_by_project(db, project.id)
	created = next((member for member in members if member.user_id == user_id), None)
	if created is None:
		raise NotFoundError("追加したメンバーを取得できません")
	return MemberResponse.model_validate(_member_summary(created, project.owner_id))


async def search_candidates(project: Project, query: str, db: AsyncSession) -> CandidateListResponse:
	limit = get_backend_settings().pagination_default_per_page
	users = await project_member_repository.search_candidates(db, project.id, query, limit, 0)
	return CandidateListResponse(
		items=[
			CandidateSummary(
				user_id=user.id,
				username=user.username,
				display_name=" ".join(part for part in (user.last_name, user.first_name) if part) or None,
			)
			for user in users
		]
	)


async def remove_member(project: Project, user_id: UUID, db: AsyncSession) -> None:
	if user_id == project.owner_id:
		raise OwnerCannotBeRemovedError()
	if not await project_member_repository.exists(db, project.id, user_id):
		raise NotFoundError()
	await project_member_repository.delete(db, project.id, user_id)
