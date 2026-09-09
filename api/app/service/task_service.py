from __future__ import annotations

from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.task import Task
from app.repository import task_repository
from app.schemas.auth import CurrentUser
from app.schemas.task import (
	BoardColumns,
	BoardResponse,
	TaskAssignee,
	TaskCreateFlatRequest,
	TaskCreateRequest,
	TaskCreator,
	TaskDetailResponse,
	TaskListItem,
	TaskListMeta,
	TaskListResponse,
	TaskResponse,
	TaskSummary,
	TaskUpdateRequest,
)


def _assignee(task: Task) -> TaskAssignee | None:
	if task.assignee is None:
		return None
	return TaskAssignee(id=task.assignee.id, username=task.assignee.username, display_name=_display_name(task.assignee))


def _display_name(user: object) -> str:
	last_name = getattr(user, "last_name", None)
	first_name = getattr(user, "first_name", None)
	return " ".join(part for part in (last_name, first_name) if part) or getattr(user, "username")


def _creator(task: Task, current_user: CurrentUser) -> TaskCreator:
	creator = task.creator
	if creator is None:
		return TaskCreator(id=current_user.id, username=current_user.username)
	return TaskCreator(id=creator.id, username=creator.username, display_name=_display_name(creator))


def _summary(task: Task) -> TaskSummary:
	return TaskSummary(
		id=task.id,
		title=task.title,
		description=task.description,
		assignee=_assignee(task),
		due_at=task.due_at,
		position=task.position,
		version=task.version,
		is_active=task.is_active,
		comment_count=0,
		created_at=task.created_at,
		updated_at=task.updated_at,
	)


def _response(item: task_repository.TaskWithProjectStatus, current_user: CurrentUser) -> TaskDetailResponse:
	task = item.task
	return TaskDetailResponse(
		id=task.id,
		project_id=task.project_id,
		project_is_active=item.project_is_active,
		title=task.title,
		description=task.description,
		status=task.status,
		assignee=_assignee(task),
		created_by=_creator(task, current_user),
		position=task.position,
		version=task.version,
		is_active=task.is_active,
		due_at=task.due_at,
		created_at=task.created_at,
		updated_at=task.updated_at,
		comment_count=0,
	)


async def get_board(project_id: UUID, include_inactive: bool, db: AsyncSession) -> BoardResponse:
	items = await task_repository.list_board(db, project_id, include_inactive)
	columns: dict[str, list[TaskSummary]] = {"todo": [], "in_progress": [], "done": []}
	for item in items:
		if item.task.status in columns:
			columns[item.task.status].append(_summary(item.task))
	return BoardResponse(
		project_id=project_id,
		project_is_active=all(item.project_is_active is not False for item in items),
		columns=BoardColumns(**columns),
	)


async def list_tasks(
	user: CurrentUser,
	project_id_filter: UUID | Literal["unassigned"] | None,
	status: str | None,
	include_inactive: bool,
	page: int,
	per_page: int,
	db: AsyncSession,
) -> TaskListResponse:
	project_id = project_id_filter if isinstance(project_id_filter, UUID) else None
	items = await task_repository.list_for_user(
		db, user.id, project_id, status, include_inactive, per_page, (page - 1) * per_page
	)
	responses = [TaskListItem(**_response(item, user).model_dump()) for item in items]
	return TaskListResponse(
		items=responses,
		meta=TaskListMeta(page=page, per_page=per_page, total=len(responses), total_pages=1 if responses else 0),
	)


async def create_task(
	project_id: UUID | None, payload: TaskCreateRequest, user: CurrentUser, db: AsyncSession
) -> TaskResponse:
	task_id = await task_repository.create(
		db,
		project_id,
		user.id,
		payload.assignee_id,
		payload.title,
		payload.description,
		payload.status,
		payload.due_at,
		None,
	)
	item = await task_repository.get_by_id(db, task_id)
	if item is None:
		raise NotFoundError()
	return _response(item, user)


async def create_task_flat(payload: TaskCreateFlatRequest, user: CurrentUser, db: AsyncSession) -> TaskResponse:
	return await create_task(payload.project_id, payload, user, db)


async def update_task(task_id: UUID, payload: TaskUpdateRequest, user: CurrentUser, db: AsyncSession) -> TaskResponse:
	item = await task_repository.get_by_id(db, task_id)
	if item is None:
		raise NotFoundError()
	task = item.task
	await task_repository.update(
		db,
		task_id,
		user.id,
		payload.version,
		payload.title if payload.title is not None else task.title,
		payload.description if "description" in payload.model_fields_set else task.description,
		payload.status if payload.status is not None else task.status,
		payload.assignee_id if "assignee_id" in payload.model_fields_set else task.assignee_id,
		payload.due_at if "due_at" in payload.model_fields_set else task.due_at,
		payload.position if payload.position is not None else task.position,
	)
	updated = await task_repository.get_by_id(db, task_id)
	if updated is None:
		raise NotFoundError()
	return _response(updated, user)


async def deactivate_task(task_id: UUID, db: AsyncSession) -> None:
	if await task_repository.get_by_id(db, task_id) is None:
		raise NotFoundError()
	await task_repository.set_active(db, task_id, False)


async def get_task_detail(task_id: UUID, user: CurrentUser, db: AsyncSession) -> TaskDetailResponse:
	item = await task_repository.get_by_id(db, task_id)
	if item is None:
		raise NotFoundError()
	return _response(item, user)


async def delete_task(task_id: UUID, user: CurrentUser, db: AsyncSession) -> None:
	await deactivate_task(task_id, db)
