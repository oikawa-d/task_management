import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
	from app.models.project import Project
	from app.models.user import User


class ProjectMember(Base):
	__tablename__ = "project_members"

	project_id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
	)
	user_id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
	)
	invited_by: Mapped[uuid.UUID | None] = mapped_column(
		UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
	)
	joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

	project: Mapped["Project"] = relationship("Project", back_populates="members", lazy="joined")
	user: Mapped["User"] = relationship("User", foreign_keys=[user_id], lazy="joined")
	inviter: Mapped["User | None"] = relationship("User", foreign_keys=[invited_by], lazy="joined")
