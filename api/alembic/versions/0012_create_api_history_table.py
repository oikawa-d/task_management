"""create api_history table

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-07

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.create_table(
		"api_history",
		sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
		sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column("method", sa.String(10), nullable=False),
		sa.Column("path", sa.String(255), nullable=False),
		sa.Column("status", sa.String(20), nullable=False),
		sa.Column("status_code", sa.SmallInteger(), nullable=False),
		sa.Column("error_code", sa.String(80), nullable=True),
		sa.Column("error_detail", sa.Text(), nullable=True),
		sa.Column("body", postgresql.JSONB(), nullable=True),
		sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
		sa.Column("ip_address", postgresql.INET(), nullable=True),
		sa.Column("user_agent", sa.Text(), nullable=True),
		sa.Column("duration_ms", sa.Integer(), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
		sa.PrimaryKeyConstraint("id", name="pk_api_history"),
		sa.UniqueConstraint("request_id", name="uq_api_history_request_id"),
		sa.ForeignKeyConstraint(
			["user_id"], ["users.id"], name="fk_api_history_user_id_users", ondelete="SET NULL"
		),
		sa.CheckConstraint("status IN ('success', 'error')", name="ck_api_history_status"),
		sa.CheckConstraint("status_code BETWEEN 100 AND 599", name="ck_api_history_status_code"),
		sa.CheckConstraint(
			"(status = 'success' AND status_code BETWEEN 200 AND 399"
			" AND error_code IS NULL AND error_detail IS NULL)"
			" OR (status = 'error' AND status_code BETWEEN 400 AND 599"
			" AND (error_code IS NOT NULL OR error_detail IS NOT NULL))",
			name="ck_api_history_status_consistency",
		),
		sa.CheckConstraint("duration_ms >= 0", name="ck_api_history_duration_ms"),
	)
	op.create_index("ix_api_history_created", "api_history", [sa.text("created_at DESC")])
	op.create_index("ix_api_history_path_created", "api_history", ["path", sa.text("created_at DESC")])
	op.create_index("ix_api_history_status_created", "api_history", ["status", sa.text("created_at DESC")])


def downgrade() -> None:
	op.drop_index("ix_api_history_status_created", table_name="api_history")
	op.drop_index("ix_api_history_path_created", table_name="api_history")
	op.drop_index("ix_api_history_created", table_name="api_history")
	op.drop_table("api_history")
