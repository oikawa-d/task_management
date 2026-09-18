"""通知関連エンドポイント（`notifications_router`）の入出力DTOを定義するモジュール。"""

from datetime import datetime
from typing import Literal, cast
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.config import BackendSettings

NotificationType = Literal["due_soon_batch", "due_today_created", "due_today_updated"]

_DEFAULT_PER_PAGE = cast(int, BackendSettings.model_fields["pagination_default_per_page"].default)
_MAX_PER_PAGE = cast(int, BackendSettings.model_fields["pagination_max_per_page"].default)


class NotificationListQuery(BaseModel):
	"""`GET /api/notifications` が受け取るクエリパラメータの形状を検証するDTO。

	ルーター側では個々のクエリパラメータを`Query(...)`で直接受け取るため、
	このクラス自体はルーターへ直接バインドされておらず、ページネーションと
	未読限定表示の指定に関するバリデーション仕様を表す。
	"""

	page: int = Field(default=1, ge=1)
	per_page: int = Field(default=_DEFAULT_PER_PAGE, ge=1, le=_MAX_PER_PAGE)
	unread_only: bool = False


class NotificationTask(BaseModel):
	"""通知が紐づくタスクの表示用サマリDTO。`NotificationItem.task` として埋め込まれる。"""

	id: UUID
	project_id: UUID | None
	title: str


class NotificationItem(BaseModel):
	"""通知一覧の1件分を表すレスポンスDTO。"""

	id: UUID
	type: NotificationType
	title: str
	body: str | None = None
	task: NotificationTask | None = None
	due_at: datetime | None = None
	read_at: datetime | None = None
	created_at: datetime


class NotificationMeta(BaseModel):
	"""通知一覧のページネーション情報を表すDTO。"""

	page: int = Field(ge=1)
	per_page: int = Field(ge=1, le=_MAX_PER_PAGE)
	total: int = Field(ge=0)
	total_pages: int = Field(ge=0)


class NotificationListResponse(BaseModel):
	"""`GET /api/notifications` のレスポンスDTO。通知一覧・ページ情報・未読件数を返す。"""

	items: list[NotificationItem]
	meta: NotificationMeta
	unread_count: int = Field(ge=0)


class UnreadCountResponse(BaseModel):
	"""`GET /api/notifications/unread-count` のレスポンスDTO。未読通知件数のみを返す。"""

	unread_count: int = Field(ge=0)


class NotificationReadResponse(BaseModel):
	"""`PATCH /api/notifications/{notification_id}/read` のレスポンスDTO。既読化した通知IDと更新後の未読件数を返す。"""

	id: UUID
	read_at: datetime
	unread_count: int = Field(ge=0)


class NotificationReadAllResponse(BaseModel):
	"""`POST /api/notifications/read-all` のレスポンスDTO。一括既読化した件数と更新後の未読件数を返す。"""

	updated_count: int = Field(ge=0)
	unread_count: int = Field(ge=0)
