"""admin一覧関数の集計・ユーザー情報を一括返却

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

DB_DIR = Path(__file__).resolve().parents[3] / "db"
FUNCTIONS_DIR = DB_DIR / "functions"
LEGACY_FUNCTIONS_DIR = FUNCTIONS_DIR / "legacy"

_FN_LIST_PROJECTS_SIGNATURE = "fn_admin_list_projects(VARCHAR, BOOLEAN, INTEGER, INTEGER)"
_FN_LIST_LOGIN_HISTORY_SIGNATURE = (
	"fn_admin_list_login_history(UUID, VARCHAR, VARCHAR, BOOLEAN, TIMESTAMPTZ, TIMESTAMPTZ, INTEGER, INTEGER)"
)


def upgrade() -> None:
	# PostgreSQLはCREATE OR REPLACEで戻り値型を変更できないため、DROP後に再作成する。
	op.execute(f"DROP FUNCTION IF EXISTS {_FN_LIST_PROJECTS_SIGNATURE}")
	op.execute(f"DROP FUNCTION IF EXISTS {_FN_LIST_LOGIN_HISTORY_SIGNATURE}")
	op.execute((FUNCTIONS_DIR / "fn_admin_list_projects.sql").read_text())
	op.execute((FUNCTIONS_DIR / "fn_admin_list_login_history.sql").read_text())


def downgrade() -> None:
	op.execute(f"DROP FUNCTION IF EXISTS {_FN_LIST_LOGIN_HISTORY_SIGNATURE}")
	op.execute(f"DROP FUNCTION IF EXISTS {_FN_LIST_PROJECTS_SIGNATURE}")
	op.execute((LEGACY_FUNCTIONS_DIR / "0020_fn_admin_list_projects.sql").read_text())
	op.execute((LEGACY_FUNCTIONS_DIR / "0020_fn_admin_list_login_history.sql").read_text())
