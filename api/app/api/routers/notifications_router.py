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
	return await notification_service.list_notifications(db, user, page, per_page, unread_only)


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(enforce_notification_read_rate_limit),
) -> UnreadCountResponse:
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
	return await notification_service.mark_notification_read(db, notification_id, user)


@router.post("/read-all", response_model=NotificationReadAllResponse)
async def mark_all_notifications_read(
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(verify_origin_if_session),
	__csrf: None = Depends(verify_csrf_if_session),
	___: None = Depends(enforce_notification_write_rate_limit),
) -> NotificationReadAllResponse:
	return await notification_service.mark_all_notifications_read(db, user)
