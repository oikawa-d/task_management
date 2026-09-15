from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from app.api.routers import tasks_router as router_module
from app.api.routers.tasks_router import router
from app.core.deps import get_current_user
from app.core.exceptions import NotFoundError, register_error_handling
from app.db import get_db_session
from app.schemas.auth import CurrentUser
from app.schemas.task import TaskListMeta, TaskListResponse
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

USER_ID = uuid4()


def _current_user() -> CurrentUser:
	return CurrentUser(id=USER_ID, username="alice", role="member", is_active=True, email_verified_at=None)


def _build_app() -> FastAPI:
	app = FastAPI()
	register_error_handling(app)
	app.include_router(router)
	app.dependency_overrides[get_current_user] = _current_user
	app.dependency_overrides[get_db_session] = lambda: SimpleNamespace()
	return app


@pytest.fixture
def client() -> TestClient:
	app = _build_app()
	with TestClient(app) as test_client:
		yield test_client
	app.dependency_overrides.clear()


def test_task_router_registers_task_endpoints() -> None:
	routes = {
		(route.path, method) for route in router.routes if isinstance(route, APIRoute) for method in route.methods
	}

	assert ("/api/projects/{project_id}/tasks", "GET") in routes
	assert ("/api/projects/{project_id}/tasks", "POST") in routes
	assert ("/api/tasks", "GET") in routes
	assert ("/api/tasks/calendar", "GET") in routes
	assert ("/api/tasks", "POST") in routes
	assert ("/api/tasks/{task_id}", "GET") in routes
	assert ("/api/tasks/{task_id}", "PATCH") in routes
	assert ("/api/tasks/{task_id}", "DELETE") in routes


def test_list_tasks_forwards_default_query(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	expected = TaskListResponse(items=[], meta=TaskListMeta(page=1, per_page=20, total=0, total_pages=0))
	mock_list = AsyncMock(return_value=expected)
	monkeypatch.setattr(router_module.task_service, "list_tasks", mock_list)

	response = client.get("/api/tasks")

	assert response.status_code == 200
	assert response.json() == expected.model_dump(mode="json")
	assert mock_list.await_args.args[1:6] == (None, None, False, 1, 20)


def test_list_tasks_rejects_non_member_project(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	mock_list = AsyncMock(side_effect=NotFoundError())
	monkeypatch.setattr(router_module.task_service, "list_tasks", mock_list)
	project_id = uuid4()

	response = client.get("/api/tasks", params={"project_id": str(project_id), "per_page": 20})

	assert response.status_code == 404
	assert response.json()["error"]["code"] == "NOT_FOUND"
	assert mock_list.await_args.args[1] == UUID(str(project_id))


def test_list_tasks_normalizes_null_project_filter(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	mock_list = AsyncMock(
		return_value=TaskListResponse(items=[], meta=TaskListMeta(page=1, per_page=20, total=0, total_pages=0))
	)
	monkeypatch.setattr(router_module.task_service, "list_tasks", mock_list)

	response = client.get("/api/tasks", params={"project_id": "null", "per_page": 20})

	assert response.status_code == 200
	assert mock_list.await_args.args[1] == "unassigned"


def test_list_tasks_rejects_invalid_project_id(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	mock_list = AsyncMock()
	monkeypatch.setattr(router_module.task_service, "list_tasks", mock_list)

	response = client.get("/api/tasks", params={"project_id": "not-a-uuid"})

	assert response.status_code == 422
	assert response.json()["error"]["code"] == "VALIDATION_ERROR"
	mock_list.assert_not_awaited()


def test_list_tasks_forwards_status_filter(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	mock_list = AsyncMock(
		return_value=TaskListResponse(items=[], meta=TaskListMeta(page=1, per_page=20, total=0, total_pages=0))
	)
	monkeypatch.setattr(router_module.task_service, "list_tasks", mock_list)

	response = client.get("/api/tasks", params={"status": "done", "per_page": 20})

	assert response.status_code == 200
	assert mock_list.await_args.args[2] == "done"


def test_list_tasks_forwards_pagination(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	mock_list = AsyncMock(
		return_value=TaskListResponse(items=[], meta=TaskListMeta(page=2, per_page=5, total=0, total_pages=0))
	)
	monkeypatch.setattr(router_module.task_service, "list_tasks", mock_list)

	response = client.get("/api/tasks", params={"page": 2, "per_page": 5})

	assert response.status_code == 200
	assert mock_list.await_args.args[4:6] == (2, 5)
