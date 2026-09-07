"""create task_comments table

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-07

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.create_table(
		"task_comments",
		sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
		sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column("body", sa.Text(), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
		sa.PrimaryKeyConstraint("id", name="pk_task_comments"),
		sa.ForeignKeyConstraint(
			["task_id"], ["tasks.id"], name="fk_task_comments_task_id_tasks", ondelete="CASCADE"
		),
		sa.ForeignKeyConstraint(
			["user_id"], ["users.id"], name="fk_task_comments_user_id_users", ondelete="RESTRICT"
		),
	)
	op.create_index("ix_task_comments_task_created", "task_comments", ["task_id", "created_at"])


def downgrade() -> None:
	op.drop_table("task_comments")
