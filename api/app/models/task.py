import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
	from app.models.project import Project
	from app.models.task_comment import TaskComment
	from app.models.user import User


class Task(UUIDPkMixin, TimestampMixin, Base):
	__tablename__ = "tasks"

	project_id: Mapped[uuid.UUID | None] = mapped_column(
		UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
	)
	title: Mapped[str] = mapped_column(String(150), nullable=False)
	description: Mapped[str | None] = mapped_column(Text, nullable=True)
	status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="todo")
	assignee_id: Mapped[uuid.UUID | None] = mapped_column(
		UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
	)
	created_by: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
	)
	position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
	version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
	due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
	is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

	project: Mapped["Project | None"] = relationship("Project", back_populates="tasks", lazy="joined")
	assignee: Mapped["User | None"] = relationship("User", foreign_keys=[assignee_id], lazy="joined")
	creator: Mapped["User"] = relationship("User", foreign_keys=[created_by], lazy="noload")
	comments: Mapped[list["TaskComment"]] = relationship(
		"TaskComment", back_populates="task", cascade="all, delete-orphan", lazy="noload"
	)

	__table_args__ = (
		CheckConstraint("status IN ('todo', 'in_progress', 'done')", name="ck_tasks_status"),
		CheckConstraint("position >= 0", name="ck_tasks_position_non_negative"),
		CheckConstraint("version > 0", name="ck_tasks_version_positive"),
		UniqueConstraint(
			"project_id",
			"status",
			"position",
			name="uq_tasks_project_status_position",
			deferrable=True,
			initially="DEFERRED",
		),
	)
