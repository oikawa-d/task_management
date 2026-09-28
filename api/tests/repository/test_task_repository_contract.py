"""app.repository.task_repository.list_for_user_with_totalの件数取得ロジック、および
db/functions配下のSQL関数がコメント件数をN+1クエリではなく1回のグループ化JOINで
取得している契約（規約）を検証するテスト。DB接続は不要（SQLファイルの静的な内容検査とモックのみ）。
"""

from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.repository import task_repository

DB_FUNCTIONS = Path(__file__).parents[3] / "db" / "functions"


class _MappingsResult:
	"""SQLAlchemyのCursorResult風インターフェース（mappings().all() / scalar_one()）を模擬するダミー結果セット。"""

	def __init__(self, rows: list[dict[str, object]]) -> None:
		"""返却する行データを保持する。

		Args:
			rows: mappings().all()で返す辞書のリスト。scalar_one()はrows[0]["count"]を返す。
		"""
		self._rows = rows

	def mappings(self) -> "_MappingsResult":
		"""SQLAlchemyのResult.mappings()と同様、自身を返してメソッドチェーンを可能にする。"""
		return self

	def all(self) -> list[dict[str, object]]:
		"""保持している全行を返す。"""
		return self._rows

	def scalar_one(self) -> object:
		"""先頭行のcount列の値を返す（件数取得クエリの戻り値を模擬）。"""
		return self._rows[0]["count"]


@pytest.mark.asyncio
async def test_list_for_user_uses_count_function_when_requested_page_is_empty() -> None:
	"""要求したページのタスク一覧が0件だった場合、list_for_user_with_totalが
	別途fn_count_tasks関数を呼ぶ集計クエリを発行して総件数を取得すること、
	またそのクエリへ渡すパラメータ（project_id・status・include_inactive・unassigned等）が
	一覧取得クエリと整合していることを検証する。
	"""
	db = AsyncMock()
	db.execute.side_effect = [_MappingsResult([]), _MappingsResult([{"count": 11}])]

	items, total = await task_repository.list_for_user_with_total(db, uuid4(), None, "todo", False, 5, 25, False)

	assert items == []
	assert total == 11
	count_statement = str(db.execute.await_args_list[1].args[0])
	assert "fn_count_tasks" in count_statement
	assert db.execute.await_args_list[1].args[1] == {
		"user_id": db.execute.await_args_list[0].args[1]["user_id"],
		"project_id": None,
		"status": "todo",
		"include_inactive": False,
		"unassigned": False,
	}


@pytest.mark.parametrize(
	"function_name",
	["fn_get_task", "fn_get_project_board", "fn_list_tasks", "fn_list_calendar_tasks"],
)
def test_task_comment_counts_use_one_grouped_join(function_name: str) -> None:
	"""指定したdb/functions配下のSQL関数定義が、タスクごとのコメント件数を
	task_idでグループ化したcomment_counts CTE/サブクエリへのLEFT JOINで取得しており、
	タスク行ごとに相関サブクエリでcount(*)を実行するN+1形式になっていないことを検証する。
	"""
	sql = (DB_FUNCTIONS / f"{function_name}.sql").read_text()

	assert "GROUP BY task_id" in sql
	assert "comment_counts" in sql
	assert "LEFT JOIN comment_counts" in sql
	assert "SELECT count(*) FROM task_comments c WHERE c.task_id = t.id" not in sql
