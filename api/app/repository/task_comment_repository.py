"""タスクコメント(task_comments テーブル)へのデータアクセス層。

各関数はトランザクションのcommit/rollbackを行わない。呼び出し元のservice層が
同一セッションのcommitを担う。
"""

import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.task_comment import TaskComment


async def create(db: AsyncSession, task_id: uuid.UUID, user_id: uuid.UUID, body: str) -> uuid.UUID:
	"""タスクにコメントを1件追加する。

	ストアドプロシージャ `sp_add_task_comment` を呼び出し、task_comments テーブルに
	1行挿入する副作用を持つ。本関数自体はcommitを行わず、呼び出し元のservice層が
	同一セッションでcommitする。

	Args:
		db: 更新に使用する非同期DBセッション。
		task_id: コメント対象のタスクID。
		user_id: コメント投稿者のユーザーID。
		body: コメント本文。

	Returns:
		作成されたコメントのID。
	"""
	result = await db.execute(
		text("CALL sp_add_task_comment(:task_id, :user_id, :body, NULL)"),
		{"task_id": task_id, "user_id": user_id, "body": body},
	)
	comment_id: uuid.UUID = result.mappings().one()["p_comment_id"]
	return comment_id


async def list_by_task(db: AsyncSession, task_id: uuid.UUID) -> list[TaskComment]:
	"""指定タスクのコメント一覧を、投稿者情報付きで取得する。

	DB関数 `fn_list_task_comments` を呼び出し、task_comments テーブルを検索する。
	`selectinload`により投稿者(author)情報を追加でロードする。

	Args:
		db: 検索に使用する非同期DBセッション。
		task_id: 検索対象のタスクID。

	Returns:
		該当するTaskCommentのリスト(各要素は`author`をロード済み)。
		該当行が無い場合は空リスト。
	"""
	result = await db.execute(
		select(TaskComment)
		.from_statement(text("SELECT * FROM fn_list_task_comments(:task_id)"))
		.params(task_id=task_id)
		.options(selectinload(TaskComment.author))
		.execution_options(populate_existing=True)
	)
	return list(result.scalars().all())


async def get_by_id(db: AsyncSession, comment_id: uuid.UUID) -> TaskComment | None:
	"""コメントIDを指定して1件取得する。

	DB関数 `fn_get_comment_with_task` を呼び出し、task_comments テーブルを検索する。
	`selectinload`により投稿者(author)と紐づくタスク(task)情報を追加でロードする。

	Args:
		db: 検索に使用する非同期DBセッション。
		comment_id: 検索対象のコメントID。

	Returns:
		該当するTaskComment(`author`・`task`をロード済み)。
		該当行が存在しない場合はNone。
	"""
	result = await db.execute(
		select(TaskComment)
		.from_statement(text("SELECT * FROM fn_get_comment_with_task(:comment_id)"))
		.params(comment_id=comment_id)
		.options(selectinload(TaskComment.author), selectinload(TaskComment.task))
		.execution_options(populate_existing=True)
	)
	return result.scalars().one_or_none()


async def update(db: AsyncSession, comment_id: uuid.UUID, user_id: uuid.UUID, body: str) -> None:
	"""コメント本文を更新する。

	ストアドプロシージャ `sp_update_task_comment` を呼び出し、task_comments テーブルの
	該当行の`body`を更新する副作用を持つ。投稿者本人かどうかの検証はAPI層(呼び出し元)の
	責務であり、本SPは検証を行わない。該当行が存在しない場合も例外を送出せず無処理となる。
	本関数自体はcommitを行わず、呼び出し元のservice層が同一セッションでcommitする。

	Args:
		db: 更新に使用する非同期DBセッション。
		comment_id: 更新対象のコメントID。
		user_id: 更新を要求したユーザーID(認可チェックは呼び出し元の責務)。
		body: 更新後のコメント本文。

	Returns:
		None。
	"""
	await db.execute(
		text("CALL sp_update_task_comment(:comment_id, :user_id, :body)"),
		{"comment_id": comment_id, "user_id": user_id, "body": body},
	)


async def delete(db: AsyncSession, comment_id: uuid.UUID, user_id: uuid.UUID) -> None:
	"""コメントを削除する。

	ストアドプロシージャ `sp_delete_task_comment` を呼び出し、task_comments テーブルから
	該当行を削除する副作用を持つ。投稿者本人かどうかの検証はAPI層(呼び出し元)の責務であり、
	本SPは検証を行わない。該当行が存在しない場合も例外を送出せず無処理となる。
	本関数自体はcommitを行わず、呼び出し元のservice層が同一セッションでcommitする。

	Args:
		db: 更新に使用する非同期DBセッション。
		comment_id: 削除対象のコメントID。
		user_id: 削除を要求したユーザーID(認可チェックは呼び出し元の責務)。

	Returns:
		None。
	"""
	await db.execute(
		text("CALL sp_delete_task_comment(:comment_id, :user_id)"),
		{"comment_id": comment_id, "user_id": user_id},
	)
