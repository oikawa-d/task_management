"""タスクのボード表示・一覧・カレンダー表示・CRUDエンドポイント。

プロジェクト配下のエンドポイントはプロジェクトメンバーであることを要求し、
非メンバー・存在しない場合は404 NOT_FOUNDを返す。更新系はOrigin検証・CSRF検証も課す。
"""

from datetime import date
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_project_member, verify_csrf_if_session, verify_origin_if_session
from app.db import get_db_session
from app.models.project import Project
from app.schemas.auth import CurrentUser
from app.schemas.task import (
	BoardResponse,
	CalendarScope,
	CalendarTaskItem,
	CalendarTaskQuery,
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
	"""GET /api/projects/{project_id}/tasks: プロジェクトのタスクをステータス別ボード形式で取得する。

	認可: プロジェクトメンバーのみ（`require_project_member`、非メンバー・存在しない場合は404 NOT_FOUND）。

	Args:
		project: パスの`project_id`から解決された対象プロジェクト。
		include_inactive: Trueの場合、無効化済みタスクも含める。
		db: DBセッション。

	Returns:
		200 OKでステータス別に分類されたタスク一覧を返す。

	Raises:
		NotFoundError: プロジェクトが存在しない、または自分がメンバーでない場合（404 NOT_FOUND）。
	"""
	return await task_service.get_board(project.id, include_inactive, db)


@router.post("/api/projects/{project_id}/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_project_task(
	payload: TaskCreateRequest,
	project: Project = Depends(require_project_member),
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(verify_origin_if_session),
	__csrf: None = Depends(verify_csrf_if_session),
) -> TaskResponse:
	"""POST /api/projects/{project_id}/tasks: プロジェクト配下にタスクを作成する。

	認可: プロジェクトメンバーのみ（`require_project_member`、非メンバー・存在しない場合は404 NOT_FOUND）。
	sessionモードではOrigin検証・CSRF検証も課す（不正時403 CSRF_INVALID）。

	Args:
		payload: タイトル・担当者・期限等の作成情報。
		project: パスの`project_id`から解決された対象プロジェクト。
		user: 認証済みユーザー（作成者）。
		db: DBセッション。

	Returns:
		201 Createdで作成したタスクを返す。

	Raises:
		NotFoundError: プロジェクトが存在しない、または自分がメンバーでない場合（404 NOT_FOUND）。
		AssigneeInactiveError: 無効化済みユーザーを担当者に指定した場合（409 ASSIGNEE_INACTIVE）。
	"""
	return await task_service.create_task(project.id, payload, user, db)


@router.get("/api/tasks", response_model=TaskListResponse)
async def list_tasks(
	query: Annotated[TaskListQuery, Query()],
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
) -> TaskListResponse:
	"""GET /api/tasks: ログインユーザーが参照可能なタスクを横断的に一覧取得する。

	認可: 認証必須。`project_id`にUUIDを指定した場合、管理者以外はそのプロジェクトの
	メンバーであることを要求し、非メンバーなら404 NOT_FOUNDを返す。

	Args:
		query: プロジェクト絞り込み・ステータス・ページング等の検索条件。
		user: 認証済みユーザー。
		db: DBセッション。

	Returns:
		200 OKでタスク一覧を返す。

	Raises:
		NotFoundError: `project_id`指定先のプロジェクトに自分がメンバーでない場合（404 NOT_FOUND）。
	"""
	return await task_service.list_tasks(
		user,
		cast(UUID | Literal["unassigned"] | None, query.project_id),
		query.status,
		query.include_inactive,
		query.page,
		query.per_page,
		db,
	)


@router.get("/api/tasks/calendar", response_model=list[CalendarTaskItem])
async def list_calendar_tasks(
	from_date: date = Query(..., alias="from"),
	to_date: date = Query(..., alias="to"),
	scope: CalendarScope = Query(...),
	project_id: UUID | None = Query(None),
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
) -> list[CalendarTaskItem]:
	"""GET /api/tasks/calendar: 期限日を持つタスクをカレンダー表示用に一覧取得する。

	認可: 認証必須。`scope=project`指定時は、管理者以外はそのプロジェクトのメンバーであることを
	要求し、非メンバー・`project_id`未指定なら404 NOT_FOUNDを返す。

	Args:
		from_date: 取得範囲の開始日（アプリタイムゾーン基準）。
		to_date: 取得範囲の終了日（アプリタイムゾーン基準）。
		scope: `project`（指定プロジェクト内）または全体等の集計範囲。
		project_id: `scope=project`のとき対象とするプロジェクトID。
		user: 認証済みユーザー。
		db: DBセッション。

	Returns:
		200 OKで期限日つきタスクの一覧を返す。

	Raises:
		NotFoundError: `scope=project`で対象プロジェクトに自分がメンバーでない場合（404 NOT_FOUND）。
	"""
	query = CalendarTaskQuery(**{"from": from_date, "to": to_date, "scope": scope, "project_id": project_id})
	return await task_service.list_calendar_tasks(user, query, db)


@router.post("/api/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_flat_task(
	payload: TaskCreateFlatRequest,
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(verify_origin_if_session),
	__csrf: None = Depends(verify_csrf_if_session),
) -> TaskResponse:
	"""POST /api/tasks: プロジェクトに属さない個人タスク、または`project_id`指定のタスクを作成する。

	認可: 認証必須。sessionモードではOrigin検証・CSRF検証も課す（不正時403 CSRF_INVALID）。

	Args:
		payload: タイトル・担当者・期限・任意の`project_id`等の作成情報。
		user: 認証済みユーザー（作成者）。
		db: DBセッション。

	Returns:
		201 Createdで作成したタスクを返す。

	Raises:
		AssigneeInactiveError: 無効化済みユーザーを担当者に指定した場合（409 ASSIGNEE_INACTIVE）。
	"""
	return await task_service.create_task_flat(payload, user, db)


@router.get("/api/tasks/{task_id}", response_model=TaskDetailResponse)
async def get_task(
	task_id: UUID,
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
) -> TaskDetailResponse:
	"""GET /api/tasks/{task_id}: タスク詳細を取得する。

	認可: 認証必須。管理者以外は、個人タスクなら作成者本人、プロジェクトタスクなら
	そのプロジェクトのメンバーであることを要求し、満たさない・無効化済みタスクの場合は404 NOT_FOUND。

	Args:
		task_id: 取得対象タスクのID。
		user: 認証済みユーザー。
		db: DBセッション。

	Returns:
		200 OKでタスク詳細を返す。

	Raises:
		NotFoundError: タスクが存在しない、無効化済み、またはアクセス権が無い場合（404 NOT_FOUND）。
	"""
	return await task_service.get_task_detail(task_id, user, db)


@router.patch("/api/tasks/{task_id}", response_model=TaskResponse)
async def update_task(
	task_id: UUID,
	payload: TaskUpdateRequest,
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(verify_origin_if_session),
	__csrf: None = Depends(verify_csrf_if_session),
) -> TaskResponse:
	"""PATCH /api/tasks/{task_id}: タスクを更新する（楽観ロックによる競合検知あり）。

	認可: 認証必須。タスクを無効化する場合を除きタスクアクセス権を要求（管理者以外は
	個人タスクの作成者本人かプロジェクトメンバーであること、満たさなければ404 NOT_FOUND）。
	さらに有効/無効を切り替える場合、管理者以外は作成者本人またはプロジェクトオーナーのみ許可し、
	それ以外は403 FORBIDDENを返す。sessionモードではOrigin検証・CSRF検証も課す（不正時403 CSRF_INVALID）。

	Args:
		task_id: 更新対象タスクのID。
		payload: 更新内容と楽観ロック用の`version`。
		user: 認証済みユーザー。
		db: DBセッション。

	Returns:
		200 OKで更新後のタスクを返す。

	Raises:
		NotFoundError: タスクが存在しない、またはアクセス権が無い場合（404 NOT_FOUND）。
		ForbiddenError: 有効/無効切り替えを作成者・オーナー以外が行おうとした場合（403 FORBIDDEN）。
		TaskConflictError: `version`が最新でなく他者の更新と競合した場合（409 TASK_CONFLICT）。
		AssigneeInactiveError: 無効化済みユーザーを担当者に指定した場合（409 ASSIGNEE_INACTIVE）。
	"""
	return await task_service.update_task(task_id, payload, user, db)


@router.delete("/api/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
	task_id: UUID,
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(verify_origin_if_session),
	__csrf: None = Depends(verify_csrf_if_session),
) -> Response:
	"""DELETE /api/tasks/{task_id}: タスクを無効化する（論理削除）。

	認可: 認証必須。管理者以外は個人タスクの作成者本人かプロジェクトメンバーであることを要求し、
	満たさなければ404 NOT_FOUND。sessionモードではOrigin検証・CSRF検証も課す（不正時403 CSRF_INVALID）。

	Args:
		task_id: 削除対象タスクのID。
		user: 認証済みユーザー。
		db: DBセッション。

	Returns:
		204 No Contentを返す。

	Raises:
		NotFoundError: タスクが存在しない、またはアクセス権が無い場合（404 NOT_FOUND）。
	"""
	await task_service.delete_task(task_id, user, db)
	return Response(status_code=status.HTTP_204_NO_CONTENT)
