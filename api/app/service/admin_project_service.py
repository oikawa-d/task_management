"""管理者によるプロジェクト操作の業務ロジック。"""

import logging
from uuid import UUID

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, raise_database_error
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
	"""ユーザーの表示名を組み立てる。

	姓名が設定されていれば「姓 名」を、いずれも未設定であればログインIDである
	`username`を表示名として用いる。

	Args:
		user: 表示名を求める対象のユーザー。

	Returns:
		str: 表示に用いるユーザー名。
	"""
	return " ".join(part for part in (user.last_name, user.first_name) if part) or user.username


async def _member_count(db: AsyncSession, project_id: UUID) -> int:
	"""プロジェクトの現在のメンバー数を取得する（監査ログ記録用）。

	Args:
		db: メンバー一覧取得に使用する非同期DBセッション。
		project_id: 対象プロジェクトのID。

	Returns:
		int: プロジェクトに所属するメンバー数。
	"""
	members = await project_member_repository.list_by_project(db, project_id)
	return len(members)


async def _task_counts(db: AsyncSession, project_id: UUID) -> AdminProjectTaskCounts:
	"""プロジェクトのステータス別タスク件数を集計する（監査ログ記録用）。

	論理削除済みタスクも含めて集計する（`include_inactive=True`）。

	Args:
		db: タスク一覧取得に使用する非同期DBセッション。
		project_id: 対象プロジェクトのID。

	Returns:
		AdminProjectTaskCounts: todo/in_progress/doneそれぞれの件数。
	"""
	tasks = await task_repository.list_board(db, project_id, include_inactive=True)
	return AdminProjectTaskCounts(
		todo=sum(item.task.status == "todo" for item in tasks),
		in_progress=sum(item.task.status == "in_progress" for item in tasks),
		done=sum(item.task.status == "done" for item in tasks),
	)


def _to_summary(row: AdminProjectListItem) -> AdminProjectSummary:
	"""管理者向けプロジェクト一覧取得結果の1行をレスポンス要素へ変換する。

	Args:
		row: リポジトリから返されたプロジェクトとメンバー数・タスク件数の集計行。

	Returns:
		AdminProjectSummary: レスポンス表示用のプロジェクト要約。
	"""
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
	`fn_admin_list_projects`が返す`total_count`はウィンドウ関数によるものであり、
	該当ページの行が0件の場合は集計値も取得できないため、その場合に限り
	`fn_count_admin_projects`へフォールバックして総件数を取得する（#347レビュー対応）。

	Args:
		query: 検索語・ページ指定を含む検索条件。
		db: 検索に使用する非同期DBセッション。

	Returns:
		AdminProjectListResponse: 該当ページのプロジェクト一覧とページングメタ情報。

	Raises:
		app.core.exceptions.AppError: DB問い合わせでSQLSTATEエラーが発生した場合、
			`raise_database_error`によりSQLSTATEに対応する業務例外へ変換されて送出される。
	"""
	offset = (query.page - 1) * query.per_page
	try:
		rows = await admin_repository.list_projects(db, query.q, None, query.per_page, offset)
		total = rows[0].total_count if rows else await admin_repository.count_projects(db, query.q, None)
	except DBAPIError as exc:
		raise_database_error(exc)
	items = [_to_summary(row) for row in rows]
	total_pages = (total + query.per_page - 1) // query.per_page if total else 0
	return AdminProjectListResponse(
		items=items,
		meta=AdminProjectListMeta(page=query.page, per_page=query.per_page, total=total, total_pages=total_pages),
	)


async def deactivate_project(
	actor: CurrentUser, project_id: UUID, db: AsyncSession, request_id: str | None = None
) -> None:
	"""管理者が任意のプロジェクトを論理削除する（06_delete_admin_project.md §6.2）。

	権限チェックはルーター側の管理者ロール判定に委ね、本関数では
	所属・オーナーシップを問わず任意のプロジェクトを対象とする。
	論理削除（`is_active=false`への更新）とコミットが本関数のトランザクション境界であり、
	`project_members` / `tasks` / `task_comments` は変更しない。削除前の
	メンバー数・タスク件数はDB更新前に取得し、監査ログへ記録する。

	Args:
		actor: 削除操作を行った管理者ユーザー。監査ログに記録する。
		project_id: 論理削除対象のプロジェクトID。
		db: プロジェクト取得・更新に使用する非同期DBセッション。
		request_id: 監査ログに紐づけるリクエストID。

	Returns:
		None

	Raises:
		NotFoundError: 指定IDのプロジェクトが存在しない場合。
		app.core.exceptions.AppError: DB更新でSQLSTATEエラーが発生した場合、
			`raise_database_error`により業務例外へ変換されて送出される。
	"""
	try:
		project = await project_repository.get_by_id(db, project_id)
	except DBAPIError as exc:
		raise_database_error(exc)
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
		raise_database_error(exc)
	logger.warning(
		"admin deactivated project",
		extra={
			"actor_user_id": str(actor.id),
			"project_id": str(project_id),
			"request_id": request_id,
			"owner_id": str(owner_id),
			"member_count": member_count,
			"task_count_todo": task_counts.todo,
			"task_count_in_progress": task_counts.in_progress,
			"task_count_done": task_counts.done,
		},
	)
