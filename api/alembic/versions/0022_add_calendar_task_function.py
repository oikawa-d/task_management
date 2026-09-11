"""add the dashboard calendar task function

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-11

"""
from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FUNCTION_PATH = Path(__file__).resolve().parents[3] / "db/functions/fn_list_calendar_tasks.sql"


def upgrade() -> None:
	op.execute(FUNCTION_PATH.read_text())


def downgrade() -> None:
	op.execute("DROP FUNCTION IF EXISTS fn_list_calendar_tasks(UUID, TIMESTAMPTZ, TIMESTAMPTZ, VARCHAR, UUID)")
