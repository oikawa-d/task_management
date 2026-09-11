from datetime import datetime, timezone
from math import ceil
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_backend_settings
from app.core.exceptions import NotFoundError
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
	if value.tzinfo is None:
		value = value.replace(tzinfo=timezone.utc)
	return value.astimezone(ZoneInfo(get_backend_settings().app_timezone))


def _to_item(item: NotificationListItem) -> NotificationItem:
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
	return UnreadCountResponse(unread_count=await notification_repository.count_unread(db, user.id))


async def mark_notification_read(
	db: AsyncSession, notification_id: UUID, user: CurrentUser
) -> NotificationReadResponse:
	read_at = await notification_repository.mark_read(db, notification_id, user.id)
	if read_at is None:
		raise NotFoundError()
	return NotificationReadResponse(
		id=notification_id,
		read_at=_to_app_timezone(read_at),
		unread_count=await notification_repository.count_unread(db, user.id),
	)


async def mark_all_notifications_read(db: AsyncSession, user: CurrentUser) -> NotificationReadAllResponse:
	before = await notification_repository.count_unread(db, user.id)
	await notification_repository.mark_all_read(db, user.id)
	after = await notification_repository.count_unread(db, user.id)
	return NotificationReadAllResponse(updated_count=max(before - after, 0), unread_count=after)
