"""add an explicit unassigned filter to the task list function

Revision ID: 0025
Revises: 0024
Create Date: 2026-09-15

"""
from pathlib import Path
from typing import Sequence, Union

from alembic import op

DB_DIR = Path(__file__).resolve().parents[3] / "db"
FUNCTION_PATH = DB_DIR / "functions/fn_list_tasks.sql"
LEGACY_FUNCTION_PATH = DB_DIR / "functions/legacy/0010_fn_list_tasks.sql"

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.execute("DROP FUNCTION IF EXISTS fn_list_tasks(UUID, UUID, VARCHAR, BOOLEAN, INTEGER, INTEGER)")
	op.execute(FUNCTION_PATH.read_text())


def downgrade() -> None:
	op.execute("DROP FUNCTION IF EXISTS fn_list_tasks(UUID, UUID, VARCHAR, BOOLEAN, INTEGER, INTEGER, BOOLEAN)")
	op.execute(LEGACY_FUNCTION_PATH.read_text())
