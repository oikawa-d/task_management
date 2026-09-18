"""タスクコメントの一覧・追加・更新・削除を扱うサービス。"""

from typing import Protocol, cast

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, raise_database_error
from app.models.task import Task
from app.models.task_comment import TaskComment
from app.repository import task_comment_repository
from app.schemas.auth import CurrentUser
from app.schemas.comment import CommentAuthor, CommentCreateRequest, CommentListResponse, CommentResponse
from app.service.authorization_service import require_comment_editor, require_task_access


class _DisplayNameUser(Protocol):
	"""表示名算出に必要な最小限の属性（`username`）を持つユーザーの構造的型。"""

	username: str


class _NamedDisplayNameUser(_DisplayNameUser, Protocol):
	"""姓名を保持し、より詳細な表示名算出が可能なユーザーの構造的型。"""

	last_name: str | None
	first_name: str | None


def _display_name(user: _DisplayNameUser) -> str:
	"""ユーザーの表示名を組み立てる。

	姓名属性を持つユーザーであれば「姓 名」を、姓名が未設定または
	姓名属性を持たないユーザーであれば`username`を表示名として用いる。

	Args:
		user: 表示名を求める対象ユーザー（`CurrentUser`等）。

	Returns:
		str: 表示に用いるユーザー名。
	"""
	if hasattr(user, "last_name") and hasattr(user, "first_name"):
		named_user = cast(_NamedDisplayNameUser, user)
		return " ".join(part for part in (named_user.last_name, named_user.first_name) if part) or user.username
	return user.username


def _comment_response(comment: TaskComment, fallback_user: CurrentUser | None = None) -> CommentResponse:
	"""コメントレコードをレスポンス用の要素へ変換する。

	コメントに紐づく投稿者が取得できない場合（リレーション未ロード等）は、
	`fallback_user`（直前に投稿操作を行ったユーザー）で代替する。

	Args:
		comment: 変換対象のタスクコメント。
		fallback_user: 投稿者情報が取得できない場合に代替する操作ユーザー。

	Returns:
		CommentResponse: レスポンス表示用のコメント要素。

	Raises:
		NotFoundError: 投稿者情報も`fallback_user`も得られない場合。
	"""
	author = comment.author or fallback_user
	if author is None:
		raise NotFoundError()
	return CommentResponse(
		id=comment.id,
		task_id=comment.task_id,
		body=comment.body,
		author=CommentAuthor(id=author.id, username=author.username, display_name=_display_name(author)),
		created_at=comment.created_at,
		updated_at=comment.updated_at,
	)


async def list_comments(task: Task, user: CurrentUser, db: AsyncSession) -> CommentListResponse:
	"""タスクに紐づく全コメントを一覧取得する。

	取得前にタスクへのアクセス権を検証する。

	Args:
		task: 対象タスク。
		user: 操作を行った認証済みユーザー。
		db: アクセス検証・コメント取得に使用する非同期DBセッション。

	Returns:
		CommentListResponse: コメント一覧と件数。

	Raises:
		NotFoundError: タスクが非アクティブ、または`user`にアクセス権がない場合
			（`require_task_access`による）。
	"""
	await require_task_access(task, user, db)
	comments = await task_comment_repository.list_by_task(db, task.id)
	return CommentListResponse(
		task_id=task.id,
		items=[_comment_response(comment) for comment in comments],
		count=len(comments),
	)


async def add_comment(
	task: Task, payload: CommentCreateRequest, user: CurrentUser, db: AsyncSession
) -> CommentResponse:
	"""タスクへ新規コメントを追加する。

	追加前にタスクへのアクセス権を検証する。コメント作成・再取得・
	コミットが本関数のトランザクション境界であり、いずれかで失敗した場合は
	ロールバックする。

	Args:
		task: コメント対象のタスク。
		payload: 追加するコメント本文を含むリクエスト。
		user: 投稿者となる認証済みユーザー。
		db: アクセス検証・コメント作成に使用する非同期DBセッション。

	Returns:
		CommentResponse: 作成されたコメント。

	Raises:
		NotFoundError: タスクへのアクセス権がない場合、または作成後の
			再取得に失敗した場合（想定外の不整合）。
		app.core.exceptions.AppError: DB更新でSQLSTATEエラーが発生した場合、
			`raise_database_error`により業務例外へ変換されて送出される。
	"""
	await require_task_access(task, user, db)
	try:
		comment_id = await task_comment_repository.create(db, task.id, user.id, payload.body)
		comment = await task_comment_repository.get_by_id(db, comment_id)
		if comment is None:
			raise NotFoundError()
		response = _comment_response(comment, user)
		await db.commit()
		return response
	except DBAPIError as exc:
		await db.rollback()
		raise_database_error(exc)
	except Exception:
		await db.rollback()
		raise


async def update_comment(
	task: Task,
	comment: TaskComment,
	payload: CommentCreateRequest,
	user: CurrentUser,
	db: AsyncSession,
) -> CommentResponse:
	"""既存のタスクコメントを更新する。

	更新前にタスクへのアクセス権と、コメント投稿者本人または管理者であることを
	検証する。コメント更新・再取得・コミットが本関数のトランザクション境界であり、
	いずれかで失敗した場合はロールバックする。

	Args:
		task: コメント対象のタスク。
		comment: 更新対象の既存コメント。
		payload: 更新後のコメント本文を含むリクエスト。
		user: 操作を行った認証済みユーザー。
		db: アクセス検証・コメント更新に使用する非同期DBセッション。

	Returns:
		CommentResponse: 更新後のコメント。

	Raises:
		NotFoundError: タスクへのアクセス権がない場合、または更新後の
			再取得に失敗した場合（想定外の不整合）。
		ForbiddenError: コメント投稿者本人でも管理者でもない場合。
		app.core.exceptions.AppError: DB更新でSQLSTATEエラーが発生した場合、
			`raise_database_error`により業務例外へ変換されて送出される。
	"""
	await require_task_access(task, user, db)
	require_comment_editor(comment.user_id, user)
	try:
		await task_comment_repository.update(db, comment.id, user.id, payload.body)
		updated = await task_comment_repository.get_by_id(db, comment.id)
		if updated is None:
			raise NotFoundError()
		response = _comment_response(updated, user)
		await db.commit()
		return response
	except DBAPIError as exc:
		await db.rollback()
		raise_database_error(exc)
	except Exception:
		await db.rollback()
		raise


async def delete_comment(task: Task, comment: TaskComment, user: CurrentUser, db: AsyncSession) -> None:
	"""タスクコメントを削除する。

	削除前にタスクへのアクセス権と、コメント投稿者本人または管理者であることを
	検証する。コメント削除とコミットが本関数のトランザクション境界である。

	Args:
		task: コメント対象のタスク。
		comment: 削除対象の既存コメント。
		user: 操作を行った認証済みユーザー。
		db: アクセス検証・コメント削除に使用する非同期DBセッション。

	Returns:
		None

	Raises:
		NotFoundError: タスクへのアクセス権がない場合。
		ForbiddenError: コメント投稿者本人でも管理者でもない場合。
		app.core.exceptions.AppError: DB更新でSQLSTATEエラーが発生した場合、
			`raise_database_error`により業務例外へ変換されて送出される。
	"""
	await require_task_access(task, user, db)
	require_comment_editor(comment.user_id, user)
	try:
		await task_comment_repository.delete(db, comment.id, user.id)
		await db.commit()
	except DBAPIError as exc:
		await db.rollback()
		raise_database_error(exc)
	except Exception:
		await db.rollback()
		raise
