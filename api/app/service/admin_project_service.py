"""管理者によるプロジェクト操作の業務ロジック。"""

import logging
from uuid import UUID

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ServiceUnavailableError
from app.models.user import User
from app.repository import admin_repository, project_member_repository, project_repository, task_repository
from app.repository.admin_repository import AdminProjectListItem
from app.schemas.admin import (
	AdminProjectListMeta,
	AdminProjectListQuery,
	AdminProjectListResponse,
	AdminProjectOwner,
	AdminProjectSummary,
	AdminProjectTaskCounts,
)
from app.schemas.auth import CurrentUser

logger = logging.getLogger("app.audit")


def _display_name(user: User) -> str:
	return " ".join(part for part in (user.last_name, user.first_name) if part) or user.username


async def _member_count(db: AsyncSession, project_id: UUID) -> int:
	members = await project_member_repository.list_by_project(db, project_id)
	return len(members)


async def _task_counts(db: AsyncSession, project_id: UUID) -> AdminProjectTaskCounts:
	tasks = await task_repository.list_board(db, project_id, include_inactive=True)
	return AdminProjectTaskCounts(
		todo=sum(item.task.status == "todo" for item in tasks),
		in_progress=sum(item.task.status == "in_progress" for item in tasks),
		done=sum(item.task.status == "done" for item in tasks),
	)


def _to_summary(row: AdminProjectListItem) -> AdminProjectSummary:
	project = row.project
	return AdminProjectSummary(
		id=project.id,
		name=project.name,
		description=project.description,
		owner=AdminProjectOwner(
			id=project.owner.id, username=project.owner.username, display_name=_display_name(project.owner)
		),
		member_count=row.member_count,
		task_counts=AdminProjectTaskCounts(
			todo=row.task_count_todo,
			in_progress=row.task_count_in_progress,
			done=row.task_count_done,
		),
		is_active=project.is_active,
		start_at=project.start_at,
		end_at=project.end_at,
		created_at=project.created_at,
	)


async def list_projects(query: AdminProjectListQuery, db: AsyncSession) -> AdminProjectListResponse:
	"""検索・ページング条件で全プロジェクトを一覧取得する（05_get_admin_projects.md §6.2）。

	admin一覧は`is_active`の値によらず常に全件を返す（無効化済みも含む）。
	fn_admin_list_projectsのtotal_countはウィンドウ関数のため該当ページが0件の場合のみ
	fn_count_admin_projectsへフォールバックする（#347レビュー対応）。
	"""
	offset = (query.page - 1) * query.per_page
	try:
		rows = await admin_repository.list_projects(db, query.q, None, query.per_page, offset)
		total = rows[0].total_count if rows else await admin_repository.count_projects(db, query.q, None)
	except DBAPIError as exc:
		raise ServiceUnavailableError() from exc
	items = [_to_summary(row) for row in rows]
	total_pages = (total + query.per_page - 1) // query.per_page if total else 0
	return AdminProjectListResponse(
		items=items,
		meta=AdminProjectListMeta(page=query.page, per_page=query.per_page, total=total, total_pages=total_pages),
	)


async def deactivate_project(actor: CurrentUser, project_id: UUID, db: AsyncSession) -> None:
	"""管理者が任意のプロジェクトを論理削除する（06_delete_admin_project.md §6.2）。

	所属・オーナーシップは問わない。存在しなければNotFoundError。
	`project_members` / `tasks` / `task_comments` は変更しない。
	"""
	try:
		project = await project_repository.get_by_id(db, project_id)
	except DBAPIError as exc:
		raise ServiceUnavailableError() from exc
	if project is None:
		raise NotFoundError("プロジェクトが見つかりません")
	owner_id = project.owner_id
	member_count = await _member_count(db, project_id)
	task_counts = await _task_counts(db, project_id)
	try:
		await admin_repository.deactivate_project(db, project_id, False)
		await db.commit()
	except DBAPIError as exc:
		await db.rollback()
		raise ServiceUnavailableError() from exc
	logger.warning(
		"admin deactivated project",
		extra={
			"actor_id": str(actor.id),
			"project_id": str(project_id),
			"owner_id": str(owner_id),
			"member_count": member_count,
			"task_counts": task_counts.model_dump(),
		},
	)
