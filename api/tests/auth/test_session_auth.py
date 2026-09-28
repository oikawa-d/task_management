"""app.auth.session_auth.SessionAuthStrategy（sessionモードの認証：ログイン・認証・ログアウト・
ロールバック、jwt専用機能の未サポート）に対する単体テスト。
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from app.auth.base import LoginResult
from app.auth.session_auth import SessionAuthStrategy
from app.core.config import BackendSettings
from app.core.exceptions import NotSupportedInModeError, SessionExpiredError
from app.repository.redis_store_common import SessionData
from fastapi import Response
from starlette.requests import Request


def _settings(**overrides: object) -> BackendSettings:
	"""SessionAuthStrategyの生成に必要な値を満たした最小限のBackendSettingsを作る。

	Args:
		**overrides: 既定値を上書きしたいフィールド（例: trusted_proxy_cidrs）。

	Returns:
		既定値にoverridesを反映したBackendSettings。
	"""
	values: dict[str, object] = {
		"database_url": "postgresql+asyncpg://test:test@localhost/test",
		"jwt_secret_key": "test-secret",
		"google_client_id": "client",
		"google_client_secret": "secret",
		"initial_admin_email": "admin@example.com",
		"initial_admin_username": "admin",
		"initial_admin_password": "Password1!",
		"session_ttl_seconds": 30,
		"session_absolute_ttl_seconds": 300,
		"cookie_secure": True,
	}
	values.update(overrides)
	return BackendSettings(**values)


def _request(cookie: str | None = None, peer: str = "127.0.0.1", forwarded: str | None = None) -> Request:
	"""検証用のASGIリクエストを組み立てる。

	Args:
		cookie: Cookieヘッダーの値（例: "cerberus_sid=session-id"）。Noneの場合は付与しない。
		peer: TCP接続の直接の送信元IP。
		forwarded: X-Forwarded-Forヘッダーの値。Noneの場合は付与しない。

	Returns:
		指定した条件のRequestインスタンス。
	"""
	headers: list[tuple[bytes, bytes]] = []
	if cookie is not None:
		headers.append((b"cookie", cookie.encode()))
	if forwarded is not None:
		headers.append((b"x-forwarded-for", forwarded.encode()))
	return Request({"type": "http", "headers": headers, "client": (peer, 1234)})


def _user() -> SimpleNamespace:
	"""IDのみを持つダミーユーザーを作る。

	Returns:
		id属性のみを持つSimpleNamespace。
	"""
	return SimpleNamespace(id=uuid4())


@pytest.mark.asyncio
async def test_login_sets_http_only_session_and_readable_csrf_cookies(monkeypatch: pytest.MonkeyPatch) -> None:
	"""ログイン成功時に、セッションCookie（cerberus_sid: HttpOnly・Secure）と
	CSRF Cookie（cerberus_csrf: 非HttpOnly、JS側から読めることが前提）が発行され、
	LoginResultにsession_id・csrf_token・expires_in（session_ttl_seconds）・
	access/refresh_tokenがNoneであることが反映されることを検証する。
	"""
	user = _user()
	monkeypatch.setattr(
		"app.auth.session_auth.redis_store.create_session",
		lambda user_id, ip, ttl: _create_session(user_id, ip, ttl),
	)
	strategy = SessionAuthStrategy(_settings())
	response = Response()

	result = await strategy.login(user, _request(), response)
	cookies = [value.decode() for key, value in response.raw_headers if key == b"set-cookie"]

	assert result.auth_mode == "session"
	assert result.access_token is None
	assert result.refresh_token is None
	assert result.csrf_token == "csrf-token"
	assert result.expires_in == 30
	assert result.session_id == "session-id"
	assert result.user_id == user.id
	assert any("cerberus_sid=session-id" in value and "HttpOnly" in value and "Secure" in value for value in cookies)
	assert any("cerberus_csrf=csrf-token" in value and "HttpOnly" not in value for value in cookies)


async def _create_session(user_id: object, ip: str | None, ttl: int) -> tuple[str, str]:
	"""redis_store.create_sessionの差し替え先。渡されたIP・TTLが期待値通りかを内部でassertしつつ、
	固定のセッションID・CSRFトークンを返す。
	"""
	assert ip == "127.0.0.1"
	assert ttl == 30
	return "session-id", "csrf-token"


@pytest.mark.asyncio
async def test_login_uses_trusted_xff_client_ip(monkeypatch: pytest.MonkeyPatch) -> None:
	"""信頼済みプロキシ経由（trusted_proxy_cidrsに合致する接続元）のログインでは、
	X-Forwarded-Forから解決したクライアントIP（プロキシ自身のIPではない）でセッションが作成されることを検証する。
	"""
	create_session = AsyncMock(return_value=("session-id", "csrf-token"))
	monkeypatch.setattr("app.auth.session_auth.redis_store.create_session", create_session)
	strategy = SessionAuthStrategy(_settings(trusted_proxy_cidrs=["10.0.0.0/8"]))
	user = _user()

	await strategy.login(user, _request(peer="10.0.0.1", forwarded="198.51.100.4, 10.0.0.2"), Response())

	create_session.assert_awaited_once_with(user.id, "198.51.100.4", 30)


@pytest.mark.asyncio
async def test_authenticate_without_cookie_returns_none() -> None:
	"""セッションCookieが無いリクエストの認証は、例外を送出せずNoneを返すことを検証する。"""
	assert await SessionAuthStrategy(_settings()).authenticate(_request()) is None


@pytest.mark.asyncio
async def test_authenticate_touches_valid_session_and_raises_for_expired_session(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""有効なセッションCookieでの認証は、Redis上のセッションを延長(touch)しつつユーザーID・セッションIDを
	含む認証コンテキストを返すこと、また延長(touch)が失敗する（絶対有効期限切れ等で更新できない）場合は
	SessionExpiredErrorを送出することを検証する。
	"""
	user_id = uuid4()
	monkeypatch.setattr(
		"app.auth.session_auth.redis_store.get_session",
		lambda session_id: _get_session(session_id, user_id),
	)
	monkeypatch.setattr("app.auth.session_auth.redis_store.touch_session", lambda *args: _touch_session(*args))
	strategy = SessionAuthStrategy(_settings())

	context = await strategy.authenticate(_request("cerberus_sid=session-id"))
	assert context is not None
	assert context.user_id == user_id
	assert context.session_id == "session-id"

	monkeypatch.setattr("app.auth.session_auth.redis_store.touch_session", lambda *args: _false_touch(*args))
	with pytest.raises(SessionExpiredError):
		await strategy.authenticate(_request("cerberus_sid=session-id"))


@pytest.mark.asyncio
async def test_authenticate_raises_for_missing_session(monkeypatch: pytest.MonkeyPatch) -> None:
	"""Cookieのセッションidに対応するセッションがRedis上に存在しない（None）場合、
	SessionExpiredErrorを送出することを検証する。
	"""
	monkeypatch.setattr("app.auth.session_auth.redis_store.get_session", AsyncMock(return_value=None))

	with pytest.raises(SessionExpiredError):
		await SessionAuthStrategy(_settings()).authenticate(_request("cerberus_sid=expired-session"))


async def _get_session(session_id: str, user_id: UUID) -> SessionData:
	"""redis_store.get_sessionの差し替え先。渡されたセッションIDが期待値通りかをassertしつつ、
	固定のSessionDataを返す。
	"""
	assert session_id == "session-id"
	return SessionData(user_id, datetime.now(UTC), "127.0.0.1")


async def _touch_session(*args: object) -> bool:
	"""redis_store.touch_sessionの差し替え先。延長対象のセッションIDが期待値通りかをassertしつつTrue(成功)を返す。"""
	assert args[0] == "session-id"
	return True


async def _false_touch(*args: object) -> bool:
	"""redis_store.touch_sessionの差し替え先。延長に失敗した状況を模擬してFalseを返す固定スタブ。"""
	return False


@pytest.mark.asyncio
async def test_logout_deletes_session_and_clears_cookies(monkeypatch: pytest.MonkeyPatch) -> None:
	"""ログアウト時にRedis上のセッションが削除され、レスポンスにセッション・CSRFの
	2つの削除用Set-Cookie（Max-Age=0）が設定されることを検証する。
	"""
	user_id = uuid4()
	monkeypatch.setattr(
		"app.auth.session_auth.redis_store.get_session",
		lambda session_id: _get_session(session_id, user_id),
	)
	monkeypatch.setattr("app.auth.session_auth.redis_store.delete_session", lambda *args: _delete_session(*args))
	strategy = SessionAuthStrategy(_settings())
	response = Response()

	await strategy.logout(_request("cerberus_sid=session-id"), response)

	assert len([header for key, header in response.raw_headers if key == b"set-cookie"]) == 2
	assert all(b"Max-Age=0" in header for key, header in response.raw_headers if key == b"set-cookie")


async def _delete_session(session_id: str, user_id: object) -> None:
	"""redis_store.delete_sessionの差し替え先。削除対象のセッションIDが期待値通りかをassertするだけのスタブ。"""
	assert session_id == "session-id"


@pytest.mark.asyncio
async def test_rollback_login_deletes_session_and_clears_cookies(monkeypatch: pytest.MonkeyPatch) -> None:
	"""登録直後のロールバック時に、発行済みセッションがRedisから削除され、
	既にセットされていたセッション/CSRF Cookieに対して、Max-Age=0の削除用Set-Cookieが
	新たに2件追加される（合計4件のSet-Cookieになる）ことを検証する。
	"""
	delete_session = AsyncMock()
	monkeypatch.setattr("app.auth.session_auth.redis_store.delete_session", delete_session)
	strategy = SessionAuthStrategy(_settings())
	response = Response()
	strategy._set_cookies(response, "session-id", "csrf-token")
	user = _user()
	rollback_user_id = uuid4()
	result = LoginResult(
		"session", csrf_token="csrf-token", expires_in=30, session_id="session-id", user_id=rollback_user_id
	)

	await strategy.rollback_login(user, result, response)

	delete_session.assert_awaited_once_with("session-id", rollback_user_id)
	assert len([header for key, header in response.raw_headers if key == b"set-cookie"]) == 4
	deleted = [header for key, header in response.raw_headers if key == b"set-cookie"][2:]
	assert all(b"Max-Age=0" in header for header in deleted)


@pytest.mark.asyncio
async def test_refresh_is_not_supported_in_session_mode() -> None:
	"""sessionモードではリフレッシュ機能自体が提供されないため、refresh呼び出しがNotSupportedInModeErrorを
	送出することを検証する。
	"""
	with pytest.raises(NotSupportedInModeError):
		await SessionAuthStrategy(_settings()).refresh(_request(), Response())
