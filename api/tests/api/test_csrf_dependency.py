"""core/deps.py の verify_origin / verify_csrf をHTTP層まで通した結合テスト。

app.main の実アプリではプロジェクト作成等がDB/Redisに依存するため、
CSRF検証の依存関係(DI)配線のみを対象にした最小限のFastAPIアプリを都度組み立てて検証する。
- 安全なmethod(GET)にはCSRF依存が配線されないこと（既存routerと同じ配線パターン）
- 更新系(POST等)はverify_origin/verify_csrfの両方が揃って初めて通過すること
- OAuth callback(GET/ブラウザリダイレクト)とOAuth exchange相当(POST、ログイン前でCSRF Cookie未発行)は
  verify_originのみが適用され、verify_csrfは適用されない例外パターンであること
  (`docs/detailed_design/auth/03_csrf.md` §6, §12: ログイン・OAuth交換はCSRF検証対象外)
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from app.auth.factory import get_auth_strategy
from app.core.deps import verify_csrf, verify_origin
from app.core.exceptions import register_error_handling
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

ALLOWED_ORIGIN = "http://localhost:5173"


def _build_app() -> FastAPI:
	app = FastAPI()
	register_error_handling(app)

	@app.get("/safe")
	async def safe_endpoint() -> dict[str, Any]:
		return {"ok": True}

	@app.post("/protected", dependencies=[Depends(verify_origin), Depends(verify_csrf)])
	async def protected_endpoint() -> dict[str, Any]:
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
	monkeypatch.setenv("CORS_ALLOW_ORIGINS", ALLOWED_ORIGIN)
	app = _build_app()
	app.dependency_overrides[get_auth_strategy] = lambda: SimpleNamespace(mode="jwt")
	with TestClient(app) as test_client:
		yield test_client
	app.dependency_overrides.clear()


def test_safe_method_get_does_not_require_origin_or_csrf(client: TestClient) -> None:
	res = client.get("/safe")

	assert res.status_code == 200


def test_protected_post_passes_with_matching_origin_and_csrf(client: TestClient) -> None:
	client.cookies.set("cerberus_csrf", "token-abc")
	res = client.post(
		"/protected",
		headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": "token-abc"},
	)

	assert res.status_code == 200


def test_protected_post_rejects_missing_csrf_header(client: TestClient) -> None:
	client.cookies.set("cerberus_csrf", "token-abc")
	res = client.post(
		"/protected",
		headers={"Origin": ALLOWED_ORIGIN},
	)

	assert res.status_code == 403
	assert res.json()["error"]["code"] == "CSRF_INVALID"


def test_protected_post_rejects_mismatched_csrf_token(client: TestClient) -> None:
	client.cookies.set("cerberus_csrf", "token-abc")
	res = client.post(
		"/protected",
		headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": "wrong-token"},
	)

	assert res.status_code == 403
	assert res.json()["error"]["code"] == "CSRF_INVALID"


def test_protected_post_rejects_disallowed_origin(client: TestClient) -> None:
	client.cookies.set("cerberus_csrf", "token-abc")
	res = client.post(
		"/protected",
		headers={"Origin": "http://evil.example", "X-CSRF-Token": "token-abc"},
	)

	assert res.status_code == 403
	assert res.json()["error"]["code"] == "CSRF_INVALID"


def test_protected_post_rejects_missing_origin(client: TestClient) -> None:
	client.cookies.set("cerberus_csrf", "token-abc")
	res = client.post(
		"/protected",
		headers={"X-CSRF-Token": "token-abc"},
	)

	assert res.status_code == 403
	assert res.json()["error"]["code"] == "CSRF_INVALID"


def test_oauth_callback_get_is_exempt_from_csrf_and_origin_checks(client: TestClient) -> None:
	"""GoogleからのリダイレクトはOriginヘッダを持たないブラウザ遷移のため検証対象外。"""
	res = client.get("/oauth/callback")

	assert res.status_code == 200


def test_oauth_exchange_post_passes_with_origin_only_no_csrf_header_required(client: TestClient) -> None:
	res = client.post("/oauth/exchange", headers={"Origin": ALLOWED_ORIGIN})

	assert res.status_code == 200


def test_oauth_exchange_post_still_rejects_disallowed_origin(client: TestClient) -> None:
	res = client.post("/oauth/exchange", headers={"Origin": "http://evil.example"})

	assert res.status_code == 403
	assert res.json()["error"]["code"] == "CSRF_INVALID"
