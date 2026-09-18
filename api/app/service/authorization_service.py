"""タスク・コメントに対する権限判定を行う認可サービス。

権限がない場合はリソースの存在を隠すため`NotFoundError`を用いる箇所と、
存在は明示したうえで操作のみを拒否する`ForbiddenError`を用いる箇所を区別する。
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.task import Task
from app.repository import project_member_repository
from app.schemas.auth import CurrentUser


async def require_task_access(task: Task, user: CurrentUser, db: AsyncSession) -> None:
	"""タスクへのアクセス権を検証する。

	論理削除済みタスク、非管理者による他人の未所属タスクへのアクセス、
	所属プロジェクトのメンバーでないユーザーからのアクセスを、いずれも
	存在の有無を秘匿するため`NotFoundError`として拒否する。管理者は
	常にアクセスを許可する。

	Args:
		task: アクセス対象のタスク。
		user: リクエストを行った認証済みユーザー。
		db: プロジェクトメンバー所属確認に使用する非同期DBセッション。

	Returns:
		None: アクセスが許可された場合は何も行わない。

	Raises:
		NotFoundError: タスクが非アクティブ、または権限がなくアクセスできない場合。
	"""
	if not task.is_active:
		raise NotFoundError()
	if user.role == "admin":
		return
	if task.project_id is None:
		if task.created_by == user.id:
			return
		raise NotFoundError()
	if not await project_member_repository.exists(db, task.project_id, user.id):
		raise NotFoundError()


def require_comment_editor(comment_user_id: uuid.UUID, user: CurrentUser) -> None:
	"""コメントの編集・削除権限を検証する。

	コメント投稿者本人、または管理者のみが操作可能とする。

	Args:
		comment_user_id: 対象コメントを投稿したユーザーのID。
		user: リクエストを行った認証済みユーザー。

	Returns:
		None: 権限がある場合は何も行わない。

	Raises:
		ForbiddenError: 投稿者本人でも管理者でもない場合。
	"""
	if user.role != "admin" and comment_user_id != user.id:
		raise ForbiddenError()
