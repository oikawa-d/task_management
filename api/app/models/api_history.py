import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
	CheckConstraint,
	ForeignKey,
	Index,
	Integer,
	SmallInteger,
	String,
	Text,
	UniqueConstraint,
	text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDPkMixin

if TYPE_CHECKING:
	from app.models.user import User


class ApiHistory(UUIDPkMixin, CreatedAtMixin, Base):
	__tablename__ = "api_history"

	request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
	method: Mapped[str] = mapped_column(String(10), nullable=False)
	path: Mapped[str] = mapped_column(String(255), nullable=False)
	status: Mapped[str] = mapped_column(String(20), nullable=False)
	status_code: Mapped[int] = mapped_column(SmallInteger, nullable=False)
	error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
	error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
	body: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
	user_id: Mapped[uuid.UUID | None] = mapped_column(
		UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
	)
	ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
	user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
	duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)

	user: Mapped["User | None"] = relationship("User", lazy="noload")

	__table_args__ = (
		UniqueConstraint("request_id", name="uq_api_history_request_id"),
		CheckConstraint("status IN ('success', 'error')", name="ck_api_history_status"),
		CheckConstraint("status_code BETWEEN 100 AND 599", name="ck_api_history_status_code"),
		CheckConstraint(
			"(status = 'success' AND status_code BETWEEN 200 AND 399"
			" AND error_code IS NULL AND error_detail IS NULL)"
			" OR (status = 'error' AND status_code BETWEEN 400 AND 599"
			" AND (error_code IS NOT NULL OR error_detail IS NOT NULL))",
			name="ck_api_history_status_consistency",
		),
		CheckConstraint("duration_ms >= 0", name="ck_api_history_duration_ms"),
		Index("ix_api_history_created", text("created_at DESC")),
		Index("ix_api_history_path_created", "path", text("created_at DESC")),
		Index("ix_api_history_status_created", "status", text("created_at DESC")),
	)
