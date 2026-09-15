from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.repository import task_repository
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from tests.integration_tasks.conftest import TaskScenario, write_headers


def _items(response) -> list[dict[str, object]]:
	return response.json()["items"]


async def test_task_crud_updates_position_and_rejects_stale_version(
	client: TestClient, scenario: TaskScenario, authenticate
) -> None:
	auth_headers = authenticate()

	created = []
	for title in ("created-first", "created-second"):
		response = client.post(
			f"/api/projects/{scenario.member_project_id}/tasks",
			json={"title": title, "status": "todo"},
			headers=write_headers(client, auth_headers),
		)
		assert response.status_code == 201, response.text
		created.append(response.json())

	first = client.get(f"/api/tasks/{created[0]['id']}", headers=auth_headers)
	assert first.status_code == 200
	assert first.json()["project_id"] == str(scenario.member_project_id)

	moved = client.patch(
		f"/api/tasks/{created[0]['id']}",
		json={"version": first.json()["version"], "position": 2},
		headers=write_headers(client, auth_headers),
	)
	assert moved.status_code == 200, moved.text
	assert moved.json()["position"] == 2

	conflict = client.patch(
		f"/api/tasks/{created[0]['id']}",
		json={"version": first.json()["version"], "title": "stale"},
		headers=write_headers(client, auth_headers),
	)
	assert conflict.status_code == 409, conflict.text
	assert conflict.json()["error"]["code"] == "TASK_CONFLICT"

	deleted = client.delete(
		f"/api/tasks/{created[1]['id']}",
		headers=write_headers(client, auth_headers),
	)
	assert deleted.status_code == 204
	assert client.get(f"/api/tasks/{created[1]['id']}", headers=auth_headers).status_code == 404

	board = client.get(f"/api/projects/{scenario.member_project_id}/tasks", headers=auth_headers)
	assert board.status_code == 200
	assert [item["id"] for item in board.json()["columns"]["todo"]] == [
		str(scenario.member_project_task_id),
		str(created[0]["id"]),
	]


async def test_list_tasks_member_scope_includes_shared_and_own_unassigned_only(
	client: TestClient, scenario: TaskScenario, authenticate
) -> None:
	response = client.get("/api/tasks", params={"per_page": 20}, headers=authenticate())

	assert response.status_code == 200, response.text
	project_ids = {item["project_id"] for item in _items(response)}
	ids = {item["id"] for item in _items(response)}
	assert project_ids >= {str(scenario.member_project_id), str(scenario.shared_project_id), None}
	assert str(scenario.member_project_task_id) in ids
	assert str(scenario.shared_project_task_id) in ids
	assert str(scenario.own_unassigned_task_id) in ids
	assert str(scenario.outsider_unassigned_task_id) not in ids


async def test_list_tasks_unassigned_filter_and_project_membership_boundary(
	client: TestClient, scenario: TaskScenario, authenticate
) -> None:
	auth_headers = authenticate()

	unassigned = client.get("/api/tasks", params={"project_id": "null", "per_page": 20}, headers=auth_headers)
	assert unassigned.status_code == 200, unassigned.text
	assert {item["id"] for item in _items(unassigned)} == {str(scenario.own_unassigned_task_id)}

	private = client.get(
		"/api/tasks", params={"project_id": str(scenario.private_project_id), "per_page": 20}, headers=auth_headers
	)
	assert private.status_code == 404, private.text
	assert private.json()["error"]["code"] == "NOT_FOUND"


async def test_list_tasks_excludes_inactive_by_default_and_can_include_it(
	client: TestClient, scenario: TaskScenario, authenticate, db_session: AsyncSession
) -> None:
	await task_repository.set_active(db_session, scenario.member_project_task_id, False)
	await db_session.commit()
	auth_headers = authenticate()

	default = client.get("/api/tasks", params={"per_page": 20}, headers=auth_headers)
	assert default.status_code == 200
	assert str(scenario.member_project_task_id) not in {item["id"] for item in _items(default)}

	included = client.get("/api/tasks", params={"per_page": 20, "include_inactive": "true"}, headers=auth_headers)
	assert included.status_code == 200
	found = [item for item in _items(included) if item["id"] == str(scenario.member_project_task_id)]
	assert len(found) == 1 and found[0]["is_active"] is False


def test_list_tasks_requires_authentication(client: TestClient) -> None:
	response = client.get("/api/tasks")

	assert response.status_code == 401
	assert response.json()["error"]["code"] == "UNAUTHENTICATED"


@pytest.mark.parametrize("invalid_project_id", ["not-a-uuid", "unassigned"])
def test_list_tasks_rejects_invalid_project_filter(client: TestClient, authenticate, invalid_project_id: str) -> None:
	response = client.get(
		"/api/tasks", params={"project_id": invalid_project_id, "per_page": 20}, headers=authenticate()
	)

	assert response.status_code == 422


def test_list_tasks_returns_503_when_database_is_unavailable(
	client: TestClient, scenario: TaskScenario, authenticate, monkeypatch: pytest.MonkeyPatch
) -> None:
	database_error = OperationalError("SELECT fn_list_tasks", {}, SimpleNamespace(sqlstate="08006"))
	monkeypatch.setattr(task_repository, "list_for_user", AsyncMock(side_effect=database_error))

	response = client.get("/api/tasks", params={"per_page": 20}, headers=authenticate())

	assert response.status_code == 503
	assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
