from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.repository import admin_repository

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ADMIN_MIGRATION = REPOSITORY_ROOT / "api/alembic/versions/0015_create_admin_functions.py"

FUNCTION_FILES = (
	"fn_admin_list_users.sql",
	"fn_admin_list_projects.sql",
	"fn_admin_list_login_history.sql",
)
PROCEDURE_FILES = (
	"sp_admin_update_user_role.sql",
	"sp_admin_update_user_status.sql",
	"sp_admin_deactivate_project.sql",
)


def test_admin_migration_references_existing_sql_sources() -> None:
	assert ADMIN_MIGRATION.is_file()
	assert all((REPOSITORY_ROOT / "db/functions" / filename).is_file() for filename in FUNCTION_FILES)
	assert all((REPOSITORY_ROOT / "db/procedures" / filename).is_file() for filename in PROCEDURE_FILES)


def test_admin_user_update_procedures_lock_target_rows() -> None:
	for filename in ("sp_admin_update_user_role.sql", "sp_admin_update_user_status.sql"):
		sql = (REPOSITORY_ROOT / "db/procedures" / filename).read_text(encoding="utf-8")
		assert "SELECT role, is_active INTO v_current_role, v_current_is_active" in sql
		assert "FOR UPDATE;" in sql


class _Result:
	def scalars(self) -> "_Result":
		return self

	def all(self) -> list[object]:
		return []


@pytest.mark.asyncio
async def test_admin_repository_passes_list_arguments_to_db_functions() -> None:
	db = AsyncMock()
	db.execute.return_value = _Result()
	user_id = uuid4()

	await admin_repository.list_users(db, "taro", "admin", False, 20, 40)
	user_statement = db.execute.await_args.args[0]
	assert "fn_admin_list_users" in str(user_statement)
	assert user_statement.compile().params == {
		"query": "taro",
		"role": "admin",
		"is_active": False,
		"limit": 20,
		"offset": 40,
	}

	db.execute.reset_mock()
	await admin_repository.list_projects(db, "project", True, 10, 30)
	project_statement = db.execute.await_args.args[0]
	assert "fn_admin_list_projects" in str(project_statement)
	assert project_statement.compile().params == {
		"query": "project",
		"is_active": True,
		"limit": 10,
		"offset": 30,
	}

	db.execute.reset_mock()
	await admin_repository.list_login_history(db, user_id, "login", "jwt", True, None, None, 5, 15)
	history_statement = db.execute.await_args.args[0]
	assert "fn_admin_list_login_history" in str(history_statement)
	assert history_statement.compile().params == {
		"user_id": user_id,
		"query": "login",
		"login_method": "jwt",
		"success": True,
		"created_from": None,
		"created_to": None,
		"limit": 5,
		"offset": 15,
	}


@pytest.mark.asyncio
async def test_admin_repository_passes_update_arguments_to_procedures() -> None:
	db = AsyncMock()
	actor_id = uuid4()
	target_id = uuid4()

	await admin_repository.update_user_role(db, actor_id, target_id, "member")
	assert str(db.execute.await_args.args[0]) == "CALL sp_admin_update_user_role(:actor_id, :target_id, :new_role)"
	assert db.execute.await_args.args[1] == {
		"actor_id": actor_id,
		"target_id": target_id,
		"new_role": "member",
	}

	db.execute.reset_mock()
	await admin_repository.update_user_status(db, actor_id, target_id, False)
	assert str(db.execute.await_args.args[0]) == "CALL sp_admin_update_user_status(:actor_id, :target_id, :is_active)"
	assert db.execute.await_args.args[1] == {
		"actor_id": actor_id,
		"target_id": target_id,
		"is_active": False,
	}

	db.execute.reset_mock()
	await admin_repository.deactivate_project(db, target_id, False)
	assert str(db.execute.await_args.args[0]) == "CALL sp_admin_deactivate_project(:project_id, :is_active)"
	assert db.execute.await_args.args[1] == {"project_id": target_id, "is_active": False}
