"""create admin用DB関数・ストアドプロシージャ

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-07

"""
from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DB_DIR = Path(__file__).resolve().parents[3] / "db"
FUNCTIONS_DIR = DB_DIR / "functions"
PROCEDURES_DIR = DB_DIR / "procedures"

_FUNCTION_FILES = (
	"fn_admin_list_users.sql",
	"fn_admin_list_projects.sql",
	"fn_admin_list_login_history.sql",
)
_PROCEDURE_FILES = (
	"sp_admin_update_user_role.sql",
	"sp_admin_update_user_status.sql",
	"sp_admin_deactivate_project.sql",
)


def upgrade() -> None:
	for filename in _FUNCTION_FILES:
		op.execute((FUNCTIONS_DIR / filename).read_text())
	for filename in _PROCEDURE_FILES:
		op.execute((PROCEDURES_DIR / filename).read_text())


def downgrade() -> None:
	op.execute("DROP PROCEDURE IF EXISTS sp_admin_deactivate_project(UUID, BOOLEAN)")
	op.execute("DROP PROCEDURE IF EXISTS sp_admin_update_user_status(UUID, UUID, BOOLEAN)")
	op.execute("DROP PROCEDURE IF EXISTS sp_admin_update_user_role(UUID, UUID, VARCHAR)")

	op.execute(
		"DROP FUNCTION IF EXISTS fn_admin_list_login_history("
		"UUID, VARCHAR, VARCHAR, BOOLEAN, TIMESTAMPTZ, TIMESTAMPTZ, INTEGER, INTEGER)"
	)
	op.execute("DROP FUNCTION IF EXISTS fn_admin_list_projects(VARCHAR, BOOLEAN, INTEGER, INTEGER)")
	op.execute("DROP FUNCTION IF EXISTS fn_admin_list_users(VARCHAR, VARCHAR, BOOLEAN, INTEGER, INTEGER)")
