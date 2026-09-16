"""create project_members table

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-07

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.create_table(
		"project_members",
		sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column("invited_by", postgresql.UUID(as_uuid=True), nullable=True),
		sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
		sa.PrimaryKeyConstraint("project_id", "user_id", name="pk_project_members"),
		sa.ForeignKeyConstraint(
			["project_id"], ["projects.id"], name="fk_project_members_project_id_projects", ondelete="CASCADE"
		),
		sa.ForeignKeyConstraint(
			["user_id"], ["users.id"], name="fk_project_members_user_id_users", ondelete="CASCADE"
		),
		sa.ForeignKeyConstraint(
			["invited_by"], ["users.id"], name="fk_project_members_invited_by_users", ondelete="SET NULL"
		),
	)
	op.create_index("ix_project_members_user_id", "project_members", ["user_id"])


def downgrade() -> None:
	op.drop_table("project_members")
