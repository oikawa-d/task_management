"""app.api.routers.comment_router（タスクコメントCRUD）のルーティング定義に対する単体テスト。"""

from app.api.routers.comment_router import router


def test_comment_router_registers_crud_endpoints() -> None:
	"""comment_routerが、一覧取得(GET)・作成(POST) /api/tasks/{task_id}/comments と、
	更新(PATCH)・削除(DELETE) /api/comments/{comment_id} の4エンドポイントを
	すべて登録していることを検証する。
	"""
	routes = {(route.path, tuple(route.methods or ())) for route in router.routes}

	assert ("/api/tasks/{task_id}/comments", ("GET",)) in routes
	assert ("/api/tasks/{task_id}/comments", ("POST",)) in routes
	assert ("/api/comments/{comment_id}", ("PATCH",)) in routes
	assert ("/api/comments/{comment_id}", ("DELETE",)) in routes
