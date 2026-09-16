from app.api.routers.comment_router import router


def test_comment_router_registers_crud_endpoints() -> None:
	routes = {(route.path, tuple(route.methods or ())) for route in router.routes}

	assert ("/api/tasks/{task_id}/comments", ("GET",)) in routes
	assert ("/api/tasks/{task_id}/comments", ("POST",)) in routes
	assert ("/api/comments/{comment_id}", ("PATCH",)) in routes
	assert ("/api/comments/{comment_id}", ("DELETE",)) in routes
