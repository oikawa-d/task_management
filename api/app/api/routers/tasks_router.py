from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_project_member, verify_csrf, verify_origin
from app.db import get_db_session
from app.models.project import Project
from app.schemas.auth import CurrentUser
from app.schemas.task import (
	BoardResponse,
	TaskCreateFlatRequest,
	TaskCreateRequest,
	TaskDetailResponse,
	TaskListQuery,
	TaskListResponse,
	TaskResponse,
	TaskUpdateRequest,
)
from app.service import task_service

router = APIRouter(tags=["tasks"])


@router.get("/api/projects/{project_id}/tasks", response_model=BoardResponse)
async def get_project_board(
	project: Project = Depends(require_project_member),
	include_inactive: bool = False,
	db: AsyncSession = Depends(get_db_session),
) -> BoardResponse:
	return await task_service.get_board(project.id, include_inactive, db)


@router.post("/api/projects/{project_id}/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_project_task(
	payload: TaskCreateRequest,
	project: Project = Depends(require_project_member),
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(verify_origin),
	__csrf: None = Depends(verify_csrf),
) -> TaskResponse:
	return await task_service.create_task(project.id, payload, user, db)


@router.get("/api/tasks", response_model=TaskListResponse)
async def list_tasks(
	query: TaskListQuery = Depends(),
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
) -> TaskListResponse:
	return await task_service.list_tasks(
		user,
		query.project_id,
		query.status,
		query.include_inactive,
		query.page,
		query.per_page,
		db,
	)


@router.post("/api/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_flat_task(
	payload: TaskCreateFlatRequest,
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(verify_origin),
	__csrf: None = Depends(verify_csrf),
) -> TaskResponse:
	return await task_service.create_task_flat(payload, user, db)


@router.get("/api/tasks/{task_id}", response_model=TaskDetailResponse)
async def get_task(
	task_id: UUID,
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
) -> TaskDetailResponse:
	return await task_service.get_task_detail(task_id, user, db)


@router.patch("/api/tasks/{task_id}", response_model=TaskResponse)
async def update_task(
	task_id: UUID,
	payload: TaskUpdateRequest,
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(verify_origin),
	__csrf: None = Depends(verify_csrf),
) -> TaskResponse:
	return await task_service.update_task(task_id, payload, user, db)


@router.delete("/api/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
	task_id: UUID,
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(verify_origin),
	__csrf: None = Depends(verify_csrf),
) -> Response:
	await task_service.delete_task(task_id, user, db)
	return Response(status_code=status.HTTP_204_NO_CONTENT)
