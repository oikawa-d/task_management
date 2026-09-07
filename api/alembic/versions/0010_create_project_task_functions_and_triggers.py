"""create project/task functions, procedures and triggers

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-07

"""
from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DB_DIR = Path(__file__).resolve().parents[3] / "db"
FUNCTIONS_DIR = DB_DIR / "functions"
PROCEDURES_DIR = DB_DIR / "procedures"

_TRIGGER_TABLES = ("projects", "tasks", "task_comments")

_FUNCTION_FILES = (
	"fn_is_project_member.sql",
	"fn_next_task_position.sql",
	"fn_get_project.sql",
	"fn_list_projects.sql",
	"fn_search_member_candidates.sql",
	"fn_list_project_members.sql",
	"fn_get_project_board.sql",
	"fn_get_task.sql",
	"fn_list_tasks.sql",
	"fn_list_task_comments.sql",
	"fn_get_comment_with_task.sql",
)
_PROCEDURE_FILES = (
	"sp_create_project.sql",
	"sp_update_project.sql",
	"sp_deactivate_project.sql",
	"sp_add_project_member.sql",
	"sp_remove_project_member.sql",
	"sp_create_task.sql",
	"sp_update_task.sql",
	"sp_deactivate_task.sql",
	"sp_add_task_comment.sql",
	"sp_update_task_comment.sql",
	"sp_delete_task_comment.sql",
)


def upgrade() -> None:
	for table in _TRIGGER_TABLES:
		op.execute(
			f"CREATE TRIGGER trg_{table}_set_updated_at "
			f"BEFORE UPDATE ON {table} FOR EACH ROW "
			f"EXECUTE FUNCTION trg_set_updated_at();"
		)
	for filename in _FUNCTION_FILES:
		op.execute((FUNCTIONS_DIR / filename).read_text())
	for filename in _PROCEDURE_FILES:
		op.execute((PROCEDURES_DIR / filename).read_text())


def downgrade() -> None:
	op.execute("DROP PROCEDURE IF EXISTS sp_delete_task_comment(UUID, UUID)")
	op.execute("DROP PROCEDURE IF EXISTS sp_update_task_comment(UUID, UUID, TEXT)")
	op.execute("DROP PROCEDURE IF EXISTS sp_add_task_comment(UUID, UUID, TEXT)")
	op.execute("DROP PROCEDURE IF EXISTS sp_deactivate_task(UUID, BOOLEAN)")
	op.execute(
		"DROP PROCEDURE IF EXISTS sp_update_task("
		"UUID, UUID, INTEGER, VARCHAR, TEXT, VARCHAR, UUID, TIMESTAMPTZ, INTEGER)"
	)
	op.execute(
		"DROP PROCEDURE IF EXISTS sp_create_task("
		"UUID, UUID, UUID, VARCHAR, TEXT, VARCHAR, TIMESTAMPTZ, INTEGER)"
	)
	op.execute("DROP PROCEDURE IF EXISTS sp_remove_project_member(UUID, UUID)")
	op.execute("DROP PROCEDURE IF EXISTS sp_add_project_member(UUID, UUID, UUID)")
	op.execute("DROP PROCEDURE IF EXISTS sp_deactivate_project(UUID, BOOLEAN)")
	op.execute("DROP PROCEDURE IF EXISTS sp_update_project(UUID, VARCHAR, TEXT, TIMESTAMPTZ, TIMESTAMPTZ)")
	op.execute("DROP PROCEDURE IF EXISTS sp_create_project(UUID, VARCHAR, TEXT, TIMESTAMPTZ, TIMESTAMPTZ)")

	op.execute("DROP FUNCTION IF EXISTS fn_get_comment_with_task(UUID)")
	op.execute("DROP FUNCTION IF EXISTS fn_list_task_comments(UUID)")
	op.execute("DROP FUNCTION IF EXISTS fn_list_tasks(UUID, UUID, VARCHAR, BOOLEAN, INTEGER, INTEGER)")
	op.execute("DROP FUNCTION IF EXISTS fn_get_task(UUID)")
	op.execute("DROP FUNCTION IF EXISTS fn_get_project_board(UUID, BOOLEAN)")
	op.execute("DROP FUNCTION IF EXISTS fn_list_project_members(UUID)")
	op.execute("DROP FUNCTION IF EXISTS fn_search_member_candidates(UUID, VARCHAR, INTEGER, INTEGER)")
	op.execute("DROP FUNCTION IF EXISTS fn_list_projects(UUID, BOOLEAN, INTEGER, INTEGER)")
	op.execute("DROP FUNCTION IF EXISTS fn_get_project(UUID)")
	op.execute("DROP FUNCTION IF EXISTS fn_next_task_position(UUID, VARCHAR)")
	op.execute("DROP FUNCTION IF EXISTS fn_is_project_member(UUID, UUID)")

	for table in reversed(_TRIGGER_TABLES):
		op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_set_updated_at ON {table}")
