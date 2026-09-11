from app.api.routers.users_router import router
from fastapi.routing import APIRoute


def test_users_router_registers_users_me_endpoints() -> None:
	routes = {
		(route.path, method) for route in router.routes if isinstance(route, APIRoute) for method in route.methods
	}

	assert ("/api/users/me", "GET") in routes
	assert ("/api/users/me", "PATCH") in routes
	assert ("/api/users/me/password", "PUT") in routes
	assert ("/api/users/me/login-history", "GET") in routes


def test_change_my_password_route_returns_no_content_status() -> None:
	password_routes = [
		route for route in router.routes if isinstance(route, APIRoute) and route.path == "/api/users/me/password"
	]

	assert password_routes[0].status_code == 204
