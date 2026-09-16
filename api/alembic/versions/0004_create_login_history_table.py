"""create login_history table

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-07

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.create_table(
		"login_history",
		sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
		sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
		sa.Column("login_identifier", sa.String(50), nullable=False),
		sa.Column("login_method", sa.String(20), nullable=False),
		sa.Column("ip_address", postgresql.INET(), nullable=True),
		sa.Column("user_agent", sa.Text(), nullable=True),
		sa.Column("success", sa.Boolean(), nullable=False),
		sa.Column("failure_reason", sa.String(50), nullable=True),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
		sa.PrimaryKeyConstraint("id", name="pk_login_history"),
		sa.ForeignKeyConstraint(
			["user_id"], ["users.id"], name="fk_login_history_user_id_users", ondelete="SET NULL"
		),
		sa.CheckConstraint(
			"login_method IN ('session', 'jwt', 'oauth_google')",
			name="ck_login_history_login_method",
		),
		sa.CheckConstraint(
			"(success = true AND failure_reason IS NULL) OR (success = false)",
			name="ck_login_history_failure_reason_consistency",
		),
	)
	op.create_index("ix_login_history_user_created", "login_history", ["user_id", sa.text("created_at DESC")])
	op.create_index("ix_login_history_created", "login_history", [sa.text("created_at DESC")])


def downgrade() -> None:
	op.drop_table("login_history")
