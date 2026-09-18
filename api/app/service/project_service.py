"""プロジェクトの一覧・作成・詳細取得・更新・無効化を扱うサービス。"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError, raise_database_error
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
	"""ユーザーの表示名を組み立てる。

	姓名が設定されていれば「姓 名」を、いずれも未設定であればログインIDである
	`username`を表示名として用いる。

	Args:
		user: 表示名を求める対象のユーザー。

	Returns:
		str: 表示に用いるユーザー名。
	"""
	return " ".join(part for part in (user.last_name, user.first_name) if part) or user.username


def _owner(user: User) -> ProjectOwner:
	"""ユーザーをプロジェクトオーナー情報へ変換する。

	Args:
		user: オーナーであるユーザー。

	Returns:
		ProjectOwner: レスポンス表示用のオーナー情報。
	"""
	return ProjectOwner(id=user.id, username=user.username, display_name=_display_name(user))


def _summary(
	project: Project,
	user_id: UUID,
	member_count: int = 0,
	task_counts: ProjectTaskCounts | None = None,
) -> ProjectSummaryResponse:
	"""プロジェクトをレスポンス用の要約へ変換する。

	`user_id`とオーナーIDを比較し、リクエストユーザーがオーナーか否かを判定して含める。

	Args:
		project: 変換対象のプロジェクト。
		user_id: オーナー判定に使用するリクエストユーザーのID。
		member_count: 含めるメンバー数（省略時0）。
		task_counts: 含めるステータス別タスク件数（省略時すべて0）。

	Returns:
		ProjectSummaryResponse: レスポンス表示用のプロジェクト要約。
	"""
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
	"""プロジェクト一覧取得結果の集計値をレスポンス用の件数へ変換する。

	Args:
		item: リポジトリから返されたプロジェクトとタスク件数集計の行。

	Returns:
		ProjectTaskCounts: todo/in_progress/doneそれぞれの件数。
	"""
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
	"""ログインユーザーが所属する（またはオーナーである）プロジェクトを一覧取得する。

	所属確認そのものはリポジトリ層のクエリ（`list_for_user`）が担う。

	Args:
		user: 一覧取得を行うログインユーザー。
		page: 取得ページ番号（1始まり）。
		per_page: 1ページあたりの件数。
		include_inactive: 無効化済みプロジェクトを含めるかどうか。
		db: 一覧取得に使用する非同期DBセッション。

	Returns:
		ProjectListResponse: 該当ページのプロジェクト一覧とページングメタ情報。
	"""
	offset = (page - 1) * per_page
	items = await project_repository.list_for_user(db, user.id, include_inactive, per_page, offset)
	responses = [_summary(item.project, user.id, item.member_count, _counts(item)) for item in items]
	total = items[0].total_count if items else 0
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
	"""新規プロジェクトを作成し、作成者をオーナーとして登録する。

	プロジェクト作成とその後の再取得・コミットが本関数のトランザクション境界であり、
	いずれかで失敗した場合はロールバックする。作成直後はオーナー本人のみが
	メンバーであるため`member_count=1`として返す。

	Args:
		user: プロジェクトを作成するログインユーザー（オーナーとなる）。
		payload: プロジェクト名・説明・開始日時・終了日時を含む作成リクエスト。
		db: プロジェクト作成に使用する非同期DBセッション。

	Returns:
		ProjectSummaryResponse: 作成されたプロジェクトの要約。

	Raises:
		NotFoundError: 作成後の再取得に失敗した場合（想定外の不整合）。
		app.core.exceptions.AppError: DB更新でSQLSTATEエラーが発生した場合、
			`raise_database_error`により業務例外へ変換されて送出される。
	"""
	try:
		project_id = await project_repository.create(
			db, user.id, payload.name, payload.description, payload.start_at, payload.end_at
		)
		project = await project_repository.get_by_id(db, project_id)
		if project is None:
			await db.rollback()
			raise NotFoundError("作成したプロジェクトを取得できません")
		await db.commit()
		return _summary(project, user.id, member_count=1)
	except DBAPIError as exc:
		await db.rollback()
		raise_database_error(exc)


async def get_project_detail(db: AsyncSession, project: Project, user: CurrentUser) -> ProjectDetailResponse:
	"""プロジェクトの詳細（メンバー一覧・タスク件数を含む）を取得する。

	アクセス権チェックはルーター側で完了している前提とし、本関数は
	集計と整形のみを行う。論理削除済みタスクも含めて件数を集計する。

	Args:
		db: メンバー・タスク取得に使用する非同期DBセッション。
		project: 対象プロジェクト。
		user: リクエストを行ったログインユーザー（オーナー判定に使用）。

	Returns:
		ProjectDetailResponse: プロジェクト詳細（メンバー一覧・タスク件数を含む）。
	"""
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
	"""プロジェクト情報を部分更新する。

	リクエストで指定されたフィールドのみを更新し、未指定フィールドは
	既存値を維持する（`model_fields_set`による部分更新判定）。
	開始日時・終了日時の前後関係は更新前にアプリケーション側で検証する。
	名称・説明・日時の更新、`is_active`のフラグ更新、再取得、コミットが
	本関数のトランザクション境界であり、いずれかで失敗した場合はロールバックする。

	Args:
		db: プロジェクト更新に使用する非同期DBセッション。
		project: 更新対象のプロジェクト（更新前の状態）。
		payload: 更新したいフィールドを含むリクエスト（未指定フィールドは維持）。
		user: 操作を行ったログインユーザー（オーナー判定に使用）。

	Returns:
		ProjectSummaryResponse: 更新後のプロジェクト要約。

	Raises:
		ValidationError: 終了日時が開始日時より前になる場合。
		NotFoundError: 更新後の再取得に失敗した場合（想定外の不整合）。
		app.core.exceptions.AppError: DB更新でSQLSTATEエラーが発生した場合、
			`raise_database_error`により業務例外へ変換されて送出される。
	"""
	name = payload.name if payload.name is not None else project.name
	description = payload.description if "description" in payload.model_fields_set else project.description
	start_at = payload.start_at if "start_at" in payload.model_fields_set else project.start_at
	end_at = payload.end_at if "end_at" in payload.model_fields_set else project.end_at
	if start_at is not None and end_at is not None and end_at < start_at:
		raise ValidationError("終了日時は開始日時以降である必要があります")
	try:
		await project_repository.update(db, project.id, name, description, start_at, end_at)
		if payload.is_active is not None:
			await project_repository.set_active(db, project.id, payload.is_active)
		updated = await project_repository.get_by_id(db, project.id)
		if updated is None:
			await db.rollback()
			raise NotFoundError("プロジェクトが見つかりません")
		await db.commit()
		return _summary(updated, user.id)
	except DBAPIError as exc:
		await db.rollback()
		raise_database_error(exc)


async def deactivate_project(db: AsyncSession, project: Project) -> None:
	"""プロジェクトを論理削除（無効化）する。

	権限チェックはルーター側（オーナーまたは管理者の判定）に委ねる。
	無効化フラグの更新とコミットが本関数のトランザクション境界である。

	Args:
		db: プロジェクト更新に使用する非同期DBセッション。
		project: 無効化対象のプロジェクト。

	Returns:
		None

	Raises:
		app.core.exceptions.AppError: DB更新でSQLSTATEエラーが発生した場合、
			`raise_database_error`により業務例外へ変換されて送出される。
	"""
	try:
		await project_repository.set_active(db, project.id, False)
		await db.commit()
	except DBAPIError as exc:
		await db.rollback()
		raise_database_error(exc)
