"""add total_count to fn_admin_list_* and P0010 not-found to sp_admin_update_user_*

PR #347レビュー対応:
- fn_admin_list_users / fn_admin_list_projects / fn_admin_list_login_history に
  ウィンドウ関数count(*) OVER()でtotal_countを追加し、該当0件用のfn_count_admin_*を新設する
  （issue #143 / PR #294のfn_list_notifications対応と同じ手法）。
- sp_admin_update_user_role / sp_admin_update_user_status に対象不存在判定（P0010）と
  更新前値のOUTパラメータ（p_old_role / p_old_is_active）を追加し、
  service層の事前存在確認SELECTを不要にする。

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-11

"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DB_DIR = Path(__file__).resolve().parents[3] / "db"
FUNCTIONS_DIR = DB_DIR / "functions"
LEGACY_FUNCTIONS_DIR = FUNCTIONS_DIR / "legacy"
PROCEDURES_DIR = DB_DIR / "procedures"
LEGACY_PROCEDURES_DIR = PROCEDURES_DIR / "legacy"

_FN_LIST_USERS_SIGNATURE = "fn_admin_list_users(VARCHAR, VARCHAR, BOOLEAN, INTEGER, INTEGER)"
_FN_LIST_PROJECTS_SIGNATURE = "fn_admin_list_projects(VARCHAR, BOOLEAN, INTEGER, INTEGER)"
_FN_LIST_LOGIN_HISTORY_SIGNATURE = (
	"fn_admin_list_login_history(UUID, VARCHAR, VARCHAR, BOOLEAN, TIMESTAMPTZ, TIMESTAMPTZ, INTEGER, INTEGER)"
)
_FN_COUNT_USERS_SIGNATURE = "fn_count_admin_users(VARCHAR, VARCHAR, BOOLEAN)"
_FN_COUNT_PROJECTS_SIGNATURE = "fn_count_admin_projects(VARCHAR, BOOLEAN)"
_FN_COUNT_LOGIN_HISTORY_SIGNATURE = (
	"fn_count_admin_login_history(UUID, VARCHAR, VARCHAR, BOOLEAN, TIMESTAMPTZ, TIMESTAMPTZ)"
)
_SP_UPDATE_USER_ROLE_SIGNATURE = "sp_admin_update_user_role(UUID, UUID, VARCHAR)"
_SP_UPDATE_USER_STATUS_SIGNATURE = "sp_admin_update_user_status(UUID, UUID, BOOLEAN)"


def upgrade() -> None:
	# PostgreSQLはCREATE OR REPLACEで戻り値型・OUTパラメータを変更できないため、
	# 一度DROPしてから新しい定義で作り直す。
	op.execute(f"DROP FUNCTION IF EXISTS {_FN_LIST_USERS_SIGNATURE}")
	op.execute(f"DROP FUNCTION IF EXISTS {_FN_LIST_PROJECTS_SIGNATURE}")
	op.execute(f"DROP FUNCTION IF EXISTS {_FN_LIST_LOGIN_HISTORY_SIGNATURE}")
	op.execute(f"DROP PROCEDURE IF EXISTS {_SP_UPDATE_USER_ROLE_SIGNATURE}")
	op.execute(f"DROP PROCEDURE IF EXISTS {_SP_UPDATE_USER_STATUS_SIGNATURE}")

	op.execute((FUNCTIONS_DIR / "fn_admin_list_users.sql").read_text())
	op.execute((FUNCTIONS_DIR / "fn_count_admin_users.sql").read_text())
	op.execute((FUNCTIONS_DIR / "fn_admin_list_projects.sql").read_text())
	op.execute((FUNCTIONS_DIR / "fn_count_admin_projects.sql").read_text())
	op.execute((FUNCTIONS_DIR / "fn_admin_list_login_history.sql").read_text())
	op.execute((FUNCTIONS_DIR / "fn_count_admin_login_history.sql").read_text())
	op.execute((PROCEDURES_DIR / "sp_admin_update_user_role.sql").read_text())
	op.execute((PROCEDURES_DIR / "sp_admin_update_user_status.sql").read_text())


def downgrade() -> None:
	op.execute(f"DROP FUNCTION IF EXISTS {_FN_COUNT_LOGIN_HISTORY_SIGNATURE}")
	op.execute(f"DROP FUNCTION IF EXISTS {_FN_COUNT_PROJECTS_SIGNATURE}")
	op.execute(f"DROP FUNCTION IF EXISTS {_FN_COUNT_USERS_SIGNATURE}")
	op.execute(f"DROP FUNCTION IF EXISTS {_FN_LIST_LOGIN_HISTORY_SIGNATURE}")
	op.execute(f"DROP FUNCTION IF EXISTS {_FN_LIST_PROJECTS_SIGNATURE}")
	op.execute(f"DROP FUNCTION IF EXISTS {_FN_LIST_USERS_SIGNATURE}")
	op.execute(f"DROP PROCEDURE IF EXISTS {_SP_UPDATE_USER_STATUS_SIGNATURE}")
	op.execute(f"DROP PROCEDURE IF EXISTS {_SP_UPDATE_USER_ROLE_SIGNATURE}")

	op.execute((LEGACY_FUNCTIONS_DIR / "0015_fn_admin_list_users.sql").read_text())
	op.execute((LEGACY_FUNCTIONS_DIR / "0015_fn_admin_list_projects.sql").read_text())
	op.execute((LEGACY_FUNCTIONS_DIR / "0015_fn_admin_list_login_history.sql").read_text())
	op.execute((LEGACY_PROCEDURES_DIR / "0015_sp_admin_update_user_role.sql").read_text())
	op.execute((LEGACY_PROCEDURES_DIR / "0015_sp_admin_update_user_status.sql").read_text())
