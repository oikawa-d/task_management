"""return the persisted read_at from sp_mark_notification_read

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-11

"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DB_DIR = Path(__file__).resolve().parents[3] / "db"
PROCEDURES_DIR = DB_DIR / "procedures"
LEGACY_PROCEDURES_DIR = PROCEDURES_DIR / "legacy"
CURRENT_PROCEDURE_SIGNATURE = "sp_mark_notification_read(UUID, UUID)"


def upgrade() -> None:
	# PostgreSQLはCREATE OR REPLACE PROCEDUREで引数数を変更できないため、旧定義を削除して作り直す。
	op.execute(f"DROP PROCEDURE IF EXISTS {CURRENT_PROCEDURE_SIGNATURE}")
	op.execute((PROCEDURES_DIR / "sp_mark_notification_read.sql").read_text())


def downgrade() -> None:
	op.execute(f"DROP PROCEDURE IF EXISTS {CURRENT_PROCEDURE_SIGNATURE}")
	op.execute((LEGACY_PROCEDURES_DIR / "0014_sp_mark_notification_read.sql").read_text())
