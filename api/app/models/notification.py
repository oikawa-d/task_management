"""タスク期限通知を表す `Notification` モデルを定義するモジュール。"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDPkMixin

if TYPE_CHECKING:
	from app.models.task import Task
	from app.models.user import User


class Notification(UUIDPkMixin, CreatedAtMixin, Base):
	"""`notifications` テーブルに対応するモデル。

	バッチ処理が生成する期限接近・当日作成/更新タスクの通知を1件ずつ保持する。
	`dedupe_key` によりユーザー単位での重複通知を防ぎ（`uq_notifications_user_dedupe`）、
	`read_at` の有無で既読/未読を判定する。`task` は通知の一覧表示・検索は
	`fn_list_notifications` のLEFT JOIN結果をrepositoryが直接マッピングするため、
	ORM側の遅延/eagerロードは使わない（`lazy="noload"`）。
	"""

	__tablename__ = "notifications"

	user_id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
	)
	task_id: Mapped[uuid.UUID | None] = mapped_column(
		UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
	)
	type: Mapped[str] = mapped_column(String(30), nullable=False)
	title: Mapped[str] = mapped_column(String(200), nullable=False)
	body: Mapped[str | None] = mapped_column(Text, nullable=True)
	due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
	dedupe_key: Mapped[str] = mapped_column(String(120), nullable=False)
	read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

	user: Mapped["User"] = relationship("User", lazy="noload")
	# task情報はfn_list_notifications内のLEFT JOINで取得しrepositoryが直接マッピングするため、
	# ORMのrelationshipによる遅延/eagerロードは使用しない。
	task: Mapped["Task | None"] = relationship("Task", lazy="noload")

	__table_args__ = (
		CheckConstraint(
			"type IN ('due_soon_batch','due_today_created','due_today_updated')",
			name="ck_notifications_type",
		),
		UniqueConstraint("user_id", "dedupe_key", name="uq_notifications_user_dedupe"),
		Index(
			"ix_notifications_user_created",
			"user_id",
			text("created_at DESC"),
		),
		Index(
			"ix_notifications_user_unread",
			"user_id",
			postgresql_where=text("read_at IS NULL"),
		),
	)
