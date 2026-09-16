"""create users table

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-07

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.create_table(
		"users",
		sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
		sa.Column("username", sa.String(50), nullable=False),
		sa.Column("email", sa.String(50), nullable=False),
		sa.Column("password_hash", sa.Text(), nullable=True),
		sa.Column("last_name", sa.String(30), nullable=True),
		sa.Column("first_name", sa.String(30), nullable=True),
		sa.Column("last_name_kana", sa.String(30), nullable=True),
		sa.Column("first_name_kana", sa.String(30), nullable=True),
		sa.Column("birth_date", sa.Date(), nullable=True),
		sa.Column("role", sa.String(10), nullable=False, server_default="member"),
		sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
		sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
		sa.PrimaryKeyConstraint("id", name="pk_users"),
		sa.CheckConstraint("role IN ('member', 'admin')", name="ck_users_role"),
		sa.CheckConstraint(r"username ~ '^[A-Za-z0-9_-]+$'", name="ck_users_username_format"),
		sa.CheckConstraint(
			r"email ~ '^[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'",
			name="ck_users_email_format",
		),
		sa.CheckConstraint(
			r"(last_name_kana IS NULL OR last_name_kana ~ '^[ぁ-んァ-ヶー0-9]+$')"
			r" AND (first_name_kana IS NULL OR first_name_kana ~ '^[ぁ-んァ-ヶー0-9]+$')",
			name="ck_users_kana_format",
		),
	)
	op.create_index("uq_users_username", "users", [sa.text("lower(username)")], unique=True)
	op.create_index("uq_users_email", "users", [sa.text("lower(email)")], unique=True)
	op.create_index("ix_users_role", "users", ["role"])
	op.create_index(
		"ix_users_email_verified_at",
		"users",
		["email_verified_at"],
		postgresql_where=sa.text("email_verified_at IS NULL"),
	)
	op.create_index("ix_users_created_at", "users", [sa.text("created_at DESC")])


def downgrade() -> None:
	op.drop_table("users")
