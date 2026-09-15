"""extend users email and login identifier length

Revision ID: 0025
Revises: 0024
Create Date: 2026-09-15

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.alter_column("users", "email", existing_type=sa.String(50), type_=sa.String(254), existing_nullable=False)
	op.alter_column(
		"login_history",
		"login_identifier",
		existing_type=sa.String(50),
		type_=sa.String(254),
		existing_nullable=False,
	)


def downgrade() -> None:
	op.alter_column(
		"login_history",
		"login_identifier",
		existing_type=sa.String(254),
		type_=sa.String(50),
		existing_nullable=False,
	)
	op.alter_column("users", "email", existing_type=sa.String(254), type_=sa.String(50), existing_nullable=False)
