from datetime import datetime
from typing import Literal, cast
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.config import BackendSettings

NotificationType = Literal["due_soon_batch", "due_today_created", "due_today_updated"]

_DEFAULT_PER_PAGE = cast(int, BackendSettings.model_fields["pagination_default_per_page"].default)
_MAX_PER_PAGE = cast(int, BackendSettings.model_fields["pagination_max_per_page"].default)


class NotificationListQuery(BaseModel):
	page: int = Field(default=1, ge=1)
	per_page: int = Field(default=_DEFAULT_PER_PAGE, ge=1, le=_MAX_PER_PAGE)
	unread_only: bool = False


class NotificationTask(BaseModel):
	id: UUID
	project_id: UUID | None
	title: str


class NotificationItem(BaseModel):
	id: UUID
	type: NotificationType
	title: str
	body: str | None = None
	task: NotificationTask | None = None
	due_at: datetime | None = None
	read_at: datetime | None = None
	created_at: datetime


class NotificationMeta(BaseModel):
	page: int = Field(ge=1)
	per_page: int = Field(ge=1, le=_MAX_PER_PAGE)
	total: int = Field(ge=0)
	total_pages: int = Field(ge=0)


class NotificationListResponse(BaseModel):
	items: list[NotificationItem]
	meta: NotificationMeta
	unread_count: int = Field(ge=0)


class UnreadCountResponse(BaseModel):
	unread_count: int = Field(ge=0)


class NotificationReadResponse(BaseModel):
	id: UUID
	read_at: datetime
	unread_count: int = Field(ge=0)


class NotificationReadAllResponse(BaseModel):
	updated_count: int = Field(ge=0)
	unread_count: int = Field(ge=0)
