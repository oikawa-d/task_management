"""ログインユーザー宛て通知の参照・既読化エンドポイント。

全エンドポイントは認証必須で、参照系・更新系それぞれ独立したレート制限を課す。
更新系はOrigin検証・CSRF検証も課す。
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import (
	enforce_notification_read_rate_limit,
	enforce_notification_write_rate_limit,
	get_current_user,
	verify_csrf_if_session,
	verify_origin_if_session,
)
from app.db import get_db_session
from app.schemas.auth import CurrentUser
from app.schemas.notification import (
	NotificationListResponse,
	NotificationReadAllResponse,
	NotificationReadResponse,
	UnreadCountResponse,
)
from app.service import notification_service

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
	page: int = Query(default=1, ge=1),
	per_page: int = Query(default=20, ge=1, le=100),
	unread_only: bool = False,
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(enforce_notification_read_rate_limit),
) -> NotificationListResponse:
	"""GET /api/notifications: ログインユーザー宛ての通知一覧を取得する。

	認可: 認証必須（未認証は401 UNAUTHENTICATED）。参照系レート制限を課す。

	Args:
		page: ページ番号（1始まり）。
		per_page: 1ページあたりの件数（最大100）。
		unread_only: Trueの場合、未読の通知のみに絞り込む。
		user: 認証済みユーザー。
		db: DBセッション。

	Returns:
		200 OKで通知一覧を返す。

	Raises:
		TooManyAttemptsError: レート制限超過時（429 TOO_MANY_ATTEMPTS）。
	"""
	return await notification_service.list_notifications(db, user, page, per_page, unread_only)


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(enforce_notification_read_rate_limit),
) -> UnreadCountResponse:
	"""GET /api/notifications/unread-count: 未読通知件数を取得する。

	認可: 認証必須（未認証は401 UNAUTHENTICATED）。参照系レート制限を課す。

	Args:
		user: 認証済みユーザー。
		db: DBセッション。

	Returns:
		200 OKで未読件数を返す。

	Raises:
		TooManyAttemptsError: レート制限超過時（429 TOO_MANY_ATTEMPTS）。
	"""
	return await notification_service.get_unread_count(db, user)


@router.patch("/{notification_id}/read", response_model=NotificationReadResponse)
async def mark_notification_read(
	notification_id: UUID,
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(verify_origin_if_session),
	__csrf: None = Depends(verify_csrf_if_session),
	___: None = Depends(enforce_notification_write_rate_limit),
) -> NotificationReadResponse:
	"""PATCH /api/notifications/{notification_id}/read: 通知を既読にする。

	認可: 認証必須。自分宛ての通知以外は404 NOT_FOUND。
	sessionモードではOrigin検証・CSRF検証も課す（不正時403 CSRF_INVALID）。更新系レート制限も課す。

	Args:
		notification_id: 既読にする通知のID。
		user: 認証済みユーザー。
		db: DBセッション。

	Returns:
		200 OKで更新後の通知を返す。

	Raises:
		NotFoundError: 通知が存在しない、または自分宛てでない場合（404 NOT_FOUND）。
		TooManyAttemptsError: レート制限超過時（429 TOO_MANY_ATTEMPTS）。
	"""
	return await notification_service.mark_notification_read(db, notification_id, user)


@router.post("/read-all", response_model=NotificationReadAllResponse)
async def mark_all_notifications_read(
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(verify_origin_if_session),
	__csrf: None = Depends(verify_csrf_if_session),
	___: None = Depends(enforce_notification_write_rate_limit),
) -> NotificationReadAllResponse:
	"""POST /api/notifications/read-all: 自分宛ての未読通知をすべて既読にする。

	認可: 認証必須。sessionモードではOrigin検証・CSRF検証も課す（不正時403 CSRF_INVALID）。更新系レート制限も課す。

	Args:
		user: 認証済みユーザー。
		db: DBセッション。

	Returns:
		200 OKで既読にした件数等を返す。

	Raises:
		TooManyAttemptsError: レート制限超過時（429 TOO_MANY_ATTEMPTS）。
	"""
	return await notification_service.mark_all_notifications_read(db, user)
