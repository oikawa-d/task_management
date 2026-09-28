"""通知APIの認証依存性・障害境界をrouter経由で検証する。
DB/Redisはいずれもモック（AsyncMock・OperationalError注入）で代替しており、実インフラへの接続は行わない。
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from app.api.routers import notifications_router
from app.auth.base import AuthContext
from app.auth.factory import get_auth_strategy
from app.auth.jwt_auth import JwtAuthStrategy
from app.auth.session_auth import SessionAuthStrategy
from app.core import deps
from app.core.config import get_backend_settings
from app.core.exceptions import register_error_handling
from app.db import get_db_session
from app.models.user import User
from app.repository.redis_store_common import SessionData
from app.service import notification_service
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

ALLOWED_ORIGIN = "http://localhost:5173"
USER_ID = uuid4()
NOTIFICATION_ID = uuid4()
NOTIFICATION_ENDPOINTS = [
	("get", "/api/notifications"),
	("get", "/api/notifications/unread-count"),
	("patch", f"/api/notifications/{NOTIFICATION_ID}/read"),
	("post", "/api/notifications/read-all"),
]


class _AuthenticatedStrategy:
	"""常に指定したユーザーIDで認証成功を返す、認証済み状態を模擬するダミーAuthStrategy。"""

	def __init__(self, mode: str, user_id: UUID) -> None:
		"""認証モードと、認証成功時に返すユーザーIDを保持する。"""
		self.mode = mode
		self._user_id = user_id

	async def authenticate(self, _request: object) -> AuthContext:
		"""常に保持しているuser_idを持つAuthContextを返す（リクエスト内容は使わない）。"""
		return AuthContext(user_id=self._user_id)


def _build_app(monkeypatch: pytest.MonkeyPatch, strategy: object, db: object) -> FastAPI:
	"""notifications_routerのみを組み込み、認証Strategy・DBセッションを差し替えたFastAPIアプリを組み立てる。

	Args:
		monkeypatch: user_repository.get_by_idの差し替えに使うpytest fixture。
		strategy: get_auth_strategyの差し替え先とするAuthStrategy。
		db: get_db_sessionの差し替え先とするダミーDBセッション（AsyncMock等）。

	Returns:
		認証・DBセッション・user_repository.get_by_idをオーバーライド済みのFastAPIアプリ。
	"""
	app = FastAPI()
	register_error_handling(app)
	app.include_router(notifications_router.router)
	app.dependency_overrides[get_auth_strategy] = lambda: strategy
	app.dependency_overrides[get_db_session] = lambda: db
	monkeypatch.setattr(
		deps.user_repository,
		"get_by_id",
		AsyncMock(
			return_value=User(
				id=USER_ID,
				username="notification-router",
				email="notification-router@example.com",
				password_hash="hash",
				role="member",
				is_active=True,
			)
		),
	)
	return app


@pytest.mark.parametrize("method, path", NOTIFICATION_ENDPOINTS)
def test_notifications_router_rejects_missing_and_invalid_jwt_authentication(
	monkeypatch: pytest.MonkeyPatch,
	method: str,
	path: str,
) -> None:
	"""notifications_router配下の全4エンドポイントについて、jwtモードでAuthorizationヘッダーが
	無い場合・不正なbearerトークンの場合のいずれも、ステータス401・エラーコードUNAUTHENTICATEDで
	応答することを検証する。
	"""
	strategy = JwtAuthStrategy(get_backend_settings())
	app = _build_app(monkeypatch, strategy, None)
	monkeypatch.setattr(deps.redis_store, "check_rate_limit", AsyncMock(return_value=1))

	with TestClient(app) as client:
		for headers in ({}, {"Authorization": "Bearer invalid-token"}):
			response = getattr(client, method)(path, headers=headers)
			assert response.status_code == 401
			assert response.json()["error"]["code"] == "UNAUTHENTICATED"


@pytest.mark.parametrize("method, path", NOTIFICATION_ENDPOINTS)
def test_notifications_router_rejects_missing_and_invalid_session_authentication(
	monkeypatch: pytest.MonkeyPatch,
	method: str,
	path: str,
) -> None:
	"""notifications_router配下の全4エンドポイントについて、sessionモードでセッションCookieが
	無い場合はステータス401・エラーコードUNAUTHENTICATED、Cookieはあるが対応するセッションが
	Redis上に存在しない場合はステータス401・エラーコードSESSION_EXPIREDで応答することを検証する。
	"""
	strategy = SessionAuthStrategy(get_backend_settings())
	app = _build_app(monkeypatch, strategy, None)
	monkeypatch.setattr(deps.redis_store, "get_session", AsyncMock(return_value=None))

	with TestClient(app) as client:
		for cookies, expected_code in (
			({}, "UNAUTHENTICATED"),
			({"cerberus_sid": "invalid-session"}, "SESSION_EXPIRED"),
		):
			response = getattr(client, method)(path, cookies=cookies)
			assert response.status_code == 401
			assert response.json()["error"]["code"] == expected_code


@pytest.mark.parametrize(
	("method", "path"),
	[("patch", f"/api/notifications/{NOTIFICATION_ID}/read"), ("post", "/api/notifications/read-all")],
)
@pytest.mark.parametrize("csrf_header", [None, "wrong-token"])
def test_session_notification_mutations_reject_missing_or_invalid_csrf(
	monkeypatch: pytest.MonkeyPatch,
	method: str,
	path: str,
	csrf_header: str | None,
) -> None:
	"""既読化(PATCH)・一括既読化(POST)の状態変更系エンドポイントについて、sessionモードで
	X-CSRF-Tokenヘッダーが無い場合・Redis保存値と一致しない場合のいずれも、service層を
	呼び出す前にステータス403・エラーコードCSRF_INVALIDで拒否することを検証する。
	"""
	strategy = SessionAuthStrategy(get_backend_settings())
	app = _build_app(monkeypatch, strategy, None)
	monkeypatch.setattr(
		deps.redis_store,
		"get_session",
		AsyncMock(return_value=SessionData(USER_ID, datetime.now(UTC), None)),
	)
	monkeypatch.setattr(deps.redis_store, "touch_session", AsyncMock(return_value=True))
	monkeypatch.setattr(deps.redis_store, "check_rate_limit", AsyncMock(return_value=1))
	monkeypatch.setattr(deps.redis_store, "get_csrf_token", AsyncMock(return_value="token-abc"))
	monkeypatch.setattr(notification_service, "mark_notification_read", AsyncMock())
	monkeypatch.setattr(notification_service, "mark_all_notifications_read", AsyncMock())

	with TestClient(app) as client:
		client.cookies.set("cerberus_sid", "sid-1")
		headers = {"Origin": ALLOWED_ORIGIN}
		if csrf_header is not None:
			headers["X-CSRF-Token"] = csrf_header
		response = getattr(client, method)(path, headers=headers)

	assert response.status_code == 403
	assert response.json()["error"]["code"] == "CSRF_INVALID"


@pytest.mark.parametrize(
	("method", "path"),
	[("patch", f"/api/notifications/{NOTIFICATION_ID}/read"), ("post", "/api/notifications/read-all")],
)
def test_session_notification_mutations_reject_disallowed_origin(
	monkeypatch: pytest.MonkeyPatch, method: str, path: str
) -> None:
	"""既読化(PATCH)・一括既読化(POST)の状態変更系エンドポイントについて、sessionモードでOriginヘッダーが
	許可オリジンに含まれない場合、CSRFトークン自体は正しくてもステータス403・エラーコードCSRF_INVALIDで
	拒否することを検証する。
	"""
	strategy = SessionAuthStrategy(get_backend_settings())
	app = _build_app(monkeypatch, strategy, None)
	monkeypatch.setattr(
		deps.redis_store,
		"get_session",
		AsyncMock(return_value=SessionData(USER_ID, datetime.now(UTC), None)),
	)
	monkeypatch.setattr(deps.redis_store, "touch_session", AsyncMock(return_value=True))
	monkeypatch.setattr(deps.redis_store, "check_rate_limit", AsyncMock(return_value=1))
	monkeypatch.setattr(deps.redis_store, "get_csrf_token", AsyncMock(return_value="token-abc"))

	with TestClient(app) as client:
		client.cookies.set("cerberus_sid", "sid-1")
		response = getattr(client, method)(
			path,
			headers={"Origin": "http://evil.example", "X-CSRF-Token": "token-abc"},
		)

	assert response.status_code == 403
	assert response.json()["error"]["code"] == "CSRF_INVALID"


@pytest.mark.parametrize("method, path", NOTIFICATION_ENDPOINTS)
def test_notification_router_returns_503_for_postgresql_failure_instead_of_empty_result(
	monkeypatch: pytest.MonkeyPatch,
	method: str,
	path: str,
) -> None:
	"""notifications_router配下の全4エンドポイントについて、DB接続エラー（sqlstate=08006）が
	発生した場合、空の一覧や0件のような正常応答ではなく、ステータス503・エラーコード
	SERVICE_UNAVAILABLEで応答し、レスポンスボディにitemsキーを含まないことを検証する。
	"""
	db = AsyncMock()
	db.execute.side_effect = OperationalError("SELECT notifications", {}, SimpleNamespace(sqlstate="08006"))
	app = _build_app(monkeypatch, _AuthenticatedStrategy("jwt", USER_ID), db)
	monkeypatch.setattr(deps.redis_store, "check_rate_limit", AsyncMock(return_value=1))

	with TestClient(app, raise_server_exceptions=False) as client:
		response = getattr(client, method)(path)

	assert response.status_code == 503
	assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
	assert response.json().get("items") is None


@pytest.mark.parametrize("method, path", NOTIFICATION_ENDPOINTS)
def test_notification_router_returns_503_for_redis_failure_instead_of_zero_result(
	monkeypatch: pytest.MonkeyPatch,
	method: str,
	path: str,
) -> None:
	"""notifications_router配下の全4エンドポイントについて、レート制限チェック自体（Redis）が
	例外を送出する場合、0件のような正常応答ではなくステータス503・エラーコードSERVICE_UNAVAILABLEで
	fail-closeし、service層（list_notifications等）は一切呼び出されないことを検証する。
	"""
	app = _build_app(monkeypatch, _AuthenticatedStrategy("jwt", USER_ID), None)
	monkeypatch.setattr(deps.redis_store, "check_rate_limit", AsyncMock(side_effect=RuntimeError("redis down")))
	mock_list = AsyncMock()
	monkeypatch.setattr(notification_service, "list_notifications", mock_list)

	with TestClient(app, raise_server_exceptions=False) as client:
		response = getattr(client, method)(path)

	assert response.status_code == 503
	assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
	mock_list.assert_not_awaited()
