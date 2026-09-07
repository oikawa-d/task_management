"""create auth/user functions, procedures and triggers

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-07

"""
from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DB_DIR = Path(__file__).resolve().parents[3] / "db"
FUNCTIONS_DIR = DB_DIR / "functions"
PROCEDURES_DIR = DB_DIR / "procedures"

_FUNCTION_FILES = (
	"trg_set_updated_at.sql",
	"fn_get_user.sql",
	"fn_find_user_by_identifier.sql",
	"fn_find_user_by_email.sql",
	"fn_find_oauth_account.sql",
	"fn_list_user_login_history.sql",
	"fn_list_user_oauth_accounts.sql",
)
_PROCEDURE_FILES = (
	"sp_purge_login_history.sql",
	"sp_register_user.sql",
	"sp_verify_user_email.sql",
	"sp_update_user_password.sql",
	"sp_update_user_profile.sql",
	"sp_upsert_oauth_account.sql",
	"sp_record_login_history.sql",
)


def upgrade() -> None:
	for filename in _FUNCTION_FILES:
		op.execute((FUNCTIONS_DIR / filename).read_text())
	op.execute(
		"CREATE TRIGGER trg_users_set_updated_at "
		"BEFORE UPDATE ON users FOR EACH ROW "
		"EXECUTE FUNCTION trg_set_updated_at();"
	)
	for filename in _PROCEDURE_FILES:
		op.execute((PROCEDURES_DIR / filename).read_text())


def downgrade() -> None:
	op.execute(
		"DROP PROCEDURE IF EXISTS sp_record_login_history(UUID, VARCHAR, VARCHAR, INET, TEXT, BOOLEAN, VARCHAR)"
	)
	op.execute("DROP PROCEDURE IF EXISTS sp_upsert_oauth_account(UUID, VARCHAR, TEXT)")
	op.execute("DROP PROCEDURE IF EXISTS sp_update_user_profile(UUID, VARCHAR, VARCHAR, VARCHAR, VARCHAR, DATE)")
	op.execute("DROP PROCEDURE IF EXISTS sp_update_user_password(UUID, TEXT)")
	op.execute("DROP PROCEDURE IF EXISTS sp_verify_user_email(UUID)")
	op.execute("DROP PROCEDURE IF EXISTS sp_register_user(VARCHAR, VARCHAR, TEXT)")
	op.execute("DROP PROCEDURE IF EXISTS sp_purge_login_history(INTEGER)")
	op.execute("DROP TRIGGER IF EXISTS trg_users_set_updated_at ON users")
	op.execute("DROP FUNCTION IF EXISTS fn_list_user_oauth_accounts(UUID)")
	op.execute("DROP FUNCTION IF EXISTS fn_list_user_login_history(UUID, INTEGER, INTEGER)")
	op.execute("DROP FUNCTION IF EXISTS fn_find_oauth_account(VARCHAR, TEXT)")
	op.execute("DROP FUNCTION IF EXISTS fn_find_user_by_email(VARCHAR)")
	op.execute("DROP FUNCTION IF EXISTS fn_find_user_by_identifier(VARCHAR)")
	op.execute("DROP FUNCTION IF EXISTS fn_get_user(UUID)")
	op.execute("DROP FUNCTION IF EXISTS trg_set_updated_at()")
