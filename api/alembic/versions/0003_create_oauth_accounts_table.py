"""create oauth_accounts table

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-07

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.create_table(
		"oauth_accounts",
		sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
		sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column("provider", sa.String(20), nullable=False),
		sa.Column("provider_user_id", sa.Text(), nullable=False),
		sa.Column("provider_email", sa.Text(), nullable=True),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
		sa.PrimaryKeyConstraint("id", name="pk_oauth_accounts"),
		sa.ForeignKeyConstraint(
			["user_id"], ["users.id"], name="fk_oauth_accounts_user_id_users", ondelete="CASCADE"
		),
		sa.CheckConstraint("provider IN ('google')", name="ck_oauth_accounts_provider"),
	)
	op.create_index(
		"uq_oauth_accounts_provider_provider_user_id",
		"oauth_accounts",
		["provider", "provider_user_id"],
		unique=True,
	)
	op.create_index("ix_oauth_accounts_user_id", "oauth_accounts", ["user_id"])


def downgrade() -> None:
	op.drop_table("oauth_accounts")
