"""app.auth.jwt_auth.JwtAuthStrategy（JWTモードの認証：ログイン・認証・リフレッシュ・ログアウト・
ロールバック）に対する単体テスト。
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import jwt
import pytest
from app.auth.base import LoginResult
from app.auth.jwt_auth import JwtAuthStrategy
from app.core.config import BackendSettings
from app.core.exceptions import TokenInvalidError, TokenRevokedError
from app.repository.redis_store_common import RefreshData, TokenReused
from fastapi import Response
from starlette.requests import Request


def _settings() -> BackendSettings:
	"""JwtAuthStrategyの生成に必要な値を満たした最小限のBackendSettingsを作る。

	Returns:
		JWT秘密鍵・トークンTTL等を固定値で設定したBackendSettings。
	"""
	return BackendSettings(
		database_url="postgresql+asyncpg://test:test@localhost/test",
		jwt_secret_key="test-secret",
		google_client_id="client",
		google_client_secret="secret",
		initial_admin_email="admin@example.com",
		initial_admin_username="admin",
		initial_admin_password="Password1!",
		access_token_ttl_seconds=60,
		refresh_ttl_seconds=900,
		cookie_secure=True,
	)


def _request(headers: list[tuple[bytes, bytes]] | None = None, cookie: str | None = None) -> Request:
	"""検証用のASGIリクエストを組み立てる。

	Args:
		headers: 付与するHTTPヘッダー（authorization等）。
		cookie: Cookieヘッダーの値（例: "cerberus_rt=old"）。Noneの場合は付与しない。

	Returns:
		指定した条件のRequestインスタンス。
	"""
	request_headers = headers or []
	if cookie is not None:
		request_headers = [*request_headers, (b"cookie", cookie.encode())]
	return Request({"type": "http", "headers": request_headers})


def _user() -> SimpleNamespace:
	"""IDのみを持つダミーユーザーを作る。

	Returns:
		id属性のみを持つSimpleNamespace。
	"""
	return SimpleNamespace(id=uuid4())


@pytest.mark.asyncio
async def test_login_issues_access_token_and_refresh_cookie(monkeypatch: pytest.MonkeyPatch) -> None:
	"""ログイン成功時に、typ=accessのJWTアクセストークンが発行され、リフレッシュトークンがRedisへ1件保存され、
	レスポンスのSet-CookieにリフレッシュCookie（cerberus_rt: HttpOnly・SameSite=strict・Path=/api/auth・
	Max-Age=refresh_ttl_seconds）とCSRF Cookie（cerberus_csrf: 非HttpOnly・Path=/・同一Max-Age）の
	両方が正しい属性で設定されることを検証する。
	"""
	stored: dict[str, tuple[object, object, int]] = {}

	async def store(token: str, user_id: object, family_id: str, ttl: int) -> None:
		"""redis_store.store_refresh_tokenの差し替え先。呼び出し引数をstoredへ記録するだけのスタブ。"""
		stored[token] = (user_id, family_id, ttl)

	monkeypatch.setattr("app.auth.jwt_auth.redis_store.store_refresh_token", store)
	strategy = JwtAuthStrategy(_settings())
	response = Response()
	user = _user()
	result = await strategy.login(user, _request(), response)

	claims = jwt.decode(result.access_token or "", _settings().jwt_secret_key, algorithms=["HS256"])
	cookies = [value.decode() for key, value in response.raw_headers if key == b"set-cookie"]
	assert claims["typ"] == "access"
	assert claims["jti"]
	assert len(stored) == 1
	assert result.refresh_token in stored
	assert result.user_id == user.id
	assert any(
		"cerberus_rt=" in value
		and "HttpOnly" in value
		and "SameSite=strict" in value
		and "Path=/api/auth" in value
		and "Max-Age=900" in value
		for value in cookies
	)
	assert any(
		"cerberus_csrf=" in value and "HttpOnly" not in value and "Path=/" in value and "Max-Age=900" in value
		for value in cookies
	)


@pytest.mark.asyncio
async def test_authenticate_accepts_only_valid_access_bearer_token() -> None:
	"""Authorizationヘッダーのbearerトークンについて、typ=accessかつ有効期限内・正しい署名のトークンのみを
	認証成功として扱い、typ不一致・期限切れ・署名不一致のトークンはいずれも認証コンテキストNoneを返す
	（例外を送出しない）ことを検証する。
	"""
	strategy = JwtAuthStrategy(_settings())
	user_id = uuid4()
	token = jwt.encode(
		{
			"sub": str(user_id),
			"iat": datetime.now(UTC),
			"exp": datetime.now(UTC) + timedelta(minutes=1),
			"jti": "jti",
			"typ": "access",
		},
		_settings().jwt_secret_key,
		algorithm="HS256",
	)

	context = await strategy.authenticate(_request([(b"authorization", f"Bearer {token}".encode())]))
	assert context is not None
	assert context.user_id == user_id

	wrong_type = jwt.encode(
		{
			"sub": str(user_id),
			"iat": datetime.now(UTC),
			"exp": datetime.now(UTC) + timedelta(minutes=1),
			"jti": "jti",
			"typ": "refresh",
		},
		_settings().jwt_secret_key,
		algorithm="HS256",
	)
	assert await strategy.authenticate(_request([(b"authorization", f"Bearer {wrong_type}".encode())])) is None

	expired = jwt.encode(
		{
			"sub": str(user_id),
			"iat": datetime.now(UTC) - timedelta(minutes=2),
			"exp": datetime.now(UTC) - timedelta(minutes=1),
			"jti": "expired-jti",
			"typ": "access",
		},
		_settings().jwt_secret_key,
		algorithm="HS256",
	)
	assert await strategy.authenticate(_request([(b"authorization", f"Bearer {expired}".encode())])) is None

	wrong_signature = jwt.encode(
		{
			"sub": str(user_id),
			"iat": datetime.now(UTC),
			"exp": datetime.now(UTC) + timedelta(minutes=1),
			"jti": "wrong-signature",
			"typ": "access",
		},
		"wrong-secret",
		algorithm="HS256",
	)
	assert await strategy.authenticate(_request([(b"authorization", f"Bearer {wrong_signature}".encode())])) is None


@pytest.mark.asyncio
async def test_refresh_rotates_token_and_reuse_revokes_family(monkeypatch: pytest.MonkeyPatch) -> None:
	"""正常なリフレッシュではトークンがローテーション（新トークン発行）されること、
	そのローテーション済みトークンで再度リフレッシュ（=トークン再利用）を試みた場合は
	トークンファミリー全体が失効し、TokenRevokedErrorが送出されることを検証する。
	"""
	user_id = uuid4()
	metadata = RefreshData(user_id, datetime.now(UTC), "family-1")
	rotated_token: list[str] = []

	async def rotate(*args: object) -> RefreshData:
		"""redis_store.rotate_refresh_tokenの差し替え先。呼び出されたトークンを記録し、正常系のRefreshDataを返す。"""
		rotated_token.append(str(args[1]))
		return metadata

	monkeypatch.setattr("app.auth.jwt_auth.redis_store.rotate_refresh_token", rotate)
	strategy = JwtAuthStrategy(_settings())
	response = Response()
	result = await strategy.refresh(_request(cookie="cerberus_rt=old"), response)
	assert result.auth_mode == "jwt"
	assert result.refresh_token == rotated_token[0]

	monkeypatch.setattr(
		"app.auth.jwt_auth.redis_store.rotate_refresh_token", lambda *args: _reused(*args, metadata=metadata)
	)
	monkeypatch.setattr("app.auth.jwt_auth.redis_store.revoke_token_family", lambda *args: _revoke_family(*args))
	with pytest.raises(TokenRevokedError):
		await strategy.refresh(_request(cookie="cerberus_rt=old"), Response())


async def _reused(*args: object, metadata: RefreshData) -> TokenReused:
	"""redis_store.rotate_refresh_tokenの差し替え先。トークン再利用が検知された状況を模擬し、
	該当メタデータのuser_id・family_idを持つTokenReusedを返す。
	"""
	return TokenReused(metadata.user_id, metadata.family_id)


async def _revoke_family(*args: object) -> int:
	"""redis_store.revoke_token_familyの差し替え先。失効件数1件を返す固定スタブ。"""
	return 1


@pytest.mark.asyncio
async def test_refresh_without_cookie_is_invalid_and_logout_clears_cookies(monkeypatch: pytest.MonkeyPatch) -> None:
	"""リフレッシュCookieが無い状態でのリフレッシュはTokenInvalidErrorを送出すること、
	また存在しない（Redis未検出の）リフレッシュトークンでのログアウトでも例外を送出せず、
	リフレッシュCookieとCSRF Cookieの2つの削除用Set-Cookieが返されることを検証する。
	"""
	strategy = JwtAuthStrategy(_settings())
	with pytest.raises(TokenInvalidError):
		await strategy.refresh(_request(), Response())

	monkeypatch.setattr("app.auth.jwt_auth.redis_store.get_refresh_token", lambda token: _missing(token))
	response = Response()
	await strategy.logout(_request(cookie="cerberus_rt=missing"), response)
	assert len([header for key, header in response.raw_headers if key == b"set-cookie"]) == 2


@pytest.mark.asyncio
async def test_rollback_login_revokes_refresh_token_and_clears_cookies(monkeypatch: pytest.MonkeyPatch) -> None:
	"""登録直後のロールバック時に、発行済みのリフレッシュトークンがRedisから失効され、
	既にセットされていたリフレッシュ/CSRF Cookieに対して、Max-Age=0の削除用Set-Cookieが
	新たに2件追加されることを検証する。
	"""
	revoke = AsyncMock()
	monkeypatch.setattr("app.auth.jwt_auth.redis_store.revoke_refresh_token", revoke)
	strategy = JwtAuthStrategy(_settings())
	response = Response()
	user = _user()
	rollback_user_id = uuid4()
	result = LoginResult("jwt", "access-token", "refresh-token", "csrf-token", 60, user_id=rollback_user_id)
	strategy._set_cookies(response, result.refresh_token or "", result.csrf_token or "")

	await strategy.rollback_login(user, result, response)

	revoke.assert_awaited_once_with(result.refresh_token, rollback_user_id)
	deleted = [header for key, header in response.raw_headers if key == b"set-cookie"][2:]
	assert len(deleted) == 2
	assert all(b"Max-Age=0" in header for header in deleted)


@pytest.mark.asyncio
async def test_refresh_with_expired_or_deleted_token_is_revoked(monkeypatch: pytest.MonkeyPatch) -> None:
	"""ローテーション対象のリフレッシュトークンがRedis上に存在しない（期限切れ・削除済み）場合、
	TokenRevokedErrorを送出することを検証する。
	"""
	monkeypatch.setattr("app.auth.jwt_auth.redis_store.rotate_refresh_token", lambda *args: _missing(args))
	with pytest.raises(TokenRevokedError):
		await JwtAuthStrategy(_settings()).refresh(_request(cookie="cerberus_rt=expired"), Response())


async def _missing(token: object) -> RefreshData | None:
	"""redis_store側の差し替え先。トークンが見つからない状況を模擬してNoneを返す固定スタブ。"""
	return None
