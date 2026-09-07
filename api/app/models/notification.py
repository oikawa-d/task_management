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
	# 設計書10_table_notifications.md §6ではlazy="joined"だが、本リポジトリのrepositoryは
	# select(Model).from_statement(text(...))でSP/FN結果をORM行にマッピングする方式であり、
	# from_statementは生SQLをそのまま使うためlazy="joined"のSQL結合が効かず、
	# 後から.taskへアクセスするとMissingGreenletになる。そのためnoloadとし、
	# タスク情報が必要な場面は将来のservice層がtask_repository.get_by_id()を別途呼ぶ前提とする。
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
