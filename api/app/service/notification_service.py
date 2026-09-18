"""通知の一覧取得・既読化を扱うサービス。"""

from datetime import datetime, timezone
from math import ceil
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_backend_settings
from app.core.exceptions import NotFoundError, raise_database_error
from app.repository import notification_repository
from app.repository.notification_repository import NotificationListItem
from app.schemas.auth import CurrentUser
from app.schemas.notification import (
	NotificationItem,
	NotificationListResponse,
	NotificationMeta,
	NotificationReadAllResponse,
	NotificationReadResponse,
	NotificationTask,
	UnreadCountResponse,
)


def _to_app_timezone(value: datetime) -> datetime:
	"""日時をアプリケーションのタイムゾーン（`APP_TIMEZONE`設定）へ変換する。

	タイムゾーン情報を持たない値はUTCとして扱ってから変換する。

	Args:
		value: 変換対象の日時。

	Returns:
		datetime: アプリケーションのタイムゾーンに変換された日時。
	"""
	if value.tzinfo is None:
		value = value.replace(tzinfo=timezone.utc)
	return value.astimezone(ZoneInfo(get_backend_settings().app_timezone))


def _to_item(item: NotificationListItem) -> NotificationItem:
	"""通知一覧取得結果の1行をレスポンス要素へ変換する。

	紐づくタスクが取得できた場合のみタスク情報を付与する。

	Args:
		item: リポジトリから返された通知と紐づくタスク情報の行。

	Returns:
		NotificationItem: レスポンス表示用の通知要素。
	"""
	notification = item.notification
	task = None
	if notification.task_id is not None and item.task_title is not None:
		task = NotificationTask(
			id=notification.task_id,
			project_id=item.task_project_id,
			title=item.task_title,
		)
	return NotificationItem(
		id=notification.id,
		type=notification.type,
		title=notification.title,
		body=notification.body,
		task=task,
		due_at=_to_app_timezone(notification.due_at) if notification.due_at else None,
		read_at=_to_app_timezone(notification.read_at) if notification.read_at else None,
		created_at=_to_app_timezone(notification.created_at),
	)


async def list_notifications(
	db: AsyncSession,
	user: CurrentUser,
	page: int,
	per_page: int,
	unread_only: bool,
) -> NotificationListResponse:
	"""ログインユーザー宛の通知を一覧取得する。

	`fn_list_notifications`が返す`total_count`はウィンドウ関数によるものであり、
	該当ページの行が0件の場合（例: ページ指定が総ページ数を超えた場合）は
	`fn_count_notifications`へフォールバックして総件数を取得する。
	`unread_only=True`の場合は取得件数がそのまま未読総数と一致するため、
	`count_unread`の追加呼び出しは行わない。

	Args:
		db: 通知一覧取得に使用する非同期DBセッション。
		user: 通知の宛先となるログインユーザー。
		page: 取得ページ番号（1始まり）。
		per_page: 1ページあたりの件数。
		unread_only: 未読の通知のみに絞り込むかどうか。

	Returns:
		NotificationListResponse: 該当ページの通知一覧、ページングメタ情報、未読件数。
	"""
	rows = await notification_repository.list_by_user(
		db, user.id, unread_only, limit=per_page, offset=(page - 1) * per_page
	)
	items = [_to_item(row) for row in rows]

	# fn_list_notificationsのtotal_countはウィンドウ関数のため該当行が0件だと取得できない
	# （pageが総ページ数を超えた場合等）。その場合のみ別途fn_count_notificationsで取得する。
	total = rows[0].total_count if rows else await notification_repository.count_notifications(db, user.id, unread_only)

	if unread_only:
		# unread_only=true時のtotalは全未読件数と一致するため、fn_count_unread_notificationsは追加で呼ばない
		unread_count = total
	else:
		unread_count = await notification_repository.count_unread(db, user.id)

	return NotificationListResponse(
		items=items,
		meta=NotificationMeta(
			page=page,
			per_page=per_page,
			total=total,
			total_pages=ceil(total / per_page) if total else 0,
		),
		unread_count=unread_count,
	)


async def get_unread_count(db: AsyncSession, user: CurrentUser) -> UnreadCountResponse:
	"""ログインユーザーの未読通知件数を取得する。

	Args:
		db: 集計に使用する非同期DBセッション。
		user: 集計対象のログインユーザー。

	Returns:
		UnreadCountResponse: 未読件数。
	"""
	return UnreadCountResponse(unread_count=await notification_repository.count_unread(db, user.id))


async def mark_notification_read(
	db: AsyncSession, notification_id: UUID, user: CurrentUser
) -> NotificationReadResponse:
	"""指定した通知を既読にする。

	通知が存在しない、または自分宛でない場合は既読化が行われず`None`が返る想定であり、
	その場合は`NotFoundError`を送出する（存在の有無を隠すため）。
	既読更新後の未読件数取得とコミットが本関数のトランザクション境界である。

	Args:
		db: 通知更新に使用する非同期DBセッション。
		notification_id: 既読にする通知のID。
		user: 操作を行ったログインユーザー（本人宛の通知のみ対象）。

	Returns:
		NotificationReadResponse: 既読化した通知のID・既読日時・更新後の未読件数。

	Raises:
		NotFoundError: 通知が存在しない、または自分宛でない場合。
		app.core.exceptions.AppError: DB更新でSQLSTATEエラーが発生した場合、
			`raise_database_error`により業務例外へ変換されて送出される。
	"""
	try:
		read_at = await notification_repository.mark_read(db, notification_id, user.id)
		if read_at is None:
			raise NotFoundError()
		unread_count = await notification_repository.count_unread(db, user.id)
		await db.commit()
		return NotificationReadResponse(
			id=notification_id,
			read_at=_to_app_timezone(read_at),
			unread_count=unread_count,
		)
	except DBAPIError as exc:
		await db.rollback()
		raise_database_error(exc)


async def mark_all_notifications_read(db: AsyncSession, user: CurrentUser) -> NotificationReadAllResponse:
	"""ログインユーザー宛の未読通知をすべて既読にする。

	一括更新後の未読件数取得とコミットが本関数のトランザクション境界である。

	Args:
		db: 通知更新に使用する非同期DBセッション。
		user: 操作を行ったログインユーザー。

	Returns:
		NotificationReadAllResponse: 既読化した件数と更新後の未読件数（通常0）。

	Raises:
		app.core.exceptions.AppError: DB更新でSQLSTATEエラーが発生した場合、
			`raise_database_error`により業務例外へ変換されて送出される。
	"""
	try:
		updated_count = await notification_repository.mark_all_read(db, user.id)
		after = await notification_repository.count_unread(db, user.id)
		await db.commit()
		return NotificationReadAllResponse(updated_count=updated_count, unread_count=after)
	except DBAPIError as exc:
		await db.rollback()
		raise_database_error(exc)
