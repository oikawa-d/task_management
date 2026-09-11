"""return notification read timestamps and update counts from procedures

Revision ID: 0023
Revises: 0022
Create Date: 2026-09-11

"""
from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DB_DIR = Path(__file__).resolve().parents[3] / "db"
PROCEDURES_DIR = DB_DIR / "procedures"
LEGACY_PROCEDURES_DIR = PROCEDURES_DIR / "legacy"


def upgrade() -> None:
	op.execute("DROP PROCEDURE IF EXISTS sp_mark_all_notifications_read(UUID)")
	op.execute("DROP PROCEDURE IF EXISTS sp_mark_notification_read(UUID, UUID)")
	op.execute((PROCEDURES_DIR / "sp_mark_notification_read.sql").read_text())
	op.execute((PROCEDURES_DIR / "sp_mark_all_notifications_read.sql").read_text())


def downgrade() -> None:
	op.execute("DROP PROCEDURE IF EXISTS sp_mark_all_notifications_read(UUID)")
	op.execute("DROP PROCEDURE IF EXISTS sp_mark_notification_read(UUID, UUID)")
	op.execute((LEGACY_PROCEDURES_DIR / "0022_sp_mark_notification_read.sql").read_text())
	op.execute((LEGACY_PROCEDURES_DIR / "0022_sp_mark_all_notifications_read.sql").read_text())
