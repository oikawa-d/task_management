"""create batch_history table

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-07

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.create_table(
		"batch_history",
		sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
		sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column("batch_name", sa.String(100), nullable=False),
		sa.Column("trigger_type", sa.String(20), nullable=False),
		sa.Column("slot", sa.String(20), nullable=True),
		sa.Column("status", sa.String(20), nullable=False, server_default="inprogress"),
		sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
		sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
		sa.Column("error_code", sa.String(80), nullable=True),
		sa.Column("error_detail", sa.Text(), nullable=True),
		sa.Column("target_count", sa.Integer(), nullable=False, server_default="0"),
		sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
		sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
		sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
		sa.PrimaryKeyConstraint("id", name="pk_batch_history"),
		sa.UniqueConstraint("run_id", name="uq_batch_history_run_id"),
		sa.CheckConstraint("trigger_type IN ('scheduled', 'manual')", name="ck_batch_history_trigger_type"),
		sa.CheckConstraint("status IN ('inprogress', 'complete', 'error')", name="ck_batch_history_status"),
		sa.CheckConstraint(
			"(status = 'inprogress' AND ended_at IS NULL AND error_code IS NULL AND error_detail IS NULL)"
			" OR (status = 'complete' AND ended_at IS NOT NULL AND error_code IS NULL AND error_detail IS NULL)"
			" OR (status = 'error' AND ended_at IS NOT NULL"
			" AND (error_code IS NOT NULL OR error_detail IS NOT NULL))",
			name="ck_batch_history_status_consistency",
		),
		sa.CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="ck_batch_history_ended_at"),
		sa.CheckConstraint(
			"target_count >= 0 AND success_count >= 0 AND skipped_count >= 0",
			name="ck_batch_history_counts",
		),
	)
	op.create_index("ix_batch_history_started", "batch_history", [sa.text("started_at DESC")])
	op.create_index("ix_batch_history_name_started", "batch_history", ["batch_name", sa.text("started_at DESC")])
	op.create_index("ix_batch_history_status_started", "batch_history", ["status", sa.text("started_at DESC")])


def downgrade() -> None:
	op.drop_index("ix_batch_history_status_started", table_name="batch_history")
	op.drop_index("ix_batch_history_name_started", table_name="batch_history")
	op.drop_index("ix_batch_history_started", table_name="batch_history")
	op.drop_table("batch_history")
