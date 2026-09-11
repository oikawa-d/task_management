"""管理者によるプロジェクト操作の業務ロジック。

参照設計書:
- docs/detailed_design/api/admin/05_get_admin_projects.md
- docs/detailed_design/api/admin/06_delete_admin_project.md

`fn_admin_list_projects`はmember_count/task_countsを集計しないため、
（非admin向けの）`fn_list_projects`のような単一FNでの集計は利用できない。
本サービスは既存のFNベースrepository関数（`project_member_repository.list_by_project` /
`task_repository.list_board`）をプロジェクトごとに呼び出して集計する。
DBへ直接SQLを発行する新規repository関数は追加していない（repositoryはSP/FN契約のみを
呼び出す方針のため）。結果としてプロジェクト件数に比例したクエリが発生する
（要検討: 設計書§11のN+1対策を満たすには`fn_admin_list_projects`へ集計列を追加する
DB変更が必要だが、本issueはservice層に限定されるため対応していない）。
"""

import logging
from uuid import UUID

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_backend_settings
from app.core.exceptions import NotFoundError, ServiceUnavailableError
from app.models.project import Project
from app.models.user import User
from app.repository import admin_repository, project_member_repository, project_repository, task_repository
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


async def _to_summary(db: AsyncSession, project: Project) -> AdminProjectSummary:
	member_count, task_counts = await _member_count(db, project.id), await _task_counts(db, project.id)
	return AdminProjectSummary(
		id=project.id,
		name=project.name,
		description=project.description,
		owner=AdminProjectOwner(
			id=project.owner.id, username=project.owner.username, display_name=_display_name(project.owner)
		),
		member_count=member_count,
		task_counts=task_counts,
		is_active=project.is_active,
		start_at=project.start_at,
		end_at=project.end_at,
		created_at=project.created_at,
	)


async def list_projects(query: AdminProjectListQuery, db: AsyncSession) -> AdminProjectListResponse:
	"""検索・ページング条件で全プロジェクトを一覧取得する（05_get_admin_projects.md §6.2）。

	admin一覧は`is_active`の値によらず常に全件を返す（無効化済みも含む）。
	"""
	settings = get_backend_settings()
	offset = (query.page - 1) * query.per_page
	try:
		matched = await admin_repository.list_projects(db, query.q, None, settings.admin_list_count_query_limit, 0)
	except DBAPIError as exc:
		raise ServiceUnavailableError() from exc
	total = len(matched)
	page_projects = matched[offset : offset + query.per_page]
	items = [await _to_summary(db, project) for project in page_projects]
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
