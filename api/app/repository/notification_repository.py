"""通知(notifications テーブル)へのデータアクセス層。

各関数はトランザクションのcommit/rollbackを行わない。呼び出し元のservice層が
同一セッションのcommitを担う。
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification


@dataclass(frozen=True)
class NotificationListItem:
	"""fn_list_notifications の1行分（通知本体＋task情報＋全体件数）。"""

	notification: Notification
	task_title: str | None
	task_project_id: uuid.UUID | None
	total_count: int


def validate_page_window(limit: int, offset: int) -> None:
	"""ページング用パラメータの妥当性を検証する。

	Args:
		limit: 取得件数の上限。
		offset: 取得開始位置。

	Returns:
		None。

	Raises:
		ValueError: `limit`が1未満、または`offset`が負の場合。
	"""
	if limit < 1:
		raise ValueError("limit must be positive")
	if offset < 0:
		raise ValueError("offset must not be negative")


async def list_by_user(
	db: AsyncSession, user_id: uuid.UUID, unread_only: bool, limit: int, offset: int
) -> list[NotificationListItem]:
	"""指定ユーザーの通知一覧をページング付きで取得する。

	DB関数 `fn_list_notifications` を呼び出し、notifications テーブルを紐づく
	タスク情報とともに検索する。

	Args:
		db: 検索に使用する非同期DBセッション。
		user_id: 検索対象のユーザーID。
		unread_only: Trueの場合、未読の通知のみに絞り込む。
		limit: 取得件数の上限。
		offset: 取得開始位置(ページング用)。

	Returns:
		通知・関連タスク情報・全体件数を含むNotificationListItemのリスト。
		該当行が無い場合は空リスト。

	Raises:
		ValueError: `limit`が1未満、または`offset`が負の場合。
	"""
	validate_page_window(limit, offset)
	result = await db.execute(
		text(
			"SELECT (notification).*, task_title, task_project_id, total_count "
			"FROM fn_list_notifications(:user_id, :unread_only, :limit, :offset)"
		),
		{"user_id": user_id, "unread_only": unread_only, "limit": limit, "offset": offset},
	)
	rows = result.mappings().all()
	return [
		NotificationListItem(
			notification=Notification(
				id=row["id"],
				user_id=row["user_id"],
				task_id=row["task_id"],
				type=row["type"],
				title=row["title"],
				body=row["body"],
				due_at=row["due_at"],
				dedupe_key=row["dedupe_key"],
				read_at=row["read_at"],
				created_at=row["created_at"],
			),
			task_title=row["task_title"],
			task_project_id=row["task_project_id"],
			total_count=row["total_count"],
		)
		for row in rows
	]


async def count_notifications(db: AsyncSession, user_id: uuid.UUID, unread_only: bool) -> int:
	"""指定ユーザーの通知件数を取得する。

	`fn_list_notifications`の`total_count`が取得できない場合(該当0件)のフォールバック
	用件数取得として使用する。DB関数 `fn_count_notifications` を呼び出す。

	Args:
		db: 検索に使用する非同期DBセッション。
		user_id: 検索対象のユーザーID。
		unread_only: Trueの場合、未読の通知のみを対象に件数を数える。

	Returns:
		該当する通知の件数(0件の場合は0)。
	"""
	result = await db.execute(
		text("SELECT fn_count_notifications(:user_id, :unread_only) AS count"),
		{"user_id": user_id, "unread_only": unread_only},
	)
	return int(result.scalar_one())


async def count_unread(db: AsyncSession, user_id: uuid.UUID) -> int:
	"""指定ユーザーの未読通知件数を取得する。

	DB関数 `fn_count_unread_notifications` を呼び出す。

	Args:
		db: 検索に使用する非同期DBセッション。
		user_id: 検索対象のユーザーID。

	Returns:
		未読通知の件数(未読が無い場合は0)。
	"""
	result = await db.execute(
		text("SELECT fn_count_unread_notifications(:user_id) AS count"),
		{"user_id": user_id},
	)
	return int(result.scalar_one())


async def mark_read(db: AsyncSession, notification_id: uuid.UUID, user_id: uuid.UUID) -> datetime | None:
	"""指定通知を既読にする。

	ストアドプロシージャ `sp_mark_notification_read` を呼び出し、notifications テーブルの
	該当行を`FOR UPDATE`でロックしたうえで`read_at`を更新する副作用を持つ(既に既読の場合は
	既存の`read_at`を維持する)。本関数自体はcommitを行わず、呼び出し元のservice層が
	同一セッションでcommitする。

	Args:
		db: 更新に使用する非同期DBセッション。
		notification_id: 既読にする通知のID。
		user_id: 通知の所有者として照合するユーザーID。

	Returns:
		更新後の`read_at`。`notification_id`と`user_id`の組み合わせに該当する行が
		存在しない場合はNone。
	"""
	result = await db.execute(
		text("CALL sp_mark_notification_read(:notification_id, :user_id, NULL)"),
		{"notification_id": notification_id, "user_id": user_id},
	)
	return cast(datetime | None, result.mappings().one()["p_read_at"])


async def mark_all_read(db: AsyncSession, user_id: uuid.UUID) -> int:
	"""指定ユーザーの未読通知を全て既読にする。

	ストアドプロシージャ `sp_mark_all_notifications_read` を呼び出し、notifications
	テーブルの該当ユーザーの未読行を全て更新する副作用を持つ。本関数自体はcommitを
	行わず、呼び出し元のservice層が同一セッションでcommitする。

	Args:
		db: 更新に使用する非同期DBセッション。
		user_id: 対象ユーザーのID。

	Returns:
		既読に更新した件数(対象が無い場合は0)。
	"""
	result = await db.execute(text("CALL sp_mark_all_notifications_read(:user_id, NULL)"), {"user_id": user_id})
	return int(result.scalar_one())


async def purge_expired(db: AsyncSession, retention_days: int) -> None:
	"""保持期間を過ぎた古い通知を削除する。

	ストアドプロシージャ `sp_purge_notifications` を呼び出し、notifications テーブルから
	`retention_days` を超えて経過した行を削除する副作用を持つ。本関数自体はcommitを
	行わず、呼び出し元のservice層が同一セッションでcommitする。

	Args:
		db: 更新に使用する非同期DBセッション。
		retention_days: この日数より古い通知を削除対象とする保持日数。

	Returns:
		None。

	Raises:
		sqlalchemy.exc.DBAPIError: `retention_days`が0以下の場合、SP内部の
			`RAISE EXCEPTION 'p_retention_days must be positive'`が発生し、
			元の例外を再送出する。
	"""
	await db.execute(text("CALL sp_purge_notifications(:retention_days)"), {"retention_days": retention_days})
