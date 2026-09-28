"""app.api.routers.projects_router（プロジェクトCRUD・メンバー管理）のルーティング定義に対する単体テスト。"""

from app.api.routers.projects_router import router
from fastapi.routing import APIRoute


def test_project_router_registers_crud_paths() -> None:
	"""projects_routerが、プロジェクトの一覧取得・作成・詳細取得・更新・削除、およびメンバーの
	一覧取得・追加・削除・候補一覧取得の各エンドポイントをすべて登録していることを検証する。
	"""
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
