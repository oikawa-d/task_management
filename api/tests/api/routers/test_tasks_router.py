from app.api.routers.tasks_router import router
from fastapi.routing import APIRoute


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
