from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import (
	get_current_user,
	require_project_member,
	require_project_owner,
	verify_csrf_if_session,
	verify_origin,
)
from app.db import get_db_session
from app.models.project import Project
from app.schemas.auth import CurrentUser
from app.schemas.project import (
	ProjectCreateRequest,
	ProjectDetailResponse,
	ProjectListResponse,
	ProjectSummaryResponse,
	ProjectUpdateRequest,
)
from app.schemas.project_member import (
	AddMemberRequest,
	CandidateListResponse,
	CandidateSearchQuery,
	MemberListResponse,
	MemberResponse,
)
from app.service import member_service, project_service

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=ProjectListResponse)
async def list_projects(
	page: int = Query(default=1, ge=1),
	per_page: int = Query(default=20, ge=1, le=100),
	include_inactive: bool = False,
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
) -> ProjectListResponse:
	return await project_service.list_projects(user, page, per_page, include_inactive, db)


@router.post("", response_model=ProjectSummaryResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
	payload: ProjectCreateRequest,
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(verify_origin),
	__csrf: None = Depends(verify_csrf_if_session),
) -> ProjectSummaryResponse:
	return await project_service.create_project(user, payload, db)


@router.get("/{project_id}", response_model=ProjectDetailResponse)
async def get_project(
	project: Project = Depends(require_project_member),
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
) -> ProjectDetailResponse:
	return await project_service.get_project_detail(db, project, user)


@router.patch("/{project_id}", response_model=ProjectSummaryResponse)
async def update_project(
	payload: ProjectUpdateRequest,
	project: Project = Depends(require_project_owner),
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(verify_origin),
	__csrf: None = Depends(verify_csrf_if_session),
) -> ProjectSummaryResponse:
	return await project_service.update_project(db, project, payload, user)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
	project: Project = Depends(require_project_owner),
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(verify_origin),
	__csrf: None = Depends(verify_csrf_if_session),
) -> Response:
	await project_service.deactivate_project(db, project)
	return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{project_id}/members", response_model=MemberListResponse)
async def list_project_members(
	project: Project = Depends(require_project_member), db: AsyncSession = Depends(get_db_session)
) -> MemberListResponse:
	return await member_service.list_members(project, db)


@router.post("/{project_id}/members", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
async def add_project_member(
	payload: AddMemberRequest,
	project: Project = Depends(require_project_owner),
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(verify_origin),
	__csrf: None = Depends(verify_csrf_if_session),
) -> MemberResponse:
	return await member_service.add_member(project, payload.user_id, user.id, db)


@router.get("/{project_id}/member-candidates", response_model=CandidateListResponse)
async def search_member_candidates(
	query: CandidateSearchQuery = Depends(),
	project: Project = Depends(require_project_owner),
	db: AsyncSession = Depends(get_db_session),
) -> CandidateListResponse:
	return await member_service.search_candidates(project, query.q, db)


@router.delete("/{project_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_project_member(
	user_id: UUID,
	project: Project = Depends(require_project_owner),
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(verify_origin),
	__csrf: None = Depends(verify_csrf_if_session),
) -> Response:
	await member_service.remove_member(project, user_id, db)
	return Response(status_code=status.HTTP_204_NO_CONTENT)
