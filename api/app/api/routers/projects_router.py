"""プロジェクトおよびプロジェクトメンバーのCRUDエンドポイント。

参照系はプロジェクトメンバー、更新・メンバー管理系はプロジェクトオーナー（または管理者）を要求し、
満たさない場合は404 NOT_FOUND（非メンバー）または403 FORBIDDEN（メンバーだが非オーナー）を返す。
更新系はOrigin検証・CSRF検証も課す。
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import (
	get_current_user,
	require_project_member,
	require_project_owner,
	verify_csrf_if_session,
	verify_origin_if_session,
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
	"""GET /api/projects: 自分が所属するプロジェクトの一覧を取得する。

	認可: 認証必須（未認証は401 UNAUTHENTICATED）。

	Args:
		page: ページ番号（1始まり）。
		per_page: 1ページあたりの件数（最大100）。
		include_inactive: Trueの場合、無効化済みプロジェクトも含める。
		user: 認証済みユーザー。
		db: DBセッション。

	Returns:
		200 OKでプロジェクト一覧を返す。
	"""
	return await project_service.list_projects(user, page, per_page, include_inactive, db)


@router.post("", response_model=ProjectSummaryResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
	payload: ProjectCreateRequest,
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(verify_origin_if_session),
	__csrf: None = Depends(verify_csrf_if_session),
) -> ProjectSummaryResponse:
	"""POST /api/projects: 新規プロジェクトを作成する。作成者がオーナー兼メンバーとなる。

	認可: 認証必須。sessionモードではOrigin検証・CSRF検証も課す（不正時403 CSRF_INVALID）。

	Args:
		payload: プロジェクト名・説明等の作成情報。
		user: 認証済みユーザー（作成者）。
		db: DBセッション。

	Returns:
		201 Createdで作成したプロジェクトを返す。
	"""
	return await project_service.create_project(user, payload, db)


@router.get("/{project_id}", response_model=ProjectDetailResponse)
async def get_project(
	project: Project = Depends(require_project_member),
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
) -> ProjectDetailResponse:
	"""GET /api/projects/{project_id}: プロジェクト詳細を取得する。

	認可: プロジェクトメンバーのみ（`require_project_member`、非メンバー・存在しない場合は404 NOT_FOUND）。

	Args:
		project: パスの`project_id`から解決された対象プロジェクト。
		user: 認証済みユーザー。
		db: DBセッション。

	Returns:
		200 OKでプロジェクト詳細を返す。

	Raises:
		NotFoundError: プロジェクトが存在しない、または自分がメンバーでない場合（404 NOT_FOUND）。
	"""
	return await project_service.get_project_detail(db, project, user)


@router.patch("/{project_id}", response_model=ProjectSummaryResponse)
async def update_project(
	payload: ProjectUpdateRequest,
	project: Project = Depends(require_project_owner),
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(verify_origin_if_session),
	__csrf: None = Depends(verify_csrf_if_session),
) -> ProjectSummaryResponse:
	"""PATCH /api/projects/{project_id}: プロジェクト情報を更新する。

	認可: プロジェクトオーナーまたは管理者のみ（`require_project_owner`）。
	非メンバー・存在しない場合は404 NOT_FOUND、メンバーだがオーナーでない場合は403 FORBIDDEN。
	sessionモードではOrigin検証・CSRF検証も課す（不正時403 CSRF_INVALID）。

	Args:
		payload: 更新内容。
		project: パスの`project_id`から解決された対象プロジェクト。
		user: 認証済みユーザー。
		db: DBセッション。

	Returns:
		200 OKで更新後のプロジェクトを返す。

	Raises:
		NotFoundError: プロジェクトが存在しない、または自分がメンバーでない場合（404 NOT_FOUND）。
		ForbiddenError: オーナー・管理者以外が更新しようとした場合（403 FORBIDDEN）。
		ValidationError: 終了日時が開始日時より前など、入力の整合性が取れない場合（422 VALIDATION_ERROR）。
	"""
	return await project_service.update_project(db, project, payload, user)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
	project: Project = Depends(require_project_owner),
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(verify_origin_if_session),
	__csrf: None = Depends(verify_csrf_if_session),
) -> Response:
	"""DELETE /api/projects/{project_id}: プロジェクトを無効化する。

	認可: プロジェクトオーナーまたは管理者のみ（`require_project_owner`）。
	非メンバー・存在しない場合は404 NOT_FOUND、メンバーだがオーナーでない場合は403 FORBIDDEN。
	sessionモードではOrigin検証・CSRF検証も課す（不正時403 CSRF_INVALID）。

	Args:
		project: パスの`project_id`から解決された対象プロジェクト。
		db: DBセッション。

	Returns:
		204 No Contentを返す。

	Raises:
		NotFoundError: プロジェクトが存在しない、または自分がメンバーでない場合（404 NOT_FOUND）。
		ForbiddenError: オーナー・管理者以外が削除しようとした場合（403 FORBIDDEN）。
	"""
	await project_service.deactivate_project(db, project)
	return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{project_id}/members", response_model=MemberListResponse)
async def list_project_members(
	project: Project = Depends(require_project_member), db: AsyncSession = Depends(get_db_session)
) -> MemberListResponse:
	"""GET /api/projects/{project_id}/members: プロジェクトメンバー一覧を取得する。

	認可: プロジェクトメンバーのみ（`require_project_member`、非メンバー・存在しない場合は404 NOT_FOUND）。

	Args:
		project: パスの`project_id`から解決された対象プロジェクト。
		db: DBセッション。

	Returns:
		200 OKでメンバー一覧を返す。

	Raises:
		NotFoundError: プロジェクトが存在しない、または自分がメンバーでない場合（404 NOT_FOUND）。
	"""
	return await member_service.list_members(project, db)


@router.post("/{project_id}/members", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
async def add_project_member(
	payload: AddMemberRequest,
	project: Project = Depends(require_project_owner),
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(verify_origin_if_session),
	__csrf: None = Depends(verify_csrf_if_session),
) -> MemberResponse:
	"""POST /api/projects/{project_id}/members: プロジェクトにメンバーを追加する。

	認可: プロジェクトオーナーまたは管理者のみ（`require_project_owner`）。
	非メンバー・存在しない場合は404 NOT_FOUND、メンバーだがオーナーでない場合は403 FORBIDDEN。
	sessionモードではOrigin検証・CSRF検証も課す（不正時403 CSRF_INVALID）。

	Args:
		payload: 追加対象ユーザーのID。
		project: パスの`project_id`から解決された対象プロジェクト。
		user: 認証済みユーザー（招待者）。
		db: DBセッション。

	Returns:
		201 Createdで追加したメンバーを返す。

	Raises:
		NotFoundError: プロジェクトまたは追加対象ユーザーが存在しない場合（404 NOT_FOUND）。
		ForbiddenError: オーナー・管理者以外が追加しようとした場合（403 FORBIDDEN）。
		AlreadyMemberError: 対象ユーザーが既にメンバーの場合（409 ALREADY_MEMBER）。
	"""
	return await member_service.add_member(project, payload.user_id, user.id, db)


@router.get("/{project_id}/member-candidates", response_model=CandidateListResponse)
async def search_member_candidates(
	query: CandidateSearchQuery = Depends(),
	project: Project = Depends(require_project_owner),
	db: AsyncSession = Depends(get_db_session),
) -> CandidateListResponse:
	"""GET /api/projects/{project_id}/member-candidates: 追加候補ユーザーを検索する。

	認可: プロジェクトオーナーまたは管理者のみ（`require_project_owner`）。
	非メンバー・存在しない場合は404 NOT_FOUND、メンバーだがオーナーでない場合は403 FORBIDDEN。

	Args:
		query: ユーザー名等の検索クエリ。
		project: パスの`project_id`から解決された対象プロジェクト。
		db: DBセッション。

	Returns:
		200 OKで候補ユーザー一覧を返す。

	Raises:
		NotFoundError: プロジェクトが存在しない、または自分がメンバーでない場合（404 NOT_FOUND）。
		ForbiddenError: オーナー・管理者以外が検索しようとした場合（403 FORBIDDEN）。
	"""
	return await member_service.search_candidates(project, query.q, db)


@router.delete("/{project_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_project_member(
	user_id: UUID,
	project: Project = Depends(require_project_owner),
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(verify_origin_if_session),
	__csrf: None = Depends(verify_csrf_if_session),
) -> Response:
	"""DELETE /api/projects/{project_id}/members/{user_id}: プロジェクトからメンバーを削除する。

	認可: プロジェクトオーナーまたは管理者のみ（`require_project_owner`）。
	非メンバー・存在しない場合は404 NOT_FOUND、メンバーだがオーナーでない場合は403 FORBIDDEN。
	sessionモードではOrigin検証・CSRF検証も課す（不正時403 CSRF_INVALID）。

	Args:
		user_id: 削除対象ユーザーのID。
		project: パスの`project_id`から解決された対象プロジェクト。
		db: DBセッション。

	Returns:
		204 No Contentを返す。

	Raises:
		NotFoundError: プロジェクトまたは対象メンバーが存在しない場合（404 NOT_FOUND）。
		ForbiddenError: オーナー・管理者以外が削除しようとした場合（403 FORBIDDEN）。
		OwnerCannotBeRemovedError: オーナー自身を削除しようとした場合（409 OWNER_CANNOT_BE_REMOVED）。
	"""
	await member_service.remove_member(project, user_id, db)
	return Response(status_code=status.HTTP_204_NO_CONTENT)
