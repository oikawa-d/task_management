"""create tasks table

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-07

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.create_table(
		"tasks",
		sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
		sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
		sa.Column("title", sa.String(150), nullable=False),
		sa.Column("description", sa.Text(), nullable=True),
		sa.Column("status", sa.String(20), nullable=False, server_default="todo"),
		sa.Column("assignee_id", postgresql.UUID(as_uuid=True), nullable=True),
		sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
		sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
		sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
		sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
		sa.PrimaryKeyConstraint("id", name="pk_tasks"),
		sa.ForeignKeyConstraint(
			["project_id"], ["projects.id"], name="fk_tasks_project_id_projects", ondelete="SET NULL"
		),
		sa.ForeignKeyConstraint(
			["assignee_id"], ["users.id"], name="fk_tasks_assignee_id_users", ondelete="SET NULL"
		),
		sa.ForeignKeyConstraint(
			["created_by"], ["users.id"], name="fk_tasks_created_by_users", ondelete="RESTRICT"
		),
		sa.CheckConstraint("status IN ('todo', 'in_progress', 'done')", name="ck_tasks_status"),
		sa.CheckConstraint("position >= 0", name="ck_tasks_position_non_negative"),
		sa.CheckConstraint("version > 0", name="ck_tasks_version_positive"),
		sa.UniqueConstraint(
			"project_id",
			"status",
			"position",
			name="uq_tasks_project_status_position",
			deferrable=True,
			initially="DEFERRED",
		),
	)
	op.create_index("ix_tasks_assignee_id", "tasks", ["assignee_id"])


def downgrade() -> None:
	op.drop_table("tasks")
