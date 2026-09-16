"""create notification/api_history/batch_history functions, procedures and trigger

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-07

"""
from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DB_DIR = Path(__file__).resolve().parents[3] / "db"
FUNCTIONS_DIR = DB_DIR / "functions"
PROCEDURES_DIR = DB_DIR / "procedures"

_FUNCTION_FILES = (
	"fn_list_notifications.sql",
	"fn_count_unread_notifications.sql",
	"fn_list_due_notification_tasks.sql",
)
_PROCEDURE_FILES = (
	"sp_mark_notification_read.sql",
	"sp_mark_all_notifications_read.sql",
	"sp_purge_notifications.sql",
	"sp_purge_api_history.sql",
	"sp_purge_batch_history.sql",
)


def upgrade() -> None:
	# notificationsはupdated_atを持たないためtrg_set_updated_atは不要。batch_historyのみ対象。
	op.execute(
		"CREATE TRIGGER trg_batch_history_set_updated_at "
		"BEFORE UPDATE ON batch_history FOR EACH ROW "
		"EXECUTE FUNCTION trg_set_updated_at();"
	)
	for filename in _FUNCTION_FILES:
		op.execute((FUNCTIONS_DIR / filename).read_text())
	for filename in _PROCEDURE_FILES:
		op.execute((PROCEDURES_DIR / filename).read_text())


def downgrade() -> None:
	op.execute("DROP PROCEDURE IF EXISTS sp_purge_batch_history(INTEGER)")
	op.execute("DROP PROCEDURE IF EXISTS sp_purge_api_history(INTEGER)")
	op.execute("DROP PROCEDURE IF EXISTS sp_purge_notifications(INTEGER)")
	op.execute("DROP PROCEDURE IF EXISTS sp_mark_all_notifications_read(UUID)")
	op.execute("DROP PROCEDURE IF EXISTS sp_mark_notification_read(UUID, UUID)")

	op.execute("DROP FUNCTION IF EXISTS fn_list_due_notification_tasks(TIMESTAMPTZ)")
	op.execute("DROP FUNCTION IF EXISTS fn_count_unread_notifications(UUID)")
	op.execute("DROP FUNCTION IF EXISTS fn_list_notifications(UUID, BOOLEAN, INTEGER, INTEGER)")

	op.execute("DROP TRIGGER IF EXISTS trg_batch_history_set_updated_at ON batch_history")
