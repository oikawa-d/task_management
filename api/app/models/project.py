import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
	from app.models.project_member import ProjectMember
	from app.models.task import Task
	from app.models.user import User


class Project(UUIDPkMixin, TimestampMixin, Base):
	__tablename__ = "projects"

	name: Mapped[str] = mapped_column(String(100), nullable=False)
	description: Mapped[str | None] = mapped_column(Text, nullable=True)
	owner_id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
	)
	is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
	start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
	end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

	owner: Mapped["User"] = relationship("User", foreign_keys=[owner_id], lazy="joined")
	members: Mapped[list["ProjectMember"]] = relationship(
		"ProjectMember", back_populates="project", cascade="all, delete-orphan", lazy="selectin"
	)
	tasks: Mapped[list["Task"]] = relationship(
		"Task", back_populates="project", cascade="all, delete-orphan", lazy="noload"
	)

	__table_args__ = (
		CheckConstraint(
			"start_at IS NULL OR end_at IS NULL OR end_at >= start_at",
			name="ck_projects_period",
		),
	)
