"""app.repository.admin_repository（管理者向けユーザー/プロジェクト/ログイン履歴の一覧・件数取得・更新）に対する
単体テスト、および対応するAlembicマイグレーション・db/functions・db/proceduresのSQL定義が
期待する契約（total_countをwindow関数で返す、行ロックしてFOR UPDATEする等）を満たしているかの静的検査。
DB接続はAsyncMockで模擬し、SQL検査はファイル読み取りのみで実DBには接続しない。
"""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.repository import admin_repository

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ADMIN_MIGRATION = REPOSITORY_ROOT / "api/alembic/versions/0015_create_admin_functions.py"
ADMIN_TOTAL_COUNT_MIGRATION = REPOSITORY_ROOT / "api/alembic/versions/0020_add_admin_list_total_count_and_not_found.py"
ADMIN_AGGREGATE_MIGRATION = REPOSITORY_ROOT / "api/alembic/versions/0022_optimize_admin_list_functions.py"

FUNCTION_FILES = (
	"fn_admin_list_users.sql",
	"fn_count_admin_users.sql",
	"fn_admin_list_projects.sql",
	"fn_count_admin_projects.sql",
	"fn_admin_list_login_history.sql",
	"fn_count_admin_login_history.sql",
)
PROCEDURE_FILES = (
	"sp_admin_update_user_role.sql",
	"sp_admin_update_user_status.sql",
	"sp_admin_deactivate_project.sql",
)


def test_admin_migration_references_existing_sql_sources() -> None:
	"""管理者機能用の各Alembicマイグレーションファイルが実在し、それらが参照するSQL関数・
	レガシー版関数・ストアドプロシージャの各ファイルもdb/functions・db/functions/legacy・
	db/procedures配下に実在することを検証する（マイグレーションとSQL資産の対応漏れ検知）。
	"""
	assert ADMIN_MIGRATION.is_file()
	assert ADMIN_TOTAL_COUNT_MIGRATION.is_file()
	assert ADMIN_AGGREGATE_MIGRATION.is_file()
	assert all((REPOSITORY_ROOT / "db/functions" / filename).is_file() for filename in FUNCTION_FILES)
	assert all(
		(REPOSITORY_ROOT / "db/functions/legacy" / filename).is_file()
		for filename in ("0020_fn_admin_list_projects.sql", "0020_fn_admin_list_login_history.sql")
	)
	assert all((REPOSITORY_ROOT / "db/procedures" / filename).is_file() for filename in PROCEDURE_FILES)


def test_admin_list_functions_return_total_count_via_window_function() -> None:
	"""管理者向け一覧取得SQL関数（users/projects/login_history）が、別途count用関数を呼ばずとも
	ウィンドウ関数count(*) OVER ()で総件数(total_count BIGINT)を1回のクエリで返せる定義に
	なっていることを検証する。
	"""
	for filename in ("fn_admin_list_users.sql", "fn_admin_list_projects.sql", "fn_admin_list_login_history.sql"):
		sql = (REPOSITORY_ROOT / "db/functions" / filename).read_text(encoding="utf-8")
		assert "count(*) OVER ()" in sql
		assert "total_count BIGINT" in sql


def test_admin_list_functions_return_aggregates_and_joined_user() -> None:
	"""fn_admin_list_projectsがproject_members由来のmember_countとtasksテーブルを
	ステータス別にFILTER集計したtask_count_todo等を持つこと、fn_admin_list_login_historyが
	usersテーブルをLEFT JOINしてログイン主体のユーザー情報を含めて返す定義になっていることを検証する。
	"""
	projects_sql = (REPOSITORY_ROOT / "db/functions/fn_admin_list_projects.sql").read_text(encoding="utf-8")
	assert "member_count BIGINT" in projects_sql
	assert "task_count_todo BIGINT" in projects_sql
	assert "count(*) FILTER (WHERE status = 'todo')" in projects_sql
	assert "FROM project_members" in projects_sql
	assert "FROM tasks" in projects_sql

	history_sql = (REPOSITORY_ROOT / "db/functions/fn_admin_list_login_history.sql").read_text(encoding="utf-8")
	assert '"user" users' in history_sql
	assert "LEFT JOIN users u" in history_sql


def test_admin_user_update_procedures_lock_target_rows_and_detect_not_found() -> None:
	"""sp_admin_update_user_role・sp_admin_update_user_statusの両ストアドプロシージャが、
	更新前の値をOUTパラメータへ退避しつつFOR UPDATEで対象行をロックしていること、
	対象ユーザーが存在しない場合はIF NOT FOUNDでエラーコードP0010を送出する定義になっていることを検証する。
	"""
	role_sql = (REPOSITORY_ROOT / "db/procedures/sp_admin_update_user_role.sql").read_text(encoding="utf-8")
	assert "SELECT role, is_active INTO p_old_role, v_current_is_active" in role_sql
	assert "FOR UPDATE;" in role_sql
	assert "IF NOT FOUND THEN" in role_sql
	assert "P0010" in role_sql
	assert "OUT p_old_role VARCHAR" in role_sql

	status_sql = (REPOSITORY_ROOT / "db/procedures/sp_admin_update_user_status.sql").read_text(encoding="utf-8")
	assert "SELECT role, is_active INTO v_current_role, p_old_is_active" in status_sql
	assert "FOR UPDATE;" in status_sql
	assert "IF NOT FOUND THEN" in status_sql
	assert "P0010" in status_sql
	assert "OUT p_old_is_active BOOLEAN" in status_sql


class _MappingsResult:
	"""SQLAlchemyのCursorResult風インターフェース（mappings()・イテレーション・one()・scalar_one()）を
	模擬するダミー結果セット。
	"""

	def __init__(self, rows: list[dict[str, object]]) -> None:
		"""返却する行データを保持する。

		Args:
			rows: mappings()経由で返す辞書のリスト。one()は先頭行、scalar_one()は先頭行のcount列を返す。
		"""
		self._rows = rows

	def mappings(self) -> "_MappingsResult":
		"""SQLAlchemyのResult.mappings()と同様、自身を返してメソッドチェーンを可能にする。"""
		return self

	def __iter__(self):
		"""保持している全行を順にイテレートする。"""
		return iter(self._rows)

	def one(self) -> dict[str, object]:
		"""先頭行を返す（ちょうど1件のみ期待するクエリの戻り値を模擬）。"""
		return self._rows[0]

	def scalar_one(self) -> object:
		"""先頭行のcount列の値を返す（件数取得クエリの戻り値を模擬）。"""
		return self._rows[0]["count"]


def _user_row(**overrides: object) -> dict[str, object]:
	"""fn_admin_list_usersの戻り値行を模擬する、ユーザー1件分の辞書を作る。

	Args:
		**overrides: 既定値を上書きしたいカラム（例: total_count）。

	Returns:
		既定値にoverridesを反映した行データの辞書。
	"""
	defaults: dict[str, object] = {
		"id": uuid4(),
		"username": "taro",
		"email": "taro@example.com",
		"password_hash": None,
		"last_name": "山田",
		"first_name": "太郎",
		"last_name_kana": None,
		"first_name_kana": None,
		"birth_date": None,
		"role": "member",
		"is_active": True,
		"email_verified_at": None,
		"created_at": datetime.now(timezone.utc),
		"updated_at": datetime.now(timezone.utc),
		"total_count": 1,
	}
	defaults.update(overrides)
	return defaults


def _project_row(**overrides: object) -> dict[str, object]:
	"""fn_admin_list_projectsの戻り値行を模擬する、プロジェクト1件分（オーナー情報・タスク件数集計込み）の辞書を作る。

	Args:
		**overrides: 既定値を上書きしたいカラム（例: total_count）。

	Returns:
		既定値にoverridesを反映した行データの辞書。
	"""
	owner_id = uuid4()
	defaults: dict[str, object] = {
		"id": uuid4(),
		"name": "Cerberus開発",
		"description": None,
		"owner_id": owner_id,
		"is_active": True,
		"start_at": None,
		"end_at": None,
		"created_at": datetime.now(timezone.utc),
		"updated_at": datetime.now(timezone.utc),
		"member_count": 2,
		"task_count_todo": 3,
		"task_count_in_progress": 4,
		"task_count_done": 5,
		"total_count": 1,
		"owner_user_id": owner_id,
		"owner_username": "owner",
		"owner_email": "owner@example.com",
		"owner_password_hash": None,
		"owner_last_name": "山田",
		"owner_first_name": "太郎",
		"owner_last_name_kana": None,
		"owner_first_name_kana": None,
		"owner_birth_date": None,
		"owner_role": "member",
		"owner_is_active": True,
		"owner_email_verified_at": None,
		"owner_created_at": datetime.now(timezone.utc),
		"owner_updated_at": datetime.now(timezone.utc),
	}
	defaults.update(overrides)
	return defaults


def _login_history_row(**overrides: object) -> dict[str, object]:
	"""fn_admin_list_login_historyの戻り値行を模擬する、ログイン履歴1件分（ユーザー情報込み）の辞書を作る。

	Args:
		**overrides: 既定値を上書きしたいカラム（例: total_count）。

	Returns:
		既定値にoverridesを反映した行データの辞書。
	"""
	defaults: dict[str, object] = {
		"id": uuid4(),
		"user_id": uuid4(),
		"login_identifier": "taro",
		"login_method": "session",
		"ip_address": None,
		"user_agent": None,
		"success": True,
		"failure_reason": None,
		"created_at": datetime.now(timezone.utc),
		"user_info_id": uuid4(),
		"user_info_username": "taro",
		"user_info_last_name": "山田",
		"user_info_first_name": "太郎",
		"total_count": 1,
	}
	defaults.update(overrides)
	return defaults


@pytest.mark.asyncio
async def test_admin_repository_list_users_maps_total_count() -> None:
	"""list_usersが検索条件（query・role・is_active・limit・offset）をfn_admin_list_users関数へ
	そのまま渡し、戻り値の各行が持つtotal_countとユーザー情報が結果オブジェクトへ正しくマッピングされることを検証する。
	"""
	db = AsyncMock()
	db.execute.return_value = _MappingsResult([_user_row(total_count=25)])

	items = await admin_repository.list_users(db, "taro", "admin", False, 20, 40)

	statement = db.execute.await_args.args[0]
	assert "fn_admin_list_users" in str(statement)
	assert db.execute.await_args.args[1] == {
		"query": "taro",
		"role": "admin",
		"is_active": False,
		"limit": 20,
		"offset": 40,
	}
	assert items[0].total_count == 25
	assert items[0].user.username == "taro"


@pytest.mark.asyncio
async def test_admin_repository_count_users_calls_fallback_function() -> None:
	"""count_usersが件数専用のfn_count_admin_users関数を呼び、0件の場合は0を返すことを検証する。"""
	db = AsyncMock()
	db.execute.return_value = _MappingsResult([{"count": 0}])

	total = await admin_repository.count_users(db, "taro", None, None)

	statement = db.execute.await_args.args[0]
	assert "fn_count_admin_users" in str(statement)
	assert total == 0


@pytest.mark.asyncio
async def test_admin_repository_list_projects_maps_total_count() -> None:
	"""list_projectsが検索条件をfn_admin_list_projects関数（member_count・タスクステータス別件数を
	含むSELECT列）へそのまま渡し、戻り値の1回のクエリからtotal_count・集計件数・オーナー情報が
	正しくマッピングされることを検証する。
	"""
	db = AsyncMock()
	db.execute.return_value = _MappingsResult([_project_row(total_count=3)])

	items = await admin_repository.list_projects(db, "project", True, 10, 30)

	statement = db.execute.await_args.args[0]
	assert "fn_admin_list_projects" in str(statement)
	assert "member_count" in str(statement)
	assert "task_count_todo" in str(statement)
	assert "task_count_in_progress" in str(statement)
	assert "task_count_done" in str(statement)
	assert db.execute.await_args.args[1] == {"query": "project", "is_active": True, "limit": 10, "offset": 30}
	assert items[0].total_count == 3
	assert items[0].member_count == 2
	assert items[0].task_count_todo == 3
	assert items[0].task_count_in_progress == 4
	assert items[0].task_count_done == 5
	assert items[0].project.owner is not None
	assert items[0].project.owner.id == items[0].project.owner_id
	assert items[0].project.owner.username == "owner"
	assert db.execute.await_count == 1


@pytest.mark.asyncio
async def test_admin_repository_count_projects_calls_fallback_function() -> None:
	"""count_projectsが件数専用のfn_count_admin_projects関数を呼び、0件の場合は0を返すことを検証する。"""
	db = AsyncMock()
	db.execute.return_value = _MappingsResult([{"count": 0}])

	total = await admin_repository.count_projects(db, None, None)

	statement = db.execute.await_args.args[0]
	assert "fn_count_admin_projects" in str(statement)
	assert total == 0


@pytest.mark.asyncio
async def test_admin_repository_list_login_history_maps_total_count() -> None:
	"""list_login_historyが検索条件（user_id・query・login_method・success・作成日時範囲・
	limit・offset）をfn_admin_list_login_history関数へそのまま渡し、戻り値のtotal_countと
	紐づくユーザー情報が正しくマッピングされることを検証する。
	"""
	db = AsyncMock()
	user_id = uuid4()
	db.execute.return_value = _MappingsResult([_login_history_row(total_count=7)])

	items = await admin_repository.list_login_history(db, user_id, "login", "jwt", True, None, None, 5, 15)

	statement = db.execute.await_args.args[0]
	assert "fn_admin_list_login_history" in str(statement)
	assert db.execute.await_args.args[1] == {
		"user_id": user_id,
		"query": "login",
		"login_method": "jwt",
		"success": True,
		"created_from": None,
		"created_to": None,
		"limit": 5,
		"offset": 15,
	}
	assert items[0].total_count == 7
	assert items[0].user is not None
	assert items[0].user.username == "taro"
	assert db.execute.await_count == 1


@pytest.mark.asyncio
async def test_admin_repository_count_login_history_calls_fallback_function() -> None:
	"""count_login_historyが件数専用のfn_count_admin_login_history関数を呼び、0件の場合は0を返すことを検証する。"""
	db = AsyncMock()
	db.execute.return_value = _MappingsResult([{"count": 0}])

	total = await admin_repository.count_login_history(db, None, None, None, None, None, None)

	statement = db.execute.await_args.args[0]
	assert "fn_count_admin_login_history" in str(statement)
	assert total == 0


@pytest.mark.asyncio
async def test_admin_repository_update_user_role_passes_out_param_placeholder() -> None:
	"""update_user_roleが、actor_id・target_id・new_roleを引数にOUTパラメータ用のNULLプレースホルダーを
	含めてsp_admin_update_user_roleストアドプロシージャをCALLし、変更前のロール（OUTパラメータ）を
	戻り値として返すことを検証する。
	"""
	db = AsyncMock()
	actor_id = uuid4()
	target_id = uuid4()
	db.execute.return_value = _MappingsResult([{"p_old_role": "member"}])

	old_role = await admin_repository.update_user_role(db, actor_id, target_id, "admin")

	assert (
		str(db.execute.await_args.args[0]) == "CALL sp_admin_update_user_role(:actor_id, :target_id, :new_role, NULL)"
	)
	assert db.execute.await_args.args[1] == {
		"actor_id": actor_id,
		"target_id": target_id,
		"new_role": "admin",
	}
	assert old_role == "member"


@pytest.mark.asyncio
async def test_admin_repository_update_user_status_passes_out_param_placeholder() -> None:
	"""update_user_statusが、actor_id・target_id・is_activeを引数にOUTパラメータ用のNULL
	プレースホルダーを含めてsp_admin_update_user_statusストアドプロシージャをCALLし、
	変更前の有効状態（OUTパラメータ）を戻り値として返すことを検証する。
	"""
	db = AsyncMock()
	actor_id = uuid4()
	target_id = uuid4()
	db.execute.return_value = _MappingsResult([{"p_old_is_active": True}])

	old_is_active = await admin_repository.update_user_status(db, actor_id, target_id, False)

	assert (
		str(db.execute.await_args.args[0])
		== "CALL sp_admin_update_user_status(:actor_id, :target_id, :is_active, NULL)"
	)
	assert db.execute.await_args.args[1] == {
		"actor_id": actor_id,
		"target_id": target_id,
		"is_active": False,
	}
	assert old_is_active is True


@pytest.mark.asyncio
async def test_admin_repository_deactivate_project_passes_arguments_to_procedure() -> None:
	"""deactivate_projectが、project_id・is_activeを引数にsp_admin_deactivate_projectストアドプロシージャを
	CALLしていることを検証する。
	"""
	db = AsyncMock()
	target_id = uuid4()

	await admin_repository.deactivate_project(db, target_id, False)

	assert str(db.execute.await_args.args[0]) == "CALL sp_admin_deactivate_project(:project_id, :is_active)"
	assert db.execute.await_args.args[1] == {"project_id": target_id, "is_active": False}
