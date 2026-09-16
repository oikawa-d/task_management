"""create notifications table

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-07

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.create_table(
		"notifications",
		sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
		sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
		sa.Column("type", sa.String(30), nullable=False),
		sa.Column("title", sa.String(200), nullable=False),
		sa.Column("body", sa.Text(), nullable=True),
		sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
		sa.Column("dedupe_key", sa.String(120), nullable=False),
		sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
		sa.PrimaryKeyConstraint("id", name="pk_notifications"),
		sa.ForeignKeyConstraint(
			["user_id"], ["users.id"], name="fk_notifications_user_id_users", ondelete="CASCADE"
		),
		sa.ForeignKeyConstraint(
			["task_id"], ["tasks.id"], name="fk_notifications_task_id_tasks", ondelete="SET NULL"
		),
		sa.CheckConstraint(
			"type IN ('due_soon_batch', 'due_today_created', 'due_today_updated')",
			name="ck_notifications_type",
		),
		sa.UniqueConstraint("user_id", "dedupe_key", name="uq_notifications_user_dedupe"),
	)
	op.create_index("ix_notifications_user_created", "notifications", ["user_id", sa.text("created_at DESC")])
	op.create_index(
		"ix_notifications_user_unread",
		"notifications",
		["user_id"],
		postgresql_where=sa.text("read_at IS NULL"),
	)


def downgrade() -> None:
	op.drop_index("ix_notifications_user_unread", table_name="notifications")
	op.drop_index("ix_notifications_user_created", table_name="notifications")
	op.drop_table("notifications")
