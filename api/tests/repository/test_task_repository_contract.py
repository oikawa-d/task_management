from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.repository import task_repository

DB_FUNCTIONS = Path(__file__).parents[3] / "db" / "functions"


class _MappingsResult:
	def __init__(self, rows: list[dict[str, object]]) -> None:
		self._rows = rows

	def mappings(self) -> "_MappingsResult":
		return self

	def all(self) -> list[dict[str, object]]:
		return self._rows

	def scalar_one(self) -> object:
		return self._rows[0]["count"]


@pytest.mark.asyncio
async def test_list_for_user_uses_count_function_when_requested_page_is_empty() -> None:
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
	sql = (DB_FUNCTIONS / f"{function_name}.sql").read_text()

	assert "GROUP BY task_id" in sql
	assert "comment_counts" in sql
	assert "LEFT JOIN comment_counts" in sql
	assert "SELECT count(*) FROM task_comments c WHERE c.task_id = t.id" not in sql
