"""create projects table

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-07

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.create_table(
		"projects",
		sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
		sa.Column("name", sa.String(100), nullable=False),
		sa.Column("description", sa.Text(), nullable=True),
		sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
		sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
		sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
		sa.PrimaryKeyConstraint("id", name="pk_projects"),
		sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_projects_owner_id_users", ondelete="RESTRICT"),
		sa.CheckConstraint(
			"start_at IS NULL OR end_at IS NULL OR end_at >= start_at",
			name="ck_projects_period",
		),
	)
	op.create_index("ix_projects_owner_id", "projects", ["owner_id"])


def downgrade() -> None:
	op.drop_table("projects")
