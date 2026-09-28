"""app.api.routers.admin_router（管理者向けユーザー/プロジェクト/ログイン履歴API）の
ルーティング定義・依存関係配線・各エンドポイント関数がservice層へ引数を委譲する挙動に対する単体テスト。
DB接続はAsyncMock(spec=AsyncSession)で模擬し、実DBには接続しない。
"""

from datetime import datetime, timezone
from inspect import signature
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.api.routers import admin_router
from app.core.deps import require_admin, verify_csrf, verify_origin
from app.schemas.admin import (
	AdminLoginHistoryListResponse,
	AdminLoginHistoryQuery,
	AdminProjectListQuery,
	AdminProjectListResponse,
	AdminUserDetailResponse,
	AdminUserListQuery,
	AdminUserListResponse,
	AdminUserRoleUpdateRequest,
	AdminUserStatusUpdateRequest,
)
from app.schemas.auth import CurrentUser
from fastapi import Request, Response
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession


def _current_admin() -> CurrentUser:
	"""adminロールを持つ検証用CurrentUser（操作者/actor）を作る。"""
	return CurrentUser(id=uuid4(), username="admin", role="admin", is_active=True, email_verified_at=None)


def _request(request_id: str = "request-123") -> Request:
	"""request.state.request_idを設定した検証用のASGIリクエストを組み立てる。

	Args:
		request_id: request.state.request_idに設定する監査ログ用の相関ID。

	Returns:
		指定したrequest_idを持つRequestインスタンス。
	"""
	request = Request({"type": "http", "method": "PATCH", "path": "/"})
	request.state.request_id = request_id
	return request


def _user_detail() -> AdminUserDetailResponse:
	"""admin_user_serviceの戻り値を模擬する、検証用のAdminUserDetailResponseを作る。"""
	now = datetime.now(timezone.utc)
	return AdminUserDetailResponse(
		id=uuid4(),
		username="target",
		email="target@example.com",
		display_name="Target User",
		role="member",
		is_active=True,
		email_verified_at=None,
		created_at=now,
		updated_at=now,
	)


def _routes() -> dict[tuple[str, str], APIRoute]:
	"""admin_router配下の全APIRouteを(パス, HTTPメソッド)をキーにした辞書へまとめる。

	Returns:
		(path, method)をキー、APIRouteを値とする辞書。
	"""
	return {
		(route.path, method): route
		for route in admin_router.router.routes
		if isinstance(route, APIRoute)
		for method in route.methods
	}


def test_admin_router_registers_contracts() -> None:
	"""admin_routerが登録する7エンドポイント（ユーザー一覧・ロール変更・状態変更・強制ログアウト・
	プロジェクト一覧・プロジェクト無効化・ログイン履歴一覧）それぞれについて、期待するパス・
	HTTPメソッド・response_model・status_codeの組み合わせと過不足なく一致することを検証する。
	"""
	routes = _routes()
	expected = {
		("/api/admin/users", "GET"): (AdminUserListResponse, None),
		("/api/admin/users/{user_id}/role", "PATCH"): (AdminUserDetailResponse, None),
		("/api/admin/users/{user_id}/status", "PATCH"): (AdminUserDetailResponse, None),
		("/api/admin/users/{user_id}/force-logout", "POST"): (None, 204),
		("/api/admin/projects", "GET"): (AdminProjectListResponse, None),
		("/api/admin/projects/{project_id}", "DELETE"): (None, 204),
		("/api/admin/login-history", "GET"): (AdminLoginHistoryListResponse, None),
	}

	assert set(expected) == set(routes)
	for route_key, (response_model, status_code) in expected.items():
		route = routes[route_key]
		assert route.response_model is response_model
		assert route.status_code == status_code


def test_admin_router_applies_admin_and_csrf_dependencies() -> None:
	"""admin_router配下の全エンドポイントがrequire_admin依存を持つこと、
	状態変更を伴うメソッド（PATCH/POST/DELETE）にはverify_origin・verify_csrfも
	配線されている一方、それ以外（GET）には配線されていないことを検証する。
	"""
	for route in admin_router.router.routes:
		if not isinstance(route, APIRoute):
			continue
		dependencies = {dependency.call for dependency in route.dependant.dependencies}
		assert require_admin in dependencies
		if route.methods & {"PATCH", "POST", "DELETE"}:
			assert verify_origin in dependencies
			assert verify_csrf in dependencies
		else:
			assert verify_origin not in dependencies
			assert verify_csrf not in dependencies


def test_main_registers_admin_router() -> None:
	"""app.mainの実アプリのOpenAPIスキーマに、admin_routerの代表的なパスが登録されていることを検証する
	（admin_routerがinclude_routerされていることの確認）。
	"""
	from app.main import app

	routes = set(app.openapi()["paths"])

	assert "/api/admin/users" in routes
	assert "/api/admin/projects/{project_id}" in routes
	assert "/api/admin/login-history" in routes


@pytest.mark.asyncio
async def test_list_admin_users_forwards_query_and_db(monkeypatch: pytest.MonkeyPatch) -> None:
	"""list_admin_usersが、受け取ったquery・dbをそのままadmin_user_service.list_usersへ渡し、
	戻り値をそのまま返すことを検証する。
	"""
	query = AdminUserListQuery(page=3, per_page=7, q="taro", role="admin", is_active=False)
	db = AsyncMock(spec=AsyncSession)
	service = AsyncMock(
		return_value=AdminUserListResponse(items=[], meta={"page": 3, "per_page": 7, "total": 0, "total_pages": 0})
	)
	monkeypatch.setattr(admin_router.admin_user_service, "list_users", service)

	result = await admin_router.list_admin_users(query=query, user=_current_admin(), db=db)

	assert result is service.return_value
	service.assert_awaited_once_with(query, db)


@pytest.mark.asyncio
async def test_patch_admin_user_role_forwards_path_payload_actor_and_db(monkeypatch: pytest.MonkeyPatch) -> None:
	"""patch_admin_user_roleが、パスパラメータのuser_id・リクエストボディのrole・操作者(actor)・db、
	および監査ログ用のrequest_idをadmin_user_service.change_roleへ正しく渡し、戻り値をそのまま返すことを検証する。
	"""
	user_id = uuid4()
	actor = _current_admin()
	db = AsyncMock(spec=AsyncSession)
	service = AsyncMock(return_value=_user_detail())
	monkeypatch.setattr(admin_router.admin_user_service, "change_role", service)

	result = await admin_router.patch_admin_user_role(
		user_id=user_id, payload=AdminUserRoleUpdateRequest(role="member"), request=_request(), actor=actor, db=db
	)

	assert result is service.return_value
	service.assert_awaited_once_with(actor, user_id, "member", db, request_id="request-123")


@pytest.mark.asyncio
async def test_patch_admin_user_status_forwards_path_payload_actor_and_db(monkeypatch: pytest.MonkeyPatch) -> None:
	"""patch_admin_user_statusが、パスパラメータのuser_id・リクエストボディのis_active・操作者(actor)・db、
	および監査ログ用のrequest_idをadmin_user_service.change_statusへ正しく渡し、戻り値をそのまま返すことを検証する。
	"""
	user_id = uuid4()
	actor = _current_admin()
	db = AsyncMock(spec=AsyncSession)
	service = AsyncMock(return_value=_user_detail())
	monkeypatch.setattr(admin_router.admin_user_service, "change_status", service)

	result = await admin_router.patch_admin_user_status(
		user_id=user_id, payload=AdminUserStatusUpdateRequest(is_active=False), request=_request(), actor=actor, db=db
	)

	assert result is service.return_value
	service.assert_awaited_once_with(actor, user_id, False, db, request_id="request-123")


@pytest.mark.asyncio
async def test_post_admin_user_force_logout_returns_no_content(monkeypatch: pytest.MonkeyPatch) -> None:
	"""post_admin_user_force_logoutが、user_id・actor・db・request_idをadmin_user_service.force_logoutへ
	渡したうえで、ステータス204・空ボディのResponseを返すことを検証する。
	"""
	user_id = uuid4()
	actor = _current_admin()
	db = AsyncMock(spec=AsyncSession)
	service = AsyncMock()
	monkeypatch.setattr(admin_router.admin_user_service, "force_logout", service)

	result = await admin_router.post_admin_user_force_logout(user_id=user_id, request=_request(), actor=actor, db=db)

	assert isinstance(result, Response)
	assert result.status_code == 204
	assert result.body == b""
	service.assert_awaited_once_with(actor, user_id, db, request_id="request-123")


@pytest.mark.asyncio
async def test_list_admin_projects_forwards_query_and_db(monkeypatch: pytest.MonkeyPatch) -> None:
	"""list_admin_projectsが、受け取ったquery・dbをそのままadmin_project_service.list_projectsへ渡し、
	戻り値をそのまま返すことを検証する。
	"""
	query = AdminProjectListQuery(page=2, per_page=5, q="cerberus")
	db = AsyncMock(spec=AsyncSession)
	service = AsyncMock(
		return_value=AdminProjectListResponse(items=[], meta={"page": 2, "per_page": 5, "total": 0, "total_pages": 0})
	)
	monkeypatch.setattr(admin_router.admin_project_service, "list_projects", service)

	result = await admin_router.list_admin_projects(query=query, user=_current_admin(), db=db)

	assert result is service.return_value
	service.assert_awaited_once_with(query, db)


@pytest.mark.asyncio
async def test_delete_admin_project_returns_no_content(monkeypatch: pytest.MonkeyPatch) -> None:
	"""delete_admin_projectが、project_id・actor・db・request_idをadmin_project_service.deactivate_projectへ
	渡したうえで、ステータス204・空ボディのResponseを返すことを検証する。
	"""
	project_id = uuid4()
	actor = _current_admin()
	db = AsyncMock(spec=AsyncSession)
	service = AsyncMock()
	monkeypatch.setattr(admin_router.admin_project_service, "deactivate_project", service)

	result = await admin_router.delete_admin_project(project_id=project_id, request=_request(), actor=actor, db=db)

	assert isinstance(result, Response)
	assert result.status_code == 204
	assert result.body == b""
	service.assert_awaited_once_with(actor, project_id, db, request_id="request-123")


@pytest.mark.asyncio
async def test_list_admin_login_history_forwards_all_paging_filters(monkeypatch: pytest.MonkeyPatch) -> None:
	"""list_admin_login_historyが、ページング・検索語・ログイン方式・成否・作成日時範囲を含む
	全フィルタ条件のqueryをそのままadmin_login_history_service.searchへ渡し、戻り値をそのまま返すことを検証する。
	"""
	query = AdminLoginHistoryQuery(
		page=4,
		per_page=6,
		user_id=uuid4(),
		q="login",
		login_method="jwt",
		success=False,
		**{"from": "2026-01-01T00:00:00Z", "to": "2026-01-02T00:00:00Z"},
	)
	db = AsyncMock(spec=AsyncSession)
	service = AsyncMock(
		return_value=AdminLoginHistoryListResponse(
			items=[], meta={"page": 4, "per_page": 6, "total": 0, "total_pages": 0}
		)
	)
	monkeypatch.setattr(admin_router.admin_login_history_service, "search", service)

	result = await admin_router.list_admin_login_history(query=query, user=_current_admin(), db=db)

	assert result is service.return_value
	service.assert_awaited_once_with(query, db)


def test_router_signatures_keep_query_and_path_parameters() -> None:
	"""admin_router内の各エンドポイント関数のシグネチャが、期待するパラメータ名の集合
	（パスパラメータ・query・request・actor・CSRF/Origin検証用のプレースホルダー引数・db）から
	過不足なく一致していることを検証する（依存関係配線の意図しない変更を検知する）。
	"""
	for function_name, parameter_names in {
		"list_admin_users": {"query", "user", "db"},
		"patch_admin_user_role": {"user_id", "payload", "request", "actor", "_", "__csrf", "db"},
		"patch_admin_user_status": {"user_id", "payload", "request", "actor", "_", "__csrf", "db"},
		"post_admin_user_force_logout": {"user_id", "request", "actor", "_", "__csrf", "db"},
		"list_admin_projects": {"query", "user", "db"},
		"delete_admin_project": {"project_id", "request", "actor", "_", "__csrf", "db"},
		"list_admin_login_history": {"query", "user", "db"},
	}.items():
		assert set(signature(getattr(admin_router, function_name)).parameters) == parameter_names
