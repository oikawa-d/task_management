"""pass application day bounds to task notification procedures

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-08

"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DB_DIR = Path(__file__).resolve().parents[3] / "db"
PROCEDURES_DIR = DB_DIR / "procedures"
LEGACY_PROCEDURES_DIR = PROCEDURES_DIR / "legacy"


def _drop_current_procedures() -> None:
	op.execute(
		"DROP PROCEDURE IF EXISTS sp_update_task("
		"UUID, UUID, INTEGER, VARCHAR, TEXT, VARCHAR, UUID, TIMESTAMPTZ, INTEGER, "
		"TIMESTAMPTZ, TIMESTAMPTZ)"
	)
	op.execute(
		"DROP PROCEDURE IF EXISTS sp_create_task("
		"UUID, UUID, UUID, VARCHAR, TEXT, VARCHAR, TIMESTAMPTZ, INTEGER, "
		"TIMESTAMPTZ, TIMESTAMPTZ)"
	)


def _drop_legacy_procedures() -> None:
	op.execute(
		"DROP PROCEDURE IF EXISTS sp_update_task("
		"UUID, UUID, INTEGER, VARCHAR, TEXT, VARCHAR, UUID, TIMESTAMPTZ, INTEGER)"
	)
	op.execute(
		"DROP PROCEDURE IF EXISTS sp_create_task(UUID, UUID, UUID, VARCHAR, TEXT, VARCHAR, TIMESTAMPTZ, INTEGER)"
	)


def upgrade() -> None:
	_drop_legacy_procedures()
	op.execute((PROCEDURES_DIR / "sp_create_task.sql").read_text())
	op.execute((PROCEDURES_DIR / "sp_update_task.sql").read_text())


def downgrade() -> None:
	_drop_current_procedures()
	op.execute((LEGACY_PROCEDURES_DIR / "0010_sp_create_task.sql").read_text())
	op.execute((LEGACY_PROCEDURES_DIR / "0010_sp_update_task.sql").read_text())
