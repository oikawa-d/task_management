from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.project import Project
from app.models.user import User
from app.repository import project_member_repository, project_repository, task_repository
from app.schemas.auth import CurrentUser
from app.schemas.project import (
	ProjectCreateRequest,
	ProjectDetailResponse,
	ProjectListMeta,
	ProjectListResponse,
	ProjectMember,
	ProjectOwner,
	ProjectSummaryResponse,
	ProjectTaskCounts,
	ProjectUpdateRequest,
)


def _display_name(user: User) -> str:
	return " ".join(part for part in (user.last_name, user.first_name) if part) or user.username


def _owner(user: User) -> ProjectOwner:
	return ProjectOwner(id=user.id, username=user.username, display_name=_display_name(user))


def _summary(
	project: Project,
	user_id: UUID,
	member_count: int = 0,
	task_counts: ProjectTaskCounts | None = None,
) -> ProjectSummaryResponse:
	return ProjectSummaryResponse(
		id=project.id,
		name=project.name,
		description=project.description,
		owner=_owner(project.owner),
		member_count=member_count,
		task_counts=task_counts or ProjectTaskCounts(todo=0, in_progress=0, done=0),
		is_owner=project.owner_id == user_id,
		is_active=project.is_active,
		start_at=project.start_at,
		end_at=project.end_at,
		created_at=project.created_at,
		updated_at=project.updated_at,
	)


def _counts(item: project_repository.ProjectListItem) -> ProjectTaskCounts:
	return ProjectTaskCounts(
		todo=item.task_count_todo,
		in_progress=item.task_count_in_progress,
		done=item.task_count_done,
	)


async def list_projects(
	user: CurrentUser,
	page: int,
	per_page: int,
	include_inactive: bool,
	db: AsyncSession,
) -> ProjectListResponse:
	offset = (page - 1) * per_page
	items = await project_repository.list_for_user(db, user.id, include_inactive, per_page, offset)
	responses = [_summary(item.project, user.id, item.member_count, _counts(item)) for item in items]
	total = sum(1 for _ in items)
	return ProjectListResponse(
		items=responses,
		meta=ProjectListMeta(
			page=page,
			per_page=per_page,
			total=total,
			total_pages=(total + per_page - 1) // per_page,
		),
	)


async def create_project(user: CurrentUser, payload: ProjectCreateRequest, db: AsyncSession) -> ProjectSummaryResponse:
	project_id = await project_repository.create(
		db, user.id, payload.name, payload.description, payload.start_at, payload.end_at
	)
	project = await project_repository.get_by_id(db, project_id)
	if project is None:
		raise NotFoundError("作成したプロジェクトを取得できません")
	return _summary(project, user.id, member_count=1)


async def get_project_detail(db: AsyncSession, project: Project, user: CurrentUser) -> ProjectDetailResponse:
	members = await project_member_repository.list_by_project(db, project.id)
	tasks = await task_repository.list_board(db, project.id, include_inactive=True)
	task_counts = ProjectTaskCounts(
		todo=sum(task.task.status == "todo" for task in tasks),
		in_progress=sum(task.task.status == "in_progress" for task in tasks),
		done=sum(task.task.status == "done" for task in tasks),
	)
	return ProjectDetailResponse(
		**_summary(project, user.id, len(members), task_counts).model_dump(),
		members=[
			ProjectMember(
				user_id=member.user_id,
				username=member.user.username,
				display_name=_display_name(member.user),
				is_owner=member.user_id == project.owner_id,
				joined_at=member.joined_at,
			)
			for member in members
		],
	)


async def update_project(
	db: AsyncSession, project: Project, payload: ProjectUpdateRequest, user: CurrentUser
) -> ProjectSummaryResponse:
	name = payload.name if payload.name is not None else project.name
	description = payload.description if "description" in payload.model_fields_set else project.description
	start_at = payload.start_at if payload.start_at is not None else project.start_at
	end_at = payload.end_at if payload.end_at is not None else project.end_at
	await project_repository.update(db, project.id, name, description, start_at, end_at)
	if payload.is_active is not None:
		await project_repository.set_active(db, project.id, payload.is_active)
	updated = await project_repository.get_by_id(db, project.id)
	if updated is None:
		raise NotFoundError("プロジェクトが見つかりません")
	return _summary(updated, user.id)


async def deactivate_project(db: AsyncSession, project: Project) -> None:
	await project_repository.set_active(db, project.id, False)
