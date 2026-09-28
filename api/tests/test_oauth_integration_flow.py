"""OAuth開始→callback→exchange→既存session/JWT認証確立までの結合テスト。

Google token/userinfo/JWKSエンドポイントのみを境界として差し替え、Redis（state/handoff/
session/refresh）とPostgreSQL（users/oauth_accounts/login_history）は実接続を用いて、
state/PKCE/nonce/handoffの検証と消費、許可redirectのみの処理、既存session/JWT認証の確立、
外部I/O障害時のfail-closeを検証する。

db_session（実DB）とTestClient（別スレッドのイベントループ）を組み合わせるとasyncpg接続が
異なるイベントループにまたがり破綻するため、ASGITransport経由のhttpx2.AsyncClientを用いて
テスト関数と同一イベントループ上でリクエストを実行する。

参照設計書: docs/detailed_design/auth/04_google_oauth.md（4〜11章、テスト設計No.2〜11）
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
import uuid
from typing import Any
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from app import redis_client
from app.api.routers import auth_router
from app.api.routers import oauth_router as oauth_router_module
from app.auth.factory import get_auth_strategy
from app.auth.oauth import GoogleOAuthProvider
from app.core.config import get_backend_settings
from app.core.exceptions import register_error_handling
from app.db import get_db_session
from app.repository import login_history_repository, oauth_account_repository, user_repository
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient
from jwt.algorithms import RSAAlgorithm
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

ALLOWED_ORIGIN = "http://localhost:5173"
FRONTEND_BASE_URL = "http://localhost:5173"


@pytest.fixture(autouse=True)
async def _fresh_redis_client_per_test() -> None:
	"""get_redis_client()はlru_cacheのプロセス単位シングルトンで、テストごとに新しい
	イベントループを使うpytest-asyncioと組み合わせると前のテストの接続を別ループで
	使い回してしまう。テストごとに接続を張り直し、実Redisへの結合を健全に保つ。"""
	redis_client.get_redis_client.cache_clear()
	yield
	try:
		await redis_client.close_redis_client()
	except Exception:
		pass
	redis_client.get_redis_client.cache_clear()


def _new_identity() -> tuple[str, str]:
	"""テストごとに一意なGoogle sub/emailを発行し、DBへの実書き込みが他テストと衝突しないようにする。

	usersテーブルのemailはvarchar(50)のため、短い一意サフィックスに収める。
	"""
	unique = uuid.uuid4().hex[:10]
	return f"google-sub-{unique}", f"oauth-{unique}@example.com"


def _userinfo(sub: str, email: str, *, email_verified: bool = True) -> dict[str, Any]:
	"""Google userinfoエンドポイントのレスポンス相当の辞書を組み立てるヘルパー関数。

	Returns:
		dict[str, Any]: `sub`・`email`・`email_verified`を持つuserinfo相当の辞書。
	"""
	return {"sub": sub, "email": email, "email_verified": email_verified}


class _HttpResponse:
	"""`_GoogleBoundary`が返す、ステータスコードとJSON本体のみを持つ最小限のHTTPレスポンススタブ。"""

	def __init__(self, status_code: int, body: dict[str, Any]) -> None:
		"""レスポンスのステータスコードとJSON本体を保持する。"""
		self.status_code = status_code
		self._body = body

	def json(self) -> dict[str, Any]:
		"""保持しているJSON本体をそのまま返す。

		Returns:
			dict[str, Any]: コンストラクタで渡された本体。
		"""
		return self._body


class _GoogleBoundary:
	"""Google token/userinfo/JWKSエンドポイントの唯一の差し替え境界（結合テスト用）。

	tokenエンドポイントへ実際に送信されたPOSTボディ（code_verifier等）を`posted`に
	記録し、開始時に発行したcode_verifierがRedis経由でcallbackのtoken交換まで
	正しく引き継がれることを検証できるようにする。
	"""

	def __init__(
		self,
		token: dict[str, Any] | None = None,
		userinfo: dict[str, Any] | None = None,
		jwks: dict[str, Any] | None = None,
		*,
		token_status: int = 200,
		userinfo_status: int = 200,
		jwks_status: int = 200,
	) -> None:
		"""各エンドポイントが返すレスポンス本体・ステータスコードを保持し、
		token交換で送信されたPOSTボディを記録する`posted`リストを初期化する。
		"""
		self.token = token or {}
		self.userinfo = userinfo or {}
		self.jwks = jwks or {}
		self.token_status = token_status
		self.userinfo_status = userinfo_status
		self.jwks_status = jwks_status
		self.posted: list[dict[str, str]] = []

	async def post(self, _url: str, *, data: dict[str, str]) -> _HttpResponse:
		"""Google tokenエンドポイント宛のPOSTを模し、送信データを`posted`へ記録したうえで
		設定済みの`token`・`token_status`を返す。

		Returns:
			_HttpResponse: 設定済みのtokenレスポンス相当のスタブ。
		"""
		self.posted.append(data)
		return _HttpResponse(self.token_status, self.token)

	async def get(self, url: str, *, headers: dict[str, str] | None = None) -> _HttpResponse:
		"""URLに"certs"を含む場合はJWKSエンドポイント、それ以外はuserinfoエンドポイント宛の
		GETとみなし、それぞれ設定済みのレスポンスを返す。

		Returns:
			_HttpResponse: URLに応じたJWKSまたはuserinfoレスポンス相当のスタブ。
		"""
		if "certs" in url:
			return _HttpResponse(self.jwks_status, self.jwks)
		return _HttpResponse(self.userinfo_status, self.userinfo)


def _signed_id_token(
	client_id: str,
	nonce: str,
	*,
	sub: str,
	email: str,
	email_verified: bool = True,
	jwks_kid: str = "key-1",
) -> tuple[str, dict[str, Any]]:
	private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
	public_jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
	public_jwk["kid"] = jwks_kid
	claims: dict[str, Any] = {
		"sub": sub,
		"email": email,
		"email_verified": email_verified,
		"iss": "https://accounts.google.com",
		"aud": client_id,
		"exp": int(time.time()) + 60,
		"nonce": nonce,
	}
	token = jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": jwks_kid})
	return token, {"keys": [public_jwk]}


def _build_app() -> FastAPI:
	"""OAuthルーター・認証ルーターを組み込み、共通エラーハンドリングを登録した検証用アプリを構築する。

	Returns:
		FastAPI: `/api/auth/oauth/*`・`/api/auth/*`のエンドポイントを持つアプリ。
	"""
	app = FastAPI()
	register_error_handling(app)
	app.include_router(oauth_router_module.router)
	app.include_router(auth_router.router)
	return app


def _configure(monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession, *, auth_mode: str, jwks_uri: str) -> FastAPI:
	"""CORS・フロントエンドURL・認証モード・JWKS URI・レート制限上限を環境変数で設定し、
	設定キャッシュ・認証ストラテジーキャッシュをクリアしたうえで、`get_db_session`を
	渡された`db_session`へ差し替えた検証用アプリを構築するヘルパー関数。

	Returns:
		FastAPI: 設定・依存差し替え済みの検証用アプリ。
	"""
	monkeypatch.setenv("CORS_ALLOW_ORIGINS", ALLOWED_ORIGIN)
	monkeypatch.setenv("FRONTEND_BASE_URL", FRONTEND_BASE_URL)
	monkeypatch.setenv("AUTH_MODE", auth_mode)
	monkeypatch.setenv("GOOGLE_JWKS_URI", jwks_uri)
	# レート制限自体は test_oauth_service.py で検証済みのため、実Redisに蓄積した
	# カウンタが結合テストの反復実行を阻害しないよう十分大きい上限へ緩和する。
	monkeypatch.setenv("RATE_LIMIT_OAUTH_MAX_REQUESTS", "100000")
	get_backend_settings.cache_clear()
	get_auth_strategy.cache_clear()
	app = _build_app()
	app.dependency_overrides[get_db_session] = lambda: db_session
	return app


def _client(app: FastAPI) -> AsyncClient:
	"""検証用アプリに対する、リダイレクトを自動追従しない`httpx2.AsyncClient`を生成するヘルパー関数。

	Returns:
		AsyncClient: `ASGITransport`経由でテスト関数と同一イベントループ上で動作するクライアント。
	"""
	return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver", follow_redirects=False)


async def _start_and_capture_state(client: AsyncClient, redirect_to: str = "/dashboard") -> tuple[str, str, str]:
	"""開始エンドポイントを叩き、実Redisへ発行されたstate/nonce/code_challengeを取得する。"""
	response = await client.get("/api/auth/oauth/google", params={"redirect_to": redirect_to})
	assert response.status_code == 302
	query = parse_qs(urlparse(response.headers["location"]).query)
	state = query["state"][0]
	nonce = query["nonce"][0]
	assert query["code_challenge_method"] == ["S256"]
	code_challenge = query["code_challenge"][0]
	assert any(cookie.startswith("cerberus_oauth_state=") for cookie in response.headers.get_list("set-cookie"))
	return state, nonce, code_challenge


def _assert_pkce_verifier_matches_challenge(boundary: _GoogleBoundary, code_challenge: str) -> None:
	"""開始時に発行したcode_challengeと、callbackがtokenエンドポイントへ実際に送信した
	code_verifierの対応関係（S256）を検証する。開始→Redis（oauth_state）→callbackの
	token交換までPKCEの値が正しく引き継がれることの結合テストでの唯一の確認経路。
	"""
	assert len(boundary.posted) == 1
	code_verifier = boundary.posted[0].get("code_verifier")
	assert code_verifier
	expected_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).rstrip(b"=").decode()
	assert expected_challenge == code_challenge


async def _create_existing_user(db_session: AsyncSession, email: str, *, verified: bool) -> uuid.UUID:
	"""OAuth連携前から存在するユーザーを1件作成するヘルパー関数（パスワード未設定）。

	Args:
		db_session: 作成・コミットに使う`AsyncSession`。
		email: 作成するユーザーのメールアドレス。
		verified: Trueの場合、作成直後にメール確認済みとしてマークする。

	Returns:
		uuid.UUID: 作成したユーザーのid。
	"""
	username = f"oauth-existing-{uuid.uuid4().hex[:10]}"
	user_id = await user_repository.create(db_session, username, email, None)
	if verified:
		await user_repository.mark_email_verified(db_session, user_id)
	await db_session.commit()
	return user_id


async def _count_users_by_email(db_session: AsyncSession, email: str) -> int:
	"""指定メールアドレスを持つ`users`行の件数を返すヘルパー関数（重複作成が無いことの確認用）。

	Returns:
		int: 該当するユーザー数。
	"""
	result = await db_session.execute(text("SELECT count(*) FROM users WHERE email = :email"), {"email": email})
	return int(result.scalar_one())


async def _delete_user(db_session: AsyncSession, user_id: uuid.UUID) -> None:
	"""テストで作成した既存ユーザーを片付けるためのヘルパー関数。指定idの`users`行を削除しコミットする。"""
	await db_session.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": user_id})
	await db_session.commit()


async def test_full_session_flow_creates_user_and_establishes_authenticated_session(
	monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession
) -> None:
	"""sessionモードで、開始→callback→session確立までの一連の流れにより、新規ユーザーが
	作成されメール確認済みとなること、`oauth_accounts`にGoogleとの紐付けが1件作成されること、
	`login_history`に`login_method='oauth_google'`・本人のemailで記録されること、
	確立したsessionで`/api/auth/me`が200を返すことを検証する。
	"""
	app = _configure(
		monkeypatch, db_session, auth_mode="session", jwks_uri="https://jwks.example.test/certs/session-happy"
	)
	client_id = get_backend_settings().google_client_id
	sub, email = _new_identity()
	async with _client(app) as client:
		state, nonce, code_challenge = await _start_and_capture_state(client, "/projects/1")
		token, jwks = _signed_id_token(client_id, nonce, sub=sub, email=email)
		boundary = _GoogleBoundary({"id_token": token, "access_token": "access-token"}, _userinfo(sub, email), jwks)
		monkeypatch.setattr(
			oauth_router_module.oauth_service,
			"GoogleOAuthProvider",
			lambda settings: GoogleOAuthProvider(settings, boundary),
		)

		callback = await client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": state})

		assert callback.status_code == 302
		assert callback.headers["location"] == f"{FRONTEND_BASE_URL}/oauth/callback#redirect_to=/projects/1"
		set_cookie = callback.headers.get_list("set-cookie")
		assert any(value.startswith("cerberus_sid=") for value in set_cookie)
		assert any("cerberus_oauth_state=" in value and "Max-Age=0" in value for value in set_cookie)
		_assert_pkce_verifier_matches_challenge(boundary, code_challenge)

		me = await client.get("/api/auth/me")
		assert me.status_code == 200
		assert me.json()["username"].startswith("google_")

	user = await user_repository.get_by_email(db_session, email)
	assert user is not None
	assert user.email_verified_at is not None
	link = await oauth_account_repository.get_by_provider_identity(db_session, "google", sub)
	assert link is not None and link.user_id == user.id
	history = await login_history_repository.list_by_user_id(db_session, user.id)
	assert any(record.login_method == "oauth_google" and record.login_identifier == user.email for record in history)


async def test_oauth_callback_links_existing_verified_email(
	monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession
) -> None:
	"""同一メールアドレスを持つ確認済みの既存ユーザーがいる場合、OAuthコールバックで
	新規ユーザーを重複作成せず、その既存ユーザーへ`oauth_accounts`の紐付けを作成することを検証する。
	"""
	app = _configure(
		monkeypatch, db_session, auth_mode="session", jwks_uri="https://jwks.example.test/certs/existing-verified"
	)
	client_id = get_backend_settings().google_client_id
	sub, email = _new_identity()
	existing_user_id = await _create_existing_user(db_session, email, verified=True)
	user_count_before = await _count_users_by_email(db_session, email)

	try:
		async with _client(app) as client:
			state, nonce, code_challenge = await _start_and_capture_state(client)
			token, jwks = _signed_id_token(client_id, nonce, sub=sub, email=email)
			boundary = _GoogleBoundary({"id_token": token, "access_token": "access-token"}, _userinfo(sub, email), jwks)
			monkeypatch.setattr(
				oauth_router_module.oauth_service,
				"GoogleOAuthProvider",
				lambda settings: GoogleOAuthProvider(settings, boundary),
			)

			callback = await client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": state})

			assert callback.status_code == 302
			assert callback.headers["location"] == f"{FRONTEND_BASE_URL}/oauth/callback#redirect_to=/dashboard"
			_assert_pkce_verifier_matches_challenge(boundary, code_challenge)

		user = await user_repository.get_by_email(db_session, email)
		assert user is not None
		assert user.id == existing_user_id
		assert user.email_verified_at is not None
		assert await _count_users_by_email(db_session, email) == user_count_before

		link = await oauth_account_repository.get_by_provider_identity(db_session, "google", sub)
		assert link is not None
		assert link.user_id == existing_user_id
	finally:
		await _delete_user(db_session, existing_user_id)


async def test_oauth_callback_rejects_unverified_email(
	monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession
) -> None:
	"""同一メールアドレスを持つ未確認の既存ユーザーがいる場合、Google側もemail未確認を返す状況では、
	`error=oauth_email_unverified`へリダイレクトし、既存ユーザーの確認状態やユーザー数を変更せず、
	`oauth_accounts`の紐付けも作成しないことを検証する。
	"""
	app = _configure(
		monkeypatch, db_session, auth_mode="session", jwks_uri="https://jwks.example.test/certs/existing-unverified"
	)
	client_id = get_backend_settings().google_client_id
	sub, email = _new_identity()
	existing_user_id = await _create_existing_user(db_session, email, verified=False)
	user_count_before = await _count_users_by_email(db_session, email)

	try:
		async with _client(app) as client:
			state, nonce, _code_challenge = await _start_and_capture_state(client)
			token, jwks = _signed_id_token(client_id, nonce, sub=sub, email=email, email_verified=False)
			boundary = _GoogleBoundary(
				{"id_token": token, "access_token": "access-token"},
				_userinfo(sub, email, email_verified=False),
				jwks,
			)
			monkeypatch.setattr(
				oauth_router_module.oauth_service,
				"GoogleOAuthProvider",
				lambda settings: GoogleOAuthProvider(settings, boundary),
			)

			callback = await client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": state})

			assert callback.status_code == 302
			assert callback.headers["location"] == f"{FRONTEND_BASE_URL}/login?error=oauth_email_unverified"

		user = await user_repository.get_by_email(db_session, email)
		assert user is not None
		assert user.id == existing_user_id
		assert user.email_verified_at is None
		assert await _count_users_by_email(db_session, email) == user_count_before
		assert await oauth_account_repository.get_by_provider_identity(db_session, "google", sub) is None
	finally:
		await _delete_user(db_session, existing_user_id)


async def test_full_jwt_flow_exchanges_handoff_and_establishes_bearer_authentication(
	monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession
) -> None:
	"""jwtモードで、開始→callback（handoffコード発行）→`/api/auth/oauth/exchange`による
	アクセストークン取得までの流れを検証し、取得したBearerトークンで`/api/auth/me`が200を返すこと、
	同一handoffコードの再利用（リプレイ）は400・`code="OAUTH_HANDOFF_INVALID"`で拒否されること、
	`login_history`に`login_method='oauth_google'`で記録されることを検証する。
	"""
	app = _configure(monkeypatch, db_session, auth_mode="jwt", jwks_uri="https://jwks.example.test/certs/jwt-happy")
	client_id = get_backend_settings().google_client_id
	sub, email = _new_identity()
	async with _client(app) as client:
		state, nonce, code_challenge = await _start_and_capture_state(client)
		token, jwks = _signed_id_token(client_id, nonce, sub=sub, email=email)
		boundary = _GoogleBoundary({"id_token": token, "access_token": "access-token"}, _userinfo(sub, email), jwks)
		monkeypatch.setattr(
			oauth_router_module.oauth_service,
			"GoogleOAuthProvider",
			lambda settings: GoogleOAuthProvider(settings, boundary),
		)

		callback = await client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": state})
		assert callback.status_code == 302
		_assert_pkce_verifier_matches_challenge(boundary, code_challenge)
		fragment = callback.headers["location"].split("#", 1)[1]
		fragment_values = dict(pair.split("=", 1) for pair in fragment.split("&"))
		handoff_code = fragment_values["code"]

		exchange = await client.post(
			"/api/auth/oauth/exchange", json={"code": handoff_code}, headers={"Origin": ALLOWED_ORIGIN}
		)
		assert exchange.status_code == 200
		access_token = exchange.json()["access_token"]

		me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {access_token}"})
		assert me.status_code == 200

		replay = await client.post(
			"/api/auth/oauth/exchange", json={"code": handoff_code}, headers={"Origin": ALLOWED_ORIGIN}
		)
		assert replay.status_code == 400
		assert replay.json()["error"]["code"] == "OAUTH_HANDOFF_INVALID"

	user = await user_repository.get_by_email(db_session, email)
	assert user is not None
	history = await login_history_repository.list_by_user_id(db_session, user.id)
	assert any(record.login_method == "oauth_google" for record in history)


async def test_callback_rejects_state_cookie_mismatch_without_creating_user(
	monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession
) -> None:
	"""`cerberus_oauth_state`Cookieの値を開始時に発行されたstateと異なる値へ改ざんした場合、
	callbackが`error=invalid_state`へリダイレクトし、ユーザーが作成されないことを検証する。
	"""
	app = _configure(
		monkeypatch, db_session, auth_mode="session", jwks_uri="https://jwks.example.test/certs/state-mismatch"
	)
	_sub, email = _new_identity()
	async with _client(app) as client:
		state, _nonce, _code_challenge = await _start_and_capture_state(client)
		client.cookies.set("cerberus_oauth_state", "tampered-state")

		callback = await client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": state})

		assert callback.status_code == 302
		assert callback.headers["location"] == f"{FRONTEND_BASE_URL}/login?error=invalid_state"

	assert await user_repository.get_by_email(db_session, email) is None


async def test_callback_rejects_nonce_mismatch_without_creating_user(
	monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession
) -> None:
	"""IDトークンに、開始時に発行したnonceと異なる値（"unexpected-nonce"）を埋め込んだ場合、
	callbackが`error=oauth_failed`へリダイレクトし、ユーザーが作成されないことを検証する。
	"""
	app = _configure(
		monkeypatch, db_session, auth_mode="session", jwks_uri="https://jwks.example.test/certs/nonce-mismatch"
	)
	client_id = get_backend_settings().google_client_id
	sub, email = _new_identity()
	async with _client(app) as client:
		state, _nonce, _code_challenge = await _start_and_capture_state(client)
		token, jwks = _signed_id_token(client_id, "unexpected-nonce", sub=sub, email=email)
		boundary = _GoogleBoundary({"id_token": token, "access_token": "access-token"}, _userinfo(sub, email), jwks)
		monkeypatch.setattr(
			oauth_router_module.oauth_service,
			"GoogleOAuthProvider",
			lambda settings: GoogleOAuthProvider(settings, boundary),
		)

		callback = await client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": state})

		assert callback.status_code == 302
		assert callback.headers["location"] == f"{FRONTEND_BASE_URL}/login?error=oauth_failed"

	assert await user_repository.get_by_email(db_session, email) is None


async def test_callback_rejects_userinfo_sub_mismatch_without_creating_user(
	monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession
) -> None:
	"""IDトークンの`sub`とuserinfoエンドポイントが返す`sub`が一致しない場合、
	callbackが`error=oauth_failed`へリダイレクトし、ユーザーが作成されないことを検証する。
	"""
	app = _configure(
		monkeypatch, db_session, auth_mode="session", jwks_uri="https://jwks.example.test/certs/sub-mismatch"
	)
	client_id = get_backend_settings().google_client_id
	sub, email = _new_identity()
	wrong_sub, _wrong_email = _new_identity()
	async with _client(app) as client:
		state, nonce, _code_challenge = await _start_and_capture_state(client)
		token, jwks = _signed_id_token(client_id, nonce, sub=sub, email=email)
		boundary = _GoogleBoundary(
			{"id_token": token, "access_token": "access-token"}, _userinfo(wrong_sub, email), jwks
		)
		monkeypatch.setattr(
			oauth_router_module.oauth_service,
			"GoogleOAuthProvider",
			lambda settings: GoogleOAuthProvider(settings, boundary),
		)

		callback = await client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": state})

		assert callback.status_code == 302
		assert callback.headers["location"] == f"{FRONTEND_BASE_URL}/login?error=oauth_failed"

	assert await user_repository.get_by_email(db_session, email) is None


async def test_callback_fails_closed_when_google_token_endpoint_is_unavailable(
	monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession
) -> None:
	"""Google tokenエンドポイントが503を返す場合、callbackが`error=oauth_failed`へ
	リダイレクトしフェイルクローズすること、失敗時点でstateが既に消費されているため
	同一stateでの再試行が`error=invalid_state`になること、ユーザーが作成されないことを検証する。
	"""
	app = _configure(
		monkeypatch, db_session, auth_mode="session", jwks_uri="https://jwks.example.test/certs/token-down"
	)
	_sub, email = _new_identity()
	async with _client(app) as client:
		state, _nonce, _code_challenge = await _start_and_capture_state(client)
		boundary = _GoogleBoundary(token_status=503)
		monkeypatch.setattr(
			oauth_router_module.oauth_service,
			"GoogleOAuthProvider",
			lambda settings: GoogleOAuthProvider(settings, boundary),
		)

		callback = await client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": state})

		assert callback.status_code == 302
		assert callback.headers["location"] == f"{FRONTEND_BASE_URL}/login?error=oauth_failed"

		# stateはcallback失敗時も消費済みのため、同一stateでの再試行は成立しない。
		client.cookies.set("cerberus_oauth_state", state)
		replay = await client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": state})
		assert replay.headers["location"] == f"{FRONTEND_BASE_URL}/login?error=invalid_state"

	assert await user_repository.get_by_email(db_session, email) is None


async def test_callback_fails_closed_when_google_jwks_endpoint_is_unavailable(
	monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession
) -> None:
	"""Google JWKSエンドポイントが503を返す場合、callbackが`error=oauth_failed`へ
	リダイレクトしフェイルクローズし、ユーザーが作成されないことを検証する。
	"""
	app = _configure(monkeypatch, db_session, auth_mode="session", jwks_uri="https://jwks.example.test/certs/jwks-down")
	_sub, email = _new_identity()
	async with _client(app) as client:
		state, _nonce, _code_challenge = await _start_and_capture_state(client)
		boundary = _GoogleBoundary({"id_token": "irrelevant", "access_token": "access-token"}, jwks_status=503)
		monkeypatch.setattr(
			oauth_router_module.oauth_service,
			"GoogleOAuthProvider",
			lambda settings: GoogleOAuthProvider(settings, boundary),
		)

		callback = await client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": state})

		assert callback.status_code == 302
		assert callback.headers["location"] == f"{FRONTEND_BASE_URL}/login?error=oauth_failed"

	assert await user_repository.get_by_email(db_session, email) is None


async def test_start_normalizes_disallowed_redirect_to_across_the_full_roundtrip(
	monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession
) -> None:
	"""開始時に外部ドメインへの`redirect_to`（"https://evil.example/steal"）を指定しても、
	その値がstateへ紐づいたままcallbackまで往復し、最終的には安全な既定値
	"/dashboard"へ正規化されてリダイレクトされることを検証する。
	"""
	app = _configure(
		monkeypatch, db_session, auth_mode="session", jwks_uri="https://jwks.example.test/certs/redirect-guard"
	)
	client_id = get_backend_settings().google_client_id
	sub, email = _new_identity()
	async with _client(app) as client:
		state, nonce, _code_challenge = await _start_and_capture_state(client, "https://evil.example/steal")
		token, jwks = _signed_id_token(client_id, nonce, sub=sub, email=email)
		boundary = _GoogleBoundary({"id_token": token, "access_token": "access-token"}, _userinfo(sub, email), jwks)
		monkeypatch.setattr(
			oauth_router_module.oauth_service,
			"GoogleOAuthProvider",
			lambda settings: GoogleOAuthProvider(settings, boundary),
		)

		callback = await client.get("/api/auth/oauth/google/callback", params={"code": "auth-code", "state": state})

		assert callback.status_code == 302
		assert callback.headers["location"] == f"{FRONTEND_BASE_URL}/oauth/callback#redirect_to=/dashboard"
