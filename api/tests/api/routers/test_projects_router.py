from app.api.routers.projects_router import router
from fastapi.routing import APIRoute


def test_project_router_registers_crud_paths() -> None:
	routes = {
		(route.path, method) for route in router.routes if isinstance(route, APIRoute) for method in route.methods
	}

	assert ("/api/projects", "GET") in routes
	assert ("/api/projects", "POST") in routes
	assert ("/api/projects/{project_id}", "GET") in routes
	assert ("/api/projects/{project_id}", "PATCH") in routes
	assert ("/api/projects/{project_id}", "DELETE") in routes
	assert ("/api/projects/{project_id}/members", "GET") in routes
	assert ("/api/projects/{project_id}/members", "POST") in routes
	assert ("/api/projects/{project_id}/member-candidates", "GET") in routes
	assert ("/api/projects/{project_id}/members/{user_id}", "DELETE") in routes
