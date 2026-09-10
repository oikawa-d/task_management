"""change fn_list_notifications return type to include task info/total_count, add fn_count_notifications

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-10

"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DB_DIR = Path(__file__).resolve().parents[3] / "db"
FUNCTIONS_DIR = DB_DIR / "functions"
LEGACY_FUNCTIONS_DIR = FUNCTIONS_DIR / "legacy"

_FN_LIST_NOTIFICATIONS_SIGNATURE = "fn_list_notifications(UUID, BOOLEAN, INTEGER, INTEGER)"
_FN_COUNT_NOTIFICATIONS_SIGNATURE = "fn_count_notifications(UUID, BOOLEAN)"


def upgrade() -> None:
	# PostgreSQLはCREATE OR REPLACE FUNCTIONで戻り値型を変更できないため、
	# 一度DROPしてから新しい戻り値型（task情報・total_countを含むTABLE）で作り直す。
	op.execute(f"DROP FUNCTION IF EXISTS {_FN_LIST_NOTIFICATIONS_SIGNATURE}")
	op.execute((FUNCTIONS_DIR / "fn_list_notifications.sql").read_text())
	op.execute((FUNCTIONS_DIR / "fn_count_notifications.sql").read_text())


def downgrade() -> None:
	op.execute(f"DROP FUNCTION IF EXISTS {_FN_COUNT_NOTIFICATIONS_SIGNATURE}")
	op.execute(f"DROP FUNCTION IF EXISTS {_FN_LIST_NOTIFICATIONS_SIGNATURE}")
	op.execute((LEGACY_FUNCTIONS_DIR / "0014_fn_list_notifications.sql").read_text())
