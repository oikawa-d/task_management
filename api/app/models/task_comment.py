import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
	from app.models.task import Task
	from app.models.user import User


class TaskComment(UUIDPkMixin, TimestampMixin, Base):
	__tablename__ = "task_comments"

	task_id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
	)
	user_id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
	)
	body: Mapped[str] = mapped_column(Text, nullable=False)

	task: Mapped["Task"] = relationship("Task", back_populates="comments", lazy="noload")
	author: Mapped["User"] = relationship("User", foreign_keys=[user_id], lazy="joined")

	__table_args__ = (Index("ix_task_comments_task_created", "task_id", "created_at"),)
