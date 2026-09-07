import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDPkMixin

if TYPE_CHECKING:
	from app.models.user import User


class LoginHistory(UUIDPkMixin, CreatedAtMixin, Base):
	__tablename__ = "login_history"

	user_id: Mapped[uuid.UUID | None] = mapped_column(
		UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
	)
	login_identifier: Mapped[str] = mapped_column(String(50), nullable=False)
	login_method: Mapped[str] = mapped_column(String(20), nullable=False)
	ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
	user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
	success: Mapped[bool] = mapped_column(Boolean, nullable=False)
	failure_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)

	user: Mapped["User | None"] = relationship(back_populates="login_histories", lazy="noload")

	__table_args__ = (
		CheckConstraint(
			"login_method IN ('session', 'jwt', 'oauth_google')",
			name="ck_login_history_login_method",
		),
		CheckConstraint(
			"(success = true AND failure_reason IS NULL) OR (success = false)",
			name="ck_login_history_failure_reason_consistency",
		),
		Index("ix_login_history_user_created", "user_id", "created_at"),
		Index("ix_login_history_created", "created_at"),
	)
