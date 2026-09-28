"""core/deps.py の verify_origin / verify_csrf をHTTP層まで通した結合テスト。

app.main の実アプリではプロジェクト作成等がDB/Redisに依存するため、
CSRF検証の依存関係(DI)配線のみを対象にした最小限のFastAPIアプリを都度組み立てて検証する。
- 安全なmethod(GET)にはCSRF依存が配線されないこと（既存routerと同じ配線パターン）
- Cookie利用APIはverify_origin/verify_csrfの両方が揃って初めて通過すること
- 通常APIはverify_origin_if_session/verify_csrf_if_sessionでsessionモードだけ検証すること
- OAuth callback(GET/ブラウザリダイレクト)とOAuth exchange相当(POST、ログイン前でCSRF Cookie未発行)は
  verify_originのみが適用され、verify_csrfは適用されない例外パターンであること
  (`docs/detailed_design/auth/03_csrf.md` §6, §12: ログイン・OAuth交換はCSRF検証対象外)
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from app.auth.factory import get_auth_strategy
from app.core.deps import verify_csrf, verify_csrf_if_session, verify_origin, verify_origin_if_session
from app.core.exceptions import register_error_handling
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

ALLOWED_ORIGIN = "http://localhost:5173"


def _build_app() -> FastAPI:
	"""CSRF/Origin検証の配線パターンを再現した、DB/Redis非依存の最小限のFastAPIアプリを組み立てる。

	Returns:
		safe(GET・検証なし)・protected(POST・verify_origin+verify_csrf必須)・
		normal-protected(POST・sessionモードのみ必須)・oauth/callback(GET・検証なし)・
		oauth/exchange(POST・verify_originのみ)の各エンドポイントを持つFastAPIアプリ。
	"""
	app = FastAPI()
	register_error_handling(app)

	@app.get("/safe")
	async def safe_endpoint() -> dict[str, Any]:
		return {"ok": True}

	@app.post("/protected", dependencies=[Depends(verify_origin), Depends(verify_csrf)])
	async def protected_endpoint() -> dict[str, Any]:
		return {"ok": True}

	@app.post("/normal-protected", dependencies=[Depends(verify_origin_if_session), Depends(verify_csrf_if_session)])
	async def normal_protected_endpoint() -> dict[str, Any]:
		return {"ok": True}

	@app.get("/oauth/callback")
	async def oauth_callback_endpoint() -> dict[str, Any]:
		"""ブラウザからのリダイレクト(GET)。安全なmethodのためCSRF依存を配線しない。"""
		return {"ok": True}

	@app.post("/oauth/exchange", dependencies=[Depends(verify_origin)])
	async def oauth_exchange_endpoint() -> dict[str, Any]:
		"""ログイン成立前でCSRF Cookie未発行のためverify_originのみを適用する。"""
		return {"ok": True}

	return app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
	"""CORS許可オリジンを固定し、認証モードをjwtに固定したget_auth_strategyの依存関係オーバーライドを
	適用した状態で_build_appのアプリを起動するTestClientを提供する。
	後片付けとしてdependency_overridesをクリアする。
	"""
	monkeypatch.setenv("CORS_ALLOW_ORIGINS", ALLOWED_ORIGIN)
	app = _build_app()
	app.dependency_overrides[get_auth_strategy] = lambda: SimpleNamespace(mode="jwt")
	with TestClient(app) as test_client:
		yield test_client
	app.dependency_overrides.clear()


def test_safe_method_get_does_not_require_origin_or_csrf(client: TestClient) -> None:
	"""安全なmethod(GET)のエンドポイントはOrigin/CSRF検証が配線されておらず、
	ヘッダー・Cookie無しでも200で応答することを検証する。
	"""
	res = client.get("/safe")

	assert res.status_code == 200


def test_protected_post_passes_with_matching_origin_and_csrf(client: TestClient) -> None:
	"""許可オリジンのOriginヘッダーと、CSRF Cookieに一致するX-CSRF-Tokenヘッダーが揃っていれば、
	verify_origin+verify_csrf必須のエンドポイントが200で応答することを検証する。
	"""
	client.cookies.set("cerberus_csrf", "token-abc")
	res = client.post(
		"/protected",
		headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": "token-abc"},
	)

	assert res.status_code == 200


def test_protected_post_rejects_missing_csrf_header(client: TestClient) -> None:
	"""X-CSRF-Tokenヘッダーが無い場合、ステータス403・エラーコードCSRF_INVALIDで拒否されることを検証する。"""
	client.cookies.set("cerberus_csrf", "token-abc")
	res = client.post(
		"/protected",
		headers={"Origin": ALLOWED_ORIGIN},
	)

	assert res.status_code == 403
	assert res.json()["error"]["code"] == "CSRF_INVALID"


def test_protected_post_rejects_mismatched_csrf_token(client: TestClient) -> None:
	"""X-CSRF-Tokenヘッダーの値がCSRF Cookieの値と一致しない場合、
	ステータス403・エラーコードCSRF_INVALIDで拒否されることを検証する。
	"""
	client.cookies.set("cerberus_csrf", "token-abc")
	res = client.post(
		"/protected",
		headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": "wrong-token"},
	)

	assert res.status_code == 403
	assert res.json()["error"]["code"] == "CSRF_INVALID"


def test_protected_post_rejects_disallowed_origin(client: TestClient) -> None:
	"""Originヘッダーが許可オリジンに含まれない場合、ステータス403・エラーコードCSRF_INVALIDで
	拒否されることを検証する。
	"""
	client.cookies.set("cerberus_csrf", "token-abc")
	res = client.post(
		"/protected",
		headers={"Origin": "http://evil.example", "X-CSRF-Token": "token-abc"},
	)

	assert res.status_code == 403
	assert res.json()["error"]["code"] == "CSRF_INVALID"


def test_protected_post_rejects_missing_origin(client: TestClient) -> None:
	"""Originヘッダーが無い場合、ステータス403・エラーコードCSRF_INVALIDで拒否されることを検証する。"""
	client.cookies.set("cerberus_csrf", "token-abc")
	res = client.post(
		"/protected",
		headers={"X-CSRF-Token": "token-abc"},
	)

	assert res.status_code == 403
	assert res.json()["error"]["code"] == "CSRF_INVALID"


def test_jwt_normal_post_skips_origin_and_csrf_without_headers_or_cookies(client: TestClient) -> None:
	"""jwtモードでは、通常APIのverify_origin_if_session/verify_csrf_if_sessionが検証自体をスキップし、
	Origin/CSRFヘッダー・Cookieが無くても200で応答することを検証する。
	"""
	res = client.post("/normal-protected")

	assert res.status_code == 200


def test_oauth_callback_get_is_exempt_from_csrf_and_origin_checks(client: TestClient) -> None:
	"""GoogleからのリダイレクトはOriginヘッダを持たないブラウザ遷移のため検証対象外。"""
	res = client.get("/oauth/callback")

	assert res.status_code == 200


def test_oauth_exchange_post_passes_with_origin_only_no_csrf_header_required(client: TestClient) -> None:
	"""ログイン成立前のOAuth交換エンドポイントは許可オリジンのOriginヘッダーのみで通過し、
	CSRFトークンヘッダーが無くても200で応答する（verify_csrfは適用されない）ことを検証する。
	"""
	res = client.post("/oauth/exchange", headers={"Origin": ALLOWED_ORIGIN})

	assert res.status_code == 200


def test_oauth_exchange_post_still_rejects_disallowed_origin(client: TestClient) -> None:
	"""OAuth交換エンドポイントでもverify_originは適用されるため、許可されないOriginでは
	ステータス403・エラーコードCSRF_INVALIDで拒否されることを検証する。
	"""
	res = client.post("/oauth/exchange", headers={"Origin": "http://evil.example"})

	assert res.status_code == 403
	assert res.json()["error"]["code"] == "CSRF_INVALID"
