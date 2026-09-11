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


def upgrade() -> None:
	op.execute("DROP PROCEDURE IF EXISTS sp_mark_all_notifications_read(UUID)")
	op.execute("DROP PROCEDURE IF EXISTS sp_mark_notification_read(UUID, UUID)")
	op.execute((PROCEDURES_DIR / "sp_mark_notification_read.sql").read_text())
	op.execute((PROCEDURES_DIR / "sp_mark_all_notifications_read.sql").read_text())


def downgrade() -> None:
	op.execute("DROP PROCEDURE IF EXISTS sp_mark_all_notifications_read(UUID)")
	op.execute("DROP PROCEDURE IF EXISTS sp_mark_notification_read(UUID, UUID)")
	op.execute(
		"""
		CREATE PROCEDURE sp_mark_notification_read(p_notification_id UUID, p_user_id UUID)
		LANGUAGE plpgsql AS $$
		BEGIN
			UPDATE notifications SET read_at = COALESCE(read_at, now())
			 WHERE id = p_notification_id AND user_id = p_user_id;
		END;
		$$;
		"""
	)
	op.execute(
		"""
		CREATE PROCEDURE sp_mark_all_notifications_read(p_user_id UUID)
		LANGUAGE plpgsql AS $$
		BEGIN
			UPDATE notifications SET read_at = now()
			 WHERE user_id = p_user_id AND read_at IS NULL;
		END;
		$$;
		"""
	)
