"""タスクのボード表示・一覧・カレンダー表示・作成・更新・論理削除を扱うサービス。

タスク更新は`version`列による楽観ロックで保護され、バージョン不一致は
`TaskConflictError`（409 TASK_CONFLICT）として送出される。
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_backend_settings
from app.core.exceptions import (
	AssigneeInactiveError,
	ForbiddenError,
	NotFoundError,
	TaskConflictError,
	raise_database_error,
)
from app.models.task import Task
from app.repository import project_repository, task_repository
from app.schemas.auth import CurrentUser
from app.schemas.task import (
	BoardColumns,
	BoardResponse,
	CalendarTaskItem,
	CalendarTaskQuery,
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
from app.service.authorization_service import require_task_access

_TASK_WRITE_CONSTRAINT_ERRORS = (AssigneeInactiveError, TaskConflictError)
"""タスク作成・更新のDB関数が業務制約違反として送出しうる例外の集合。

これらは`raise_database_error`によるSQLSTATE変換より前に送出される
アプリケーション例外であり、送出時は他のDBAPIErrorと同様にロールバックしてから
そのまま再送出する。
"""


def _assignee(task: Task) -> TaskAssignee | None:
	"""タスクの担当者情報をレスポンス用の要素へ変換する。

	Args:
		task: 変換元のタスク。

	Returns:
		TaskAssignee | None: 担当者情報。未アサインの場合は`None`。
	"""
	if task.assignee is None:
		return None
	return TaskAssignee(id=task.assignee.id, username=task.assignee.username, display_name=_display_name(task.assignee))


def _display_name(user: object) -> str:
	"""ユーザーの表示名を組み立てる。

	姓名が設定されていれば「姓 名」を、いずれも未設定であればログインIDである
	`username`を表示名として用いる。

	Args:
		user: 表示名を求める対象ユーザー（属性アクセスのみを行うため型は問わない）。

	Returns:
		str: 表示に用いるユーザー名。
	"""
	last_name = getattr(user, "last_name", None)
	first_name = getattr(user, "first_name", None)
	return " ".join(part for part in (last_name, first_name) if part) or getattr(user, "username")


def _creator(task: Task, current_user: CurrentUser) -> TaskCreator:
	"""タスクの作成者情報をレスポンス用の要素へ変換する。

	リレーションから作成者が取得できない場合は、リクエストを行った
	現在のユーザーを作成者として代替する。

	Args:
		task: 変換元のタスク。
		current_user: 作成者が取得できない場合に代替する現在のユーザー。

	Returns:
		TaskCreator: レスポンス表示用の作成者情報。
	"""
	creator = task.creator
	if creator is None:
		return TaskCreator(id=current_user.id, username=current_user.username)
	return TaskCreator(id=creator.id, username=creator.username, display_name=_display_name(creator))


def _summary(task: Task, comment_count: int = 0) -> TaskSummary:
	"""タスクをボード・一覧表示用の要約へ変換する。

	Args:
		task: 変換対象のタスク。
		comment_count: 含めるコメント件数（省略時0）。

	Returns:
		TaskSummary: 表示用のタスク要約。
	"""
	return TaskSummary(
		id=task.id,
		title=task.title,
		description=task.description,
		assignee=_assignee(task),
		due_at=task.due_at,
		position=task.position,
		version=task.version,
		is_active=task.is_active,
		comment_count=comment_count,
		created_at=task.created_at,
		updated_at=task.updated_at,
	)


def _response(item: task_repository.TaskWithProjectStatus, current_user: CurrentUser) -> TaskDetailResponse:
	"""タスクをプロジェクト状態・コメント件数を含む詳細レスポンスへ変換する。

	Args:
		item: リポジトリから返されたタスクとプロジェクト有効状態・コメント件数の行。
		current_user: 作成者情報が取得できない場合に代替する現在のユーザー。

	Returns:
		TaskDetailResponse: レスポンス表示用のタスク詳細。
	"""
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
		comment_count=item.comment_count,
	)


async def get_board(project_id: UUID, include_inactive: bool, db: AsyncSession) -> BoardResponse:
	"""プロジェクトのカンバンボード（todo/in_progress/done列）を取得する。

	プロジェクトへのアクセス権チェックはルーター側に委ねる。

	Args:
		project_id: 対象プロジェクトのID。
		include_inactive: 論理削除済みタスクを含めるかどうか。
		db: タスク取得に使用する非同期DBセッション。

	Returns:
		BoardResponse: ステータス別に分類されたタスク一覧。
	"""
	items = await task_repository.list_board(db, project_id, include_inactive)
	columns: dict[str, list[TaskSummary]] = {"todo": [], "in_progress": [], "done": []}
	for item in items:
		if item.task.status in columns:
			columns[item.task.status].append(_summary(item.task, item.comment_count))
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
	"""ログインユーザーが閲覧可能なタスクを条件検索し、ページング結果を返す。

	`project_id_filter`にUUIDが指定された場合、管理者以外はそのプロジェクトの
	メンバーであることを要求し、メンバーでなければ存在を隠すため
	`NotFoundError`とする。`"unassigned"`指定は未所属タスクへの絞り込みを表す。

	Args:
		user: 検索を行うログインユーザー。
		project_id_filter: 絞り込み対象。UUID・`"unassigned"`・`None`（絞り込みなし）。
		status: ステータスによる絞り込み（`None`で絞り込みなし）。
		include_inactive: 論理削除済みタスクを含めるかどうか。
		page: 取得ページ番号（1始まり）。
		per_page: 1ページあたりの件数。
		db: 検索に使用する非同期DBセッション。

	Returns:
		TaskListResponse: 該当ページのタスク一覧とページングメタ情報。

	Raises:
		NotFoundError: 管理者以外が所属していないプロジェクトを指定した場合。
	"""
	project_id = project_id_filter if isinstance(project_id_filter, UUID) else None
	if (
		user.role != "admin"
		and isinstance(project_id_filter, UUID)
		and not await project_repository.is_member(db, project_id_filter, user.id)
	):
		raise NotFoundError()
	items, total = await task_repository.list_for_user_with_total(
		db,
		user.id,
		project_id,
		status,
		include_inactive,
		per_page,
		(page - 1) * per_page,
		project_id_filter == "unassigned",
	)
	responses = [TaskListItem(**_response(item, user).model_dump()) for item in items]
	return TaskListResponse(
		items=responses,
		meta=TaskListMeta(page=page, per_page=per_page, total=total, total_pages=(total + per_page - 1) // per_page),
	)


async def list_calendar_tasks(user: CurrentUser, query: CalendarTaskQuery, db: AsyncSession) -> list[CalendarTaskItem]:
	"""カレンダー表示用に、期間内の締切を持つタスクを一覧取得する。

	`scope="project"`の場合、管理者以外はプロジェクトメンバーであることを要求し、
	メンバーでなければ存在を隠すため`NotFoundError`とする。日付範囲は
	アプリケーションのタイムゾーン（`APP_TIMEZONE`）で解釈しUTCへ変換したうえで、
	終了日は翌日0時未満として範囲に含める。

	Args:
		user: 検索を行うログインユーザー。
		query: 取得範囲（scope・期間・project_id）を含むクエリ条件。
		db: 検索に使用する非同期DBセッション。

	Returns:
		list[CalendarTaskItem]: 締切日を持つタスクのカレンダー表示用一覧。

	Raises:
		NotFoundError: `scope="project"`で管理者以外が所属していない
			プロジェクトを指定した場合。
	"""
	if query.scope == "project" and user.role != "admin":
		if query.project_id is None or not await project_repository.is_member(db, query.project_id, user.id):
			raise NotFoundError()
	zone = ZoneInfo(get_backend_settings().app_timezone)
	from_utc = datetime.combine(query.from_date, time.min, tzinfo=zone).astimezone(UTC)
	to_utc = datetime.combine(query.to_date + timedelta(days=1), time.min, tzinfo=zone).astimezone(UTC)
	items = await task_repository.list_calendar(db, user.id, from_utc, to_utc, query.scope, query.project_id)
	return [
		CalendarTaskItem(
			**_response(item, user).model_dump(),
			due_date=item.task.due_at.astimezone(zone).date(),
		)
		for item in items
		if item.task.due_at is not None
	]


async def create_task(
	project_id: UUID | None, payload: TaskCreateRequest, user: CurrentUser, db: AsyncSession
) -> TaskResponse:
	"""タスクを新規作成する。

	プロジェクトへのアクセス権・担当者指定の妥当性チェックはDB関数側の制約に委ね、
	`AssigneeInactiveError`（無効化済みユーザーを担当者指定）等の業務制約違反は
	`_TASK_WRITE_CONSTRAINT_ERRORS`としてロールバック後そのまま再送出する。
	タスク作成・再取得・コミットが本関数のトランザクション境界である。

	Args:
		project_id: 所属先プロジェクトのID。未所属タスクの場合は`None`。
		payload: タイトル・説明・担当者・ステータス・締切等を含む作成リクエスト。
		user: 作成者となるログインユーザー。
		db: タスク作成に使用する非同期DBセッション。

	Returns:
		TaskResponse: 作成されたタスク。

	Raises:
		AssigneeInactiveError: 無効化済みユーザーを担当者に指定した場合。
		NotFoundError: 作成後の再取得に失敗した場合（想定外の不整合）。
		app.core.exceptions.AppError: DB更新でその他のSQLSTATEエラーが発生した場合、
			`raise_database_error`により業務例外へ変換されて送出される。
	"""
	try:
		try:
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
		except _TASK_WRITE_CONSTRAINT_ERRORS:
			await db.rollback()
			raise
		item = await task_repository.get_by_id(db, task_id)
		if item is None:
			await db.rollback()
			raise NotFoundError()
		response = _response(item, user)
		await db.commit()
		return response
	except DBAPIError as exc:
		await db.rollback()
		raise_database_error(exc)


async def create_task_flat(payload: TaskCreateFlatRequest, user: CurrentUser, db: AsyncSession) -> TaskResponse:
	"""プロジェクトIDをリクエストボディに含む形式でタスクを作成する（未所属タスク作成用）。

	`create_task`へ委譲するのみで、業務ルールは`create_task`と同一。

	Args:
		payload: プロジェクトIDを含むタスク作成リクエスト。
		user: 作成者となるログインユーザー。
		db: タスク作成に使用する非同期DBセッション。

	Returns:
		TaskResponse: 作成されたタスク。

	Raises:
		AssigneeInactiveError: 無効化済みユーザーを担当者に指定した場合。
		NotFoundError: 作成後の再取得に失敗した場合（想定外の不整合）。
		app.core.exceptions.AppError: DB更新でSQLSTATEエラーが発生した場合、
			`raise_database_error`により業務例外へ変換されて送出される。
	"""
	return await create_task(payload.project_id, payload, user, db)


async def update_task(task_id: UUID, payload: TaskUpdateRequest, user: CurrentUser, db: AsyncSession) -> TaskResponse:
	"""タスクを更新する。

	`payload.version`とDB上の現在のバージョンをDB関数側で比較する楽観ロックにより、
	別ユーザーが先に更新していた場合は`TaskConflictError`（409 TASK_CONFLICT）となる。
	権限判定は二段階で行う。(1) `is_active`を`True`から変更しない通常更新では
	`require_task_access`によるタスクアクセス権チェックを行う。(2) `is_active`を
	指定する場合（有効化・無効化）は、管理者・タスク作成者・所属プロジェクトの
	オーナーのいずれかでなければ`ForbiddenError`とする。
	未指定フィールドはDB更新時に現在値を渡すことで維持する（部分更新）。
	タスク更新・再取得・コミットが本関数のトランザクション境界であり、
	業務制約違反（`_TASK_WRITE_CONSTRAINT_ERRORS`）はロールバック後そのまま再送出する。

	Args:
		task_id: 更新対象のタスクID。
		payload: 更新内容とバージョン番号を含むリクエスト。
		user: 操作を行ったログインユーザー。
		db: タスク取得・更新に使用する非同期DBセッション。

	Returns:
		TaskResponse: 更新後のタスク。

	Raises:
		NotFoundError: タスクが存在しない場合、タスクへのアクセス権がない場合、
			または更新後の再取得に失敗した場合（想定外の不整合）。
		ForbiddenError: `is_active`変更を管理者・作成者・プロジェクトオーナーの
			いずれでもないユーザーが試みた場合。
		TaskConflictError: `payload.version`がDB上の現在バージョンと一致しない場合。
		AssigneeInactiveError: 無効化済みユーザーを担当者に指定した場合。
		app.core.exceptions.AppError: DB更新でその他のSQLSTATEエラーが発生した場合、
			`raise_database_error`により業務例外へ変換されて送出される。
	"""
	item = await task_repository.get_by_id(db, task_id)
	if item is None:
		raise NotFoundError()
	task = item.task
	if task.is_active or payload.is_active is not True:
		await require_task_access(task, user, db)
	if payload.is_active is not None and user.role != "admin":
		is_creator = task.created_by == user.id
		project = await project_repository.get_by_id(db, task.project_id) if task.project_id else None
		if not is_creator and (project is None or project.owner_id != user.id):
			raise ForbiddenError()
	try:
		try:
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
				payload.is_active,
			)
		except _TASK_WRITE_CONSTRAINT_ERRORS:
			await db.rollback()
			raise
		updated = await task_repository.get_by_id(db, task_id)
		if updated is None:
			await db.rollback()
			raise NotFoundError()
		response = _response(updated, user)
		await db.commit()
		return response
	except DBAPIError as exc:
		await db.rollback()
		raise_database_error(exc)


async def deactivate_task(task_id: UUID, user: CurrentUser, db: AsyncSession) -> None:
	"""タスクを論理削除（無効化）する。

	更新前にタスクへのアクセス権を検証する。無効化フラグの更新とコミットが
	本関数のトランザクション境界である。

	Args:
		task_id: 無効化対象のタスクID。
		user: 操作を行ったログインユーザー。
		db: タスク取得・更新に使用する非同期DBセッション。

	Returns:
		None

	Raises:
		NotFoundError: タスクが存在しない場合、またはアクセス権がない場合。
		app.core.exceptions.AppError: DB更新でSQLSTATEエラーが発生した場合、
			`raise_database_error`により業務例外へ変換されて送出される。
	"""
	item = await task_repository.get_by_id(db, task_id)
	if item is None:
		raise NotFoundError()
	await require_task_access(item.task, user, db)
	try:
		await task_repository.set_active(db, task_id, False)
		await db.commit()
	except DBAPIError as exc:
		await db.rollback()
		raise_database_error(exc)


async def get_task_detail(task_id: UUID, user: CurrentUser, db: AsyncSession) -> TaskDetailResponse:
	"""タスクの詳細を取得する。

	取得前にタスクへのアクセス権を検証する。

	Args:
		task_id: 取得対象のタスクID。
		user: 操作を行ったログインユーザー。
		db: タスク取得に使用する非同期DBセッション。

	Returns:
		TaskDetailResponse: タスク詳細。

	Raises:
		NotFoundError: タスクが存在しない場合、またはアクセス権がない場合。
	"""
	item = await task_repository.get_by_id(db, task_id)
	if item is None:
		raise NotFoundError()
	await require_task_access(item.task, user, db)
	return _response(item, user)


async def delete_task(task_id: UUID, user: CurrentUser, db: AsyncSession) -> None:
	"""タスクを削除する（内部的には論理削除）。

	`deactivate_task`への委譲であり、業務ルールは同一。

	Args:
		task_id: 削除対象のタスクID。
		user: 操作を行ったログインユーザー。
		db: タスク取得・更新に使用する非同期DBセッション。

	Returns:
		None

	Raises:
		NotFoundError: タスクが存在しない場合、またはアクセス権がない場合。
		app.core.exceptions.AppError: DB更新でSQLSTATEエラーが発生した場合、
			`raise_database_error`により業務例外へ変換されて送出される。
	"""
	await deactivate_task(task_id, user, db)
