"""users_router の結合テスト。

service層(user_service, #113でテスト済み)はモックし、router層の責務
(認証・CSRF/Origin検証の配線とservice呼び出しへの委譲、エラーのHTTPステータスへの
マッピング)のみを検証する。設計書のテスト表(01〜04)の結合テストケースに対応する。

08_login_history §12 No.9「他ユーザーの履歴が混入しないこと」はservice層
(login_history_repository経由でuser_id条件を必ず付与)の責務であり、
tests/service/test_user_service.py側でカバー済みのためここでは扱わない。
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.api.routers import users_router as router_module
from app.auth.factory import get_auth_strategy
from app.core import deps
from app.core.deps import get_current_user
from app.core.exceptions import (
	InvalidCredentialsError,
	UnauthenticatedError,
	UserInactiveError,
	ValidationError,
	register_error_handling,
)
from app.db import get_db_session
from app.schemas.auth import CurrentUser
from app.schemas.user import LoginHistoryListResponse, LoginHistoryMeta, UserProfileResponse
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

ALLOWED_ORIGIN = "http://localhost:5173"
USER_ID = uuid4()


def _current_user() -> CurrentUser:
	"""get_current_userの差し替え先。固定のUSER_IDを持つ検証用CurrentUserを返す。"""
	return CurrentUser(id=USER_ID, username="taro", role="member", is_active=True, email_verified_at=None)


def _profile_response(**overrides: object) -> UserProfileResponse:
	"""user_service.get_profile/update_profileの戻り値を模擬する、検証用のUserProfileResponseを作る。

	Args:
		**overrides: 既定値を上書きしたいフィールド（例: last_name・profile_completed）。

	Returns:
		既定値にoverridesを反映したUserProfileResponse。
	"""
	defaults: dict[str, object] = {
		"id": USER_ID,
		"username": "taro",
		"email": "taro@example.com",
		"last_name": "山田",
		"first_name": "太郎",
		"last_name_kana": "ヤマダ",
		"first_name_kana": "タロウ",
		"birth_date": date(1995, 4, 1),
		"profile_completed": True,
		"role": "member",
		"has_password": True,
		"oauth_providers": ["google"],
	}
	defaults.update(overrides)
	return UserProfileResponse.model_validate(defaults)


def _build_app() -> FastAPI:
	"""users_routerのみを組み込み、認証とDBセッションをダミーに差し替えたFastAPIアプリを組み立てる。

	Returns:
		get_current_user・get_db_sessionの依存関係をオーバーライド済みのFastAPIアプリ
		（get_auth_strategyのオーバーライドは呼び出し側で設定する）。
	"""
	app = FastAPI()
	register_error_handling(app)
	app.include_router(router_module.router)
	app.dependency_overrides[get_current_user] = _current_user
	app.dependency_overrides[get_db_session] = lambda: None
	return app


def _app_with_mode(mode: str) -> FastAPI:
	"""_build_appのアプリへ、指定した認証モードのget_auth_strategyオーバーライドを追加する。

	Args:
		mode: "session"または"jwt"。

	Returns:
		指定モードで固定したFastAPIアプリ。
	"""
	app = _build_app()
	app.dependency_overrides[get_auth_strategy] = lambda: SimpleNamespace(mode=mode)
	return app


@pytest.fixture
def app_and_mocks() -> FastAPI:
	"""jwtモードに固定した_build_appのアプリを提供する。後片付けとしてdependency_overridesをクリアする。"""
	app = _app_with_mode("jwt")
	yield app
	app.dependency_overrides.clear()


@pytest.fixture
def client(app_and_mocks: FastAPI) -> TestClient:
	"""app_and_mocksのアプリを起動するTestClientを提供する。後片付けは行わない（app_and_mocks側で行う）。"""
	with TestClient(app_and_mocks) as test_client:
		yield test_client


def _unauthenticated_client(app: FastAPI) -> TestClient:
	"""get_current_userを常にUnauthenticatedErrorを送出するよう差し替えたTestClientを返す。

	Args:
		app: オーバーライドを追加する対象のFastAPIアプリ。

	Returns:
		未認証状態を模擬するTestClient。
	"""

	def _raise() -> CurrentUser:
		"""get_current_userの差し替え先。常にUnauthenticatedErrorを送出する。"""
		raise UnauthenticatedError()

	app.dependency_overrides[get_current_user] = _raise
	return TestClient(app)


def _inactive_user_client(app: FastAPI) -> TestClient:
	"""get_current_userを常にUserInactiveErrorを送出するよう差し替えたTestClientを返す。

	Args:
		app: オーバーライドを追加する対象のFastAPIアプリ。

	Returns:
		非アクティブユーザーによるアクセスを模擬するTestClient。
	"""

	def _raise() -> CurrentUser:
		"""get_current_userの差し替え先。常にUserInactiveErrorを送出する。"""
		raise UserInactiveError()

	app.dependency_overrides[get_current_user] = _raise
	return TestClient(app)


def test_users_router_registers_users_me_endpoints() -> None:
	"""users_routerが、プロフィール取得(GET)・更新(PATCH)、パスワード変更(PUT)、
	ログイン履歴取得(GET)の4エンドポイントをすべて登録していることを検証する。
	"""
	routes = {
		(route.path, method)
		for route in router_module.router.routes
		if isinstance(route, APIRoute)
		for method in route.methods
	}

	assert ("/api/users/me", "GET") in routes
	assert ("/api/users/me", "PATCH") in routes
	assert ("/api/users/me/password", "PUT") in routes
	assert ("/api/users/me/login-history", "GET") in routes


def test_change_my_password_route_returns_no_content_status() -> None:
	"""PUT /api/users/me/password のルート定義がstatus_code=204（本文無し）であることを検証する。"""
	password_routes = [
		route
		for route in router_module.router.routes
		if isinstance(route, APIRoute) and route.path == "/api/users/me/password"
	]

	assert password_routes[0].status_code == 204


# --- GET /api/users/me ------------------------------------------------------


def test_get_my_profile_session_mode_success(monkeypatch: pytest.MonkeyPatch) -> None:
	"""sessionモードでGET /api/users/me を呼ぶと、認証済みユーザーでservice層を呼び出し、
	200でプロフィールを返し、レスポンスにCache-Control: no-storeが設定されることを検証する。
	"""
	app = _app_with_mode("session")
	expected = _profile_response()
	mock_get_profile = AsyncMock(return_value=expected)
	monkeypatch.setattr(router_module.user_service, "get_profile", mock_get_profile)

	with TestClient(app) as client:
		res = client.get("/api/users/me")

	assert res.status_code == 200
	assert res.json() == expected.model_dump(mode="json")
	assert res.headers["Cache-Control"] == "no-store"
	called_user, _ = mock_get_profile.call_args.args
	assert called_user.id == USER_ID
	app.dependency_overrides.clear()


def test_get_my_profile_jwt_mode_success(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	"""jwtモードでGET /api/users/me を呼ぶと、200でservice層の結果をそのまま返すことを検証する。"""
	expected = _profile_response()
	monkeypatch.setattr(router_module.user_service, "get_profile", AsyncMock(return_value=expected))

	res = client.get("/api/users/me")

	assert res.status_code == 200
	assert res.json() == expected.model_dump(mode="json")


def test_get_my_profile_unauthenticated_returns_401(app_and_mocks: FastAPI) -> None:
	"""未認証状態でGET /api/users/me を呼ぶと、ステータス401・エラーコードUNAUTHENTICATEDで応答することを検証する。"""
	with _unauthenticated_client(app_and_mocks) as client:
		res = client.get("/api/users/me")

	assert res.status_code == 401
	assert res.json()["error"]["code"] == "UNAUTHENTICATED"


def test_get_my_profile_inactive_user_returns_403(app_and_mocks: FastAPI) -> None:
	"""非アクティブユーザーでGET /api/users/me を呼ぶと、ステータス403・エラーコードUSER_INACTIVEで
	応答することを検証する。
	"""
	with _inactive_user_client(app_and_mocks) as client:
		res = client.get("/api/users/me")

	assert res.status_code == 403
	assert res.json()["error"]["code"] == "USER_INACTIVE"


def test_get_my_profile_oauth_incomplete_profile_returns_false(
	client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
	"""OAuth連携のみでプロフィール未入力（氏名等がNone・パスワード未設定）のユーザーの場合、
	200で応答しつつprofile_completedがFalseで返ることを検証する。
	"""
	expected = _profile_response(
		last_name=None,
		first_name=None,
		last_name_kana=None,
		first_name_kana=None,
		birth_date=None,
		profile_completed=False,
		has_password=False,
	)
	monkeypatch.setattr(router_module.user_service, "get_profile", AsyncMock(return_value=expected))

	res = client.get("/api/users/me")

	assert res.status_code == 200
	assert res.json()["profile_completed"] is False


# --- PATCH /api/users/me -----------------------------------------------------


def test_patch_my_profile_session_mode_success(monkeypatch: pytest.MonkeyPatch) -> None:
	"""sessionモードで有効なOrigin・CSRFトークンを付与してPATCH /api/users/me を呼ぶと、
	200で更新後のプロフィールを返し、レスポンスにCache-Control: no-storeが設定されることを検証する。
	"""
	app = _app_with_mode("session")
	monkeypatch.setattr(deps.redis_store, "get_csrf_token", AsyncMock(return_value="token-abc"))
	expected = _profile_response(last_name="鈴木")
	mock_update = AsyncMock(return_value=expected)
	monkeypatch.setattr(router_module.user_service, "update_profile", mock_update)

	with TestClient(app) as client:
		client.cookies.set("cerberus_sid", "sid-1")
		res = client.patch(
			"/api/users/me",
			json={"last_name": "鈴木"},
			headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": "token-abc"},
		)

	assert res.status_code == 200
	assert res.json()["last_name"] == "鈴木"
	assert res.headers["Cache-Control"] == "no-store"
	app.dependency_overrides.clear()


def test_patch_my_profile_jwt_mode_success(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	"""jwtモードではCSRFトークン無しでPATCH /api/users/me を呼んでも200で更新後のプロフィールが
	返ることを検証する。
	"""
	expected = _profile_response(last_name="鈴木")
	monkeypatch.setattr(router_module.user_service, "update_profile", AsyncMock(return_value=expected))

	res = client.patch("/api/users/me", json={"last_name": "鈴木"}, headers={"Origin": ALLOWED_ORIGIN})

	assert res.status_code == 200
	assert res.json()["last_name"] == "鈴木"


def test_patch_my_profile_csrf_missing_session_returns_403(monkeypatch: pytest.MonkeyPatch) -> None:
	"""sessionモードでX-CSRF-Tokenヘッダーが無い場合、service層を呼び出す前にステータス403・
	エラーコードCSRF_INVALIDで拒否することを検証する。
	"""
	app = _app_with_mode("session")
	mock_update = AsyncMock()
	monkeypatch.setattr(router_module.user_service, "update_profile", mock_update)

	with TestClient(app) as client:
		client.cookies.set("cerberus_sid", "sid-1")
		res = client.patch("/api/users/me", json={"last_name": "鈴木"}, headers={"Origin": ALLOWED_ORIGIN})

	assert res.status_code == 403
	assert res.json()["error"]["code"] == "CSRF_INVALID"
	mock_update.assert_not_called()
	app.dependency_overrides.clear()


def test_patch_my_profile_unauthenticated_returns_401(app_and_mocks: FastAPI) -> None:
	"""未認証状態でPATCH /api/users/me を呼ぶと、ステータス401・エラーコードUNAUTHENTICATEDで応答することを検証する。"""
	with _unauthenticated_client(app_and_mocks) as client:
		res = client.patch("/api/users/me", json={"last_name": "鈴木"}, headers={"Origin": ALLOWED_ORIGIN})

	assert res.status_code == 401
	assert res.json()["error"]["code"] == "UNAUTHENTICATED"


def test_patch_my_profile_inactive_user_returns_403(app_and_mocks: FastAPI) -> None:
	"""非アクティブユーザーでPATCH /api/users/me を呼ぶと、ステータス403・エラーコードUSER_INACTIVEで
	応答することを検証する。
	"""
	with _inactive_user_client(app_and_mocks) as client:
		res = client.patch("/api/users/me", json={"last_name": "鈴木"}, headers={"Origin": ALLOWED_ORIGIN})

	assert res.status_code == 403
	assert res.json()["error"]["code"] == "USER_INACTIVE"


def test_patch_my_profile_invalid_kana_returns_422(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	"""last_name_kanaにカタカナ以外の文字列（漢字）を送信した場合、service層を呼び出す前に
	ステータス422・エラーコードVALIDATION_ERRORで拒否することを検証する。
	"""
	mock_update = AsyncMock()
	monkeypatch.setattr(router_module.user_service, "update_profile", mock_update)

	res = client.patch("/api/users/me", json={"last_name_kana": "山田"}, headers={"Origin": ALLOWED_ORIGIN})

	assert res.status_code == 422
	assert res.json()["error"]["code"] == "VALIDATION_ERROR"
	mock_update.assert_not_called()


def test_patch_my_profile_null_rejected_by_service_returns_422(
	client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
	"""送信済みフィールドのnull化不可(service層判定)がrouterで422として返ること。"""
	monkeypatch.setattr(
		router_module.user_service,
		"update_profile",
		AsyncMock(side_effect=ValidationError(details=[{"field": "last_name", "message": "null is not allowed"}])),
	)

	res = client.patch("/api/users/me", json={"last_name": "鈴木"}, headers={"Origin": ALLOWED_ORIGIN})

	assert res.status_code == 422
	assert res.json()["error"]["code"] == "VALIDATION_ERROR"


# --- PUT /api/users/me/password ----------------------------------------------


def _password_payload(**overrides: object) -> dict[str, object]:
	"""PUT /api/users/me/password へ送信するリクエストボディを作る。

	Args:
		**overrides: 既定値を上書きしたいフィールド（例: current_password・new_password）。

	Returns:
		既定値にoverridesを反映したリクエストボディの辞書。
	"""
	payload: dict[str, object] = {
		"current_password": "OldPass1!",
		"new_password": "NewPass1!",
		"password_confirm": "NewPass1!",
	}
	payload.update(overrides)
	return payload


def test_change_my_password_session_mode_success(monkeypatch: pytest.MonkeyPatch) -> None:
	"""sessionモードで有効なOrigin・CSRFトークンを付与してPUT /api/users/me/password を呼ぶと、
	service層のchange_passwordが1回呼ばれ、ステータス204で応答することを検証する。
	"""
	app = _app_with_mode("session")
	monkeypatch.setattr(deps.redis_store, "get_csrf_token", AsyncMock(return_value="token-abc"))
	mock_change = AsyncMock(return_value=None)
	monkeypatch.setattr(router_module.user_service, "change_password", mock_change)

	with TestClient(app) as client:
		client.cookies.set("cerberus_sid", "sid-1")
		res = client.put(
			"/api/users/me/password",
			json=_password_payload(),
			headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": "token-abc"},
		)

	assert res.status_code == 204
	mock_change.assert_awaited_once()
	app.dependency_overrides.clear()


def test_change_my_password_jwt_mode_success(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	"""jwtモードではCSRFトークン無しでPUT /api/users/me/password を呼んでもステータス204で応答することを検証する。"""
	monkeypatch.setattr(router_module.user_service, "change_password", AsyncMock(return_value=None))

	res = client.put("/api/users/me/password", json=_password_payload(), headers={"Origin": ALLOWED_ORIGIN})

	assert res.status_code == 204


def test_change_my_password_csrf_missing_session_returns_403(monkeypatch: pytest.MonkeyPatch) -> None:
	"""sessionモードでX-CSRF-Tokenヘッダーが無い場合、service層を呼び出す前にステータス403・
	エラーコードCSRF_INVALIDで拒否することを検証する。
	"""
	app = _app_with_mode("session")
	mock_change = AsyncMock()
	monkeypatch.setattr(router_module.user_service, "change_password", mock_change)

	with TestClient(app) as client:
		client.cookies.set("cerberus_sid", "sid-1")
		res = client.put("/api/users/me/password", json=_password_payload(), headers={"Origin": ALLOWED_ORIGIN})

	assert res.status_code == 403
	assert res.json()["error"]["code"] == "CSRF_INVALID"
	mock_change.assert_not_called()
	app.dependency_overrides.clear()


def test_change_my_password_unauthenticated_returns_401(app_and_mocks: FastAPI) -> None:
	"""未認証状態でPUT /api/users/me/password を呼ぶと、ステータス401・エラーコードUNAUTHENTICATEDで
	応答することを検証する。
	"""
	with _unauthenticated_client(app_and_mocks) as client:
		res = client.put("/api/users/me/password", json=_password_payload(), headers={"Origin": ALLOWED_ORIGIN})

	assert res.status_code == 401
	assert res.json()["error"]["code"] == "UNAUTHENTICATED"


def test_change_my_password_inactive_user_returns_403(app_and_mocks: FastAPI) -> None:
	"""非アクティブユーザーでPUT /api/users/me/password を呼ぶと、ステータス403・エラーコードUSER_INACTIVEで
	応答することを検証する。
	"""
	with _inactive_user_client(app_and_mocks) as client:
		res = client.put("/api/users/me/password", json=_password_payload(), headers={"Origin": ALLOWED_ORIGIN})

	assert res.status_code == 403
	assert res.json()["error"]["code"] == "USER_INACTIVE"


def test_change_my_password_policy_violation_returns_422(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	"""パスワードポリシーを満たさない新パスワード（例: "weak"）を送信した場合、service層を
	呼び出す前にステータス422・エラーコードVALIDATION_ERRORで拒否することを検証する。
	"""
	mock_change = AsyncMock()
	monkeypatch.setattr(router_module.user_service, "change_password", mock_change)

	res = client.put(
		"/api/users/me/password",
		json=_password_payload(new_password="weak", password_confirm="weak"),
		headers={"Origin": ALLOWED_ORIGIN},
	)

	assert res.status_code == 422
	assert res.json()["error"]["code"] == "VALIDATION_ERROR"
	mock_change.assert_not_called()


def test_change_my_password_wrong_current_password_returns_401(
	client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
	"""service層のchange_passwordがInvalidCredentialsErrorを送出した場合（現在のパスワードが誤り）、
	ステータス401・エラーコードINVALID_CREDENTIALSで応答することを検証する。
	"""
	monkeypatch.setattr(
		router_module.user_service,
		"change_password",
		AsyncMock(side_effect=InvalidCredentialsError(message="現在のパスワードが正しくありません")),
	)

	res = client.put("/api/users/me/password", json=_password_payload(), headers={"Origin": ALLOWED_ORIGIN})

	assert res.status_code == 401
	assert res.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_change_my_password_missing_current_password_returns_422(
	client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
	"""has_password=trueなのにcurrent_password未送信(service層判定)が422として返ること。"""
	monkeypatch.setattr(
		router_module.user_service,
		"change_password",
		AsyncMock(side_effect=ValidationError(details=[{"field": "current_password", "message": "required"}])),
	)

	res = client.put(
		"/api/users/me/password",
		json=_password_payload(current_password=None),
		headers={"Origin": ALLOWED_ORIGIN},
	)

	assert res.status_code == 422
	assert res.json()["error"]["code"] == "VALIDATION_ERROR"


# --- GET /api/users/me/login-history -----------------------------------------


def test_get_my_login_history_session_mode_success(monkeypatch: pytest.MonkeyPatch) -> None:
	"""sessionモードでGET /api/users/me/login-history を呼ぶと、200でservice層の結果を返し、
	レスポンスにCache-Control: no-storeが設定されることを検証する。
	"""
	app = _app_with_mode("session")
	expected = LoginHistoryListResponse(items=[], meta=LoginHistoryMeta(limit=50, count=0))
	mock_get_history = AsyncMock(return_value=expected)
	monkeypatch.setattr(router_module.user_service, "get_login_history", mock_get_history)

	with TestClient(app) as client:
		res = client.get("/api/users/me/login-history")

	assert res.status_code == 200
	assert res.json() == expected.model_dump(mode="json")
	assert res.headers["Cache-Control"] == "no-store"
	app.dependency_overrides.clear()


def test_get_my_login_history_jwt_mode_success(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	"""jwtモードでGET /api/users/me/login-history を呼ぶと、200でservice層の結果をそのまま返すことを検証する。"""
	expected = LoginHistoryListResponse(items=[], meta=LoginHistoryMeta(limit=50, count=0))
	monkeypatch.setattr(router_module.user_service, "get_login_history", AsyncMock(return_value=expected))

	res = client.get("/api/users/me/login-history")

	assert res.status_code == 200
	assert res.json() == expected.model_dump(mode="json")


def test_get_my_login_history_unauthenticated_returns_401(app_and_mocks: FastAPI) -> None:
	"""未認証状態でGET /api/users/me/login-history を呼ぶと、ステータス401・エラーコード
	UNAUTHENTICATEDで応答することを検証する。
	"""
	with _unauthenticated_client(app_and_mocks) as client:
		res = client.get("/api/users/me/login-history")

	assert res.status_code == 401
	assert res.json()["error"]["code"] == "UNAUTHENTICATED"


def test_get_my_login_history_inactive_user_returns_403(app_and_mocks: FastAPI) -> None:
	"""非アクティブユーザーでGET /api/users/me/login-history を呼ぶと、ステータス403・エラーコード
	USER_INACTIVEで応答することを検証する。
	"""
	with _inactive_user_client(app_and_mocks) as client:
		res = client.get("/api/users/me/login-history")

	assert res.status_code == 403
	assert res.json()["error"]["code"] == "USER_INACTIVE"


def test_get_my_login_history_uses_configured_limit(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
	"""GET /api/users/me/login-history が、クエリパラメータ無しでも設定上の既定件数(limit=50)を
	service層へ渡していることを検証する。
	"""
	expected = LoginHistoryListResponse(items=[], meta=LoginHistoryMeta(limit=50, count=0))
	mock_get_history = AsyncMock(return_value=expected)
	monkeypatch.setattr(router_module.user_service, "get_login_history", mock_get_history)

	client.get("/api/users/me/login-history")

	_, kwargs = mock_get_history.call_args
	assert kwargs["limit"] == 50
