import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPkMixin


class BatchHistory(UUIDPkMixin, Base):
	"""batchジョブ1回の実行履歴。API側には同テーブルを更新できるモデルを置かない（12_table_batch_history.md §4）。

	created_at相当の役割はstarted_atが担うため、CreatedAtMixin/TimestampMixinは使わずupdated_atのみを持つ。
	"""

	__tablename__ = "batch_history"

	run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
	batch_name: Mapped[str] = mapped_column(String(100), nullable=False)
	trigger_type: Mapped[str] = mapped_column(String(20), nullable=False)
	slot: Mapped[str | None] = mapped_column(String(20), nullable=True)
	status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="inprogress")
	started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
	ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
	error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
	error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
	target_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
	success_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
	skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
	updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

	__table_args__ = (
		UniqueConstraint("run_id", name="uq_batch_history_run_id"),
		CheckConstraint("trigger_type IN ('scheduled', 'manual')", name="ck_batch_history_trigger_type"),
		CheckConstraint("status IN ('inprogress', 'complete', 'error')", name="ck_batch_history_status"),
		CheckConstraint(
			"(status = 'inprogress' AND ended_at IS NULL AND error_code IS NULL AND error_detail IS NULL)"
			" OR (status = 'complete' AND ended_at IS NOT NULL AND error_code IS NULL AND error_detail IS NULL)"
			" OR (status = 'error' AND ended_at IS NOT NULL"
			" AND (error_code IS NOT NULL OR error_detail IS NOT NULL))",
			name="ck_batch_history_status_consistency",
		),
		CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="ck_batch_history_ended_at"),
		CheckConstraint(
			"target_count >= 0 AND success_count >= 0 AND skipped_count >= 0",
			name="ck_batch_history_counts",
		),
		Index("ix_batch_history_started", text("started_at DESC")),
		Index("ix_batch_history_name_started", "batch_name", text("started_at DESC")),
		Index("ix_batch_history_status_started", "status", text("started_at DESC")),
	)
