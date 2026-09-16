"""align task update, comment count, and paging database contracts

Revision ID: 0028
Revises: 0027
Create Date: 2026-09-16
"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op

DB_DIR = Path(__file__).resolve().parents[3] / "db"

revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.execute(
		"DROP PROCEDURE IF EXISTS sp_update_task(UUID, UUID, INTEGER, VARCHAR, TEXT, VARCHAR, UUID, "
		"TIMESTAMPTZ, INTEGER, TIMESTAMPTZ, TIMESTAMPTZ)"
	)
	for signature in (
		"fn_get_task(UUID)",
		"fn_get_project_board(UUID, BOOLEAN)",
		"fn_list_tasks(UUID, UUID, VARCHAR, BOOLEAN, INTEGER, INTEGER, BOOLEAN)",
		"fn_count_tasks(UUID, UUID, VARCHAR, BOOLEAN, BOOLEAN)",
		"fn_list_calendar_tasks(UUID, TIMESTAMPTZ, TIMESTAMPTZ, VARCHAR, UUID)",
	):
		op.execute(f"DROP FUNCTION IF EXISTS {signature}")
	op.execute((DB_DIR / "procedures/sp_update_task.sql").read_text())
	for filename in (
		"fn_get_task.sql",
		"fn_get_project_board.sql",
		"fn_list_tasks.sql",
		"fn_count_tasks.sql",
		"fn_list_calendar_tasks.sql",
	):
		op.execute((DB_DIR / "functions" / filename).read_text())


def downgrade() -> None:
	op.execute(
		"DROP PROCEDURE IF EXISTS sp_update_task(UUID, UUID, INTEGER, VARCHAR, TEXT, VARCHAR, UUID, "
		"TIMESTAMPTZ, INTEGER, BOOLEAN, TIMESTAMPTZ, TIMESTAMPTZ)"
	)
	op.execute((DB_DIR / "procedures/legacy/0027_sp_update_task.sql").read_text())
	for signature in (
		"fn_get_task(UUID)",
		"fn_get_project_board(UUID, BOOLEAN)",
		"fn_list_tasks(UUID, UUID, VARCHAR, BOOLEAN, INTEGER, INTEGER, BOOLEAN)",
		"fn_count_tasks(UUID, UUID, VARCHAR, BOOLEAN, BOOLEAN)",
		"fn_list_calendar_tasks(UUID, TIMESTAMPTZ, TIMESTAMPTZ, VARCHAR, UUID)",
	):
		op.execute(f"DROP FUNCTION IF EXISTS {signature}")
	for filename in (
		"fn_get_task.sql",
		"fn_get_project_board.sql",
		"fn_list_tasks.sql",
		"fn_list_calendar_tasks.sql",
	):
		op.execute((DB_DIR / "functions/legacy" / f"0027_{filename}").read_text())
