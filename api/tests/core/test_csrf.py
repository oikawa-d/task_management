"""app.core.deps のOrigin検証(verify_origin系)・CSRFトークン検証(verify_csrf系)、
および app.core.security.csrf_tokens_match に対する単体テスト。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.core import security
from app.core.deps import (
	_origin_from_referer,
	verify_csrf,
	verify_csrf_if_session,
	verify_origin,
	verify_origin_if_session,
)
from app.core.exceptions import CsrfInvalidError
from starlette.requests import Request


def _settings(
	*,
	cors_allow_origins: list[str] | None = None,
	csrf_trust_referer_on_https: bool = False,
	cookie_name_session: str = "cerberus_sid",
	cookie_name_csrf: str = "cerberus_csrf",
) -> SimpleNamespace:
	"""verify_origin系・verify_csrf系が参照する設定値のうち、テストに必要な項目だけを持つダミー設定を作る。

	Args:
		cors_allow_origins: 許可オリジンの一覧。Noneの場合は"http://localhost:5173"のみを許可する。
		csrf_trust_referer_on_https: HTTPS時にOriginヘッダー欠如をRefererヘッダーで代替検証するか。
		cookie_name_session: セッションCookie名。
		cookie_name_csrf: CSRFトークンCookie名。

	Returns:
		対象関数が要求する属性のみを持つSimpleNamespace（BackendSettingsの代わりに渡す）。
	"""
	return SimpleNamespace(
		cors_allow_origins=cors_allow_origins if cors_allow_origins is not None else ["http://localhost:5173"],
		csrf_trust_referer_on_https=csrf_trust_referer_on_https,
		cookie_name_session=cookie_name_session,
		cookie_name_csrf=cookie_name_csrf,
	)


def _strategy(mode: str) -> SimpleNamespace:
	"""認証モード（session/jwt）だけを持つダミーのAuthStrategyを作る。

	Args:
		mode: "session"または"jwt"。

	Returns:
		mode属性のみを持つSimpleNamespace。
	"""
	return SimpleNamespace(mode=mode)


def _request(
	*,
	scheme: str = "http",
	headers: dict[str, str] | None = None,
	cookies: dict[str, str] | None = None,
) -> Request:
	"""Origin/CSRF検証対象となる、POST /api/projects 宛のASGIリクエストを組み立てる。

	Args:
		scheme: リクエストスキーム（http/https）。RefererフォールバックはHTTPS限定のため区別する。
		headers: 付与するHTTPヘッダー（origin・referer・x-csrf-token等）。
		cookies: 付与するCookie（セッションID・CSRFトークン等）。

	Returns:
		指定した条件のRequestインスタンス。
	"""
	raw_headers: list[tuple[bytes, bytes]] = []
	for key, value in (headers or {}).items():
		raw_headers.append((key.lower().encode("latin-1"), value.encode("latin-1")))
	if cookies:
		cookie_header = "; ".join(f"{key}={value}" for key, value in cookies.items())
		raw_headers.append((b"cookie", cookie_header.encode("latin-1")))
	scope = {
		"type": "http",
		"method": "POST",
		"scheme": scheme,
		"path": "/api/projects",
		"headers": raw_headers,
		"query_string": b"",
		"server": ("testserver", 80),
		"client": ("testclient", 123),
	}
	return Request(scope)


class TestVerifyOrigin:
	"""verify_origin（Originヘッダー必須の厳格な検証）の許可/拒否・Refererフォールバックの挙動を検証する。"""

	async def test_allowed_origin_passes(self) -> None:
		"""OriginヘッダーがCORS許可オリジンと一致する場合、例外を送出せず検証を通過することを検証する。"""
		request = _request(headers={"origin": "http://localhost:5173"})

		await verify_origin(request, _settings())

	async def test_disallowed_origin_is_rejected(self) -> None:
		"""Originヘッダーが許可オリジンに含まれない場合、CsrfInvalidErrorを送出することを検証する。"""
		request = _request(headers={"origin": "http://evil.example"})

		with pytest.raises(CsrfInvalidError):
			await verify_origin(request, _settings())

	async def test_missing_origin_is_rejected_by_default(self) -> None:
		"""Originヘッダー・Refererヘッダーがいずれも無い場合、既定ではCsrfInvalidErrorを送出することを検証する。"""
		request = _request()

		with pytest.raises(CsrfInvalidError):
			await verify_origin(request, _settings())

	async def test_missing_origin_falls_back_to_referer_on_https_when_trusted(self) -> None:
		"""HTTPS接続かつcsrf_trust_referer_on_https=Trueの場合、Originヘッダー欠如時にRefererヘッダーから
		導出したオリジンで許可判定できることを検証する。
		"""
		request = _request(scheme="https", headers={"referer": "https://localhost:5173/dashboard"})
		settings = _settings(cors_allow_origins=["https://localhost:5173"], csrf_trust_referer_on_https=True)

		await verify_origin(request, settings)

	async def test_missing_origin_referer_fallback_rejects_mismatched_referer(self) -> None:
		"""Refererフォールバックが有効でも、導出したオリジンが許可オリジンと一致しない場合はCsrfInvalidErrorを
		送出することを検証する。
		"""
		request = _request(scheme="https", headers={"referer": "https://evil.example/x"})
		settings = _settings(cors_allow_origins=["https://localhost:5173"], csrf_trust_referer_on_https=True)

		with pytest.raises(CsrfInvalidError):
			await verify_origin(request, settings)

	async def test_referer_fallback_not_applied_on_plain_http_even_if_trusted(self) -> None:
		"""csrf_trust_referer_on_https=Trueであっても、接続がHTTP（非HTTPS）の場合はRefererフォールバックを
		適用せず、Originヘッダー欠如としてCsrfInvalidErrorを送出することを検証する。
		"""
		request = _request(scheme="http", headers={"referer": "http://localhost:5173/x"})
		settings = _settings(cors_allow_origins=["http://localhost:5173"], csrf_trust_referer_on_https=True)

		with pytest.raises(CsrfInvalidError):
			await verify_origin(request, settings)

	def test_origin_from_referer_extracts_scheme_and_host(self) -> None:
		"""_origin_from_refererがRefererのURLからクエリ・パスを除いたスキームとホストのみを抽出することを検証する。"""
		assert _origin_from_referer("https://example.com/path?x=1") == "https://example.com"

	def test_origin_from_referer_rejects_malformed_values(self) -> None:
		"""_origin_from_refererが空文字・None・URLとして解釈できない値に対して、例外を送出せずNoneを返すことを検証する。"""
		assert _origin_from_referer("") is None
		assert _origin_from_referer(None) is None
		assert _origin_from_referer("not-a-url") is None


class TestVerifyOriginIfSession:
	"""verify_origin_if_session（sessionモードのみOrigin検証を必須とする条件付き検証）の挙動を検証する。"""

	async def test_session_mode_requires_allowed_origin(self) -> None:
		"""sessionモードで許可オリジンのOriginヘッダーが付与されている場合、検証を通過することを検証する。"""
		request = _request(headers={"origin": "http://localhost:5173"})

		await verify_origin_if_session(request, _strategy("session"), _settings())

	async def test_session_mode_rejects_missing_origin(self) -> None:
		"""sessionモードでOriginヘッダーが無い場合、CsrfInvalidErrorを送出することを検証する。"""
		request = _request()

		with pytest.raises(CsrfInvalidError):
			await verify_origin_if_session(request, _strategy("session"), _settings())

	async def test_jwt_mode_skips_origin_check_without_header(self) -> None:
		"""jwtモードではOriginヘッダーが無くてもOrigin検証自体をスキップし、例外を送出しないことを検証する。"""
		request = _request()

		await verify_origin_if_session(request, _strategy("jwt"), _settings())


class TestVerifyCsrfSessionMode:
	"""verify_csrf（必須のCSRF検証）のsessionモードにおける、ヘッダー・Cookie・Redis保存値の突合の挙動を検証する。"""

	async def test_matching_cookie_header_and_redis_value_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
		"""x-csrf-tokenヘッダーとRedisに保存されたトークンが一致する場合に検証を通過し、
		Redisへセッションcookie値をキーとして問い合わせていることを検証する。
		"""
		get_csrf_token = AsyncMock(return_value="token-123")
		monkeypatch.setattr("app.core.deps.redis_store.get_csrf_token", get_csrf_token)
		request = _request(headers={"x-csrf-token": "token-123"}, cookies={"cerberus_sid": "sid-1"})

		await verify_csrf(request, _strategy("session"), _settings())

		get_csrf_token.assert_awaited_once_with("sid-1")

	async def test_missing_header_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
		"""x-csrf-tokenヘッダーが無い場合、Redisへ問い合わせる前にCsrfInvalidErrorを送出することを検証する。"""
		get_csrf_token = AsyncMock(return_value="token-123")
		monkeypatch.setattr("app.core.deps.redis_store.get_csrf_token", get_csrf_token)
		request = _request(cookies={"cerberus_sid": "sid-1"})

		with pytest.raises(CsrfInvalidError):
			await verify_csrf(request, _strategy("session"), _settings())
		get_csrf_token.assert_not_awaited()

	async def test_missing_session_cookie_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
		"""セッションCookieが無い場合、Redisへ問い合わせる前にCsrfInvalidErrorを送出することを検証する。"""
		get_csrf_token = AsyncMock(return_value="token-123")
		monkeypatch.setattr("app.core.deps.redis_store.get_csrf_token", get_csrf_token)
		request = _request(headers={"x-csrf-token": "token-123"})

		with pytest.raises(CsrfInvalidError):
			await verify_csrf(request, _strategy("session"), _settings())
		get_csrf_token.assert_not_awaited()

	async def test_redis_value_mismatch_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
		"""ヘッダーのトークンとRedis保存値が一致しない場合、CsrfInvalidErrorを送出することを検証する。"""
		monkeypatch.setattr("app.core.deps.redis_store.get_csrf_token", AsyncMock(return_value="other-token"))
		request = _request(headers={"x-csrf-token": "token-123"}, cookies={"cerberus_sid": "sid-1"})

		with pytest.raises(CsrfInvalidError):
			await verify_csrf(request, _strategy("session"), _settings())

	async def test_missing_redis_value_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
		"""Redisにトークンが保存されていない（None）場合、CsrfInvalidErrorを送出することを検証する。"""
		monkeypatch.setattr("app.core.deps.redis_store.get_csrf_token", AsyncMock(return_value=None))
		request = _request(headers={"x-csrf-token": "token-123"}, cookies={"cerberus_sid": "sid-1"})

		with pytest.raises(CsrfInvalidError):
			await verify_csrf(request, _strategy("session"), _settings())


class TestVerifyCsrfJwtMode:
	"""verify_csrfのjwtモードにおける、CSRF用Cookieとヘッダーの直接比較（Redis非経由）の挙動を検証する。"""

	async def test_matching_cookie_and_header_passes_without_redis_access(
		self, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""jwtモードではx-csrf-tokenヘッダーとcerberus_csrf Cookieの値が一致すれば検証を通過し、
		Redisへは一切問い合わせないことを検証する。
		"""
		get_csrf_token = AsyncMock()
		monkeypatch.setattr("app.core.deps.redis_store.get_csrf_token", get_csrf_token)
		request = _request(headers={"x-csrf-token": "token-abc"}, cookies={"cerberus_csrf": "token-abc"})

		await verify_csrf(request, _strategy("jwt"), _settings())

		get_csrf_token.assert_not_awaited()

	async def test_cookie_header_mismatch_is_rejected(self) -> None:
		"""jwtモードでヘッダーとCookieの値が一致しない場合、CsrfInvalidErrorを送出することを検証する。"""
		request = _request(headers={"x-csrf-token": "token-abc"}, cookies={"cerberus_csrf": "token-xyz"})

		with pytest.raises(CsrfInvalidError):
			await verify_csrf(request, _strategy("jwt"), _settings())

	async def test_missing_csrf_cookie_is_rejected(self) -> None:
		"""jwtモードでcerberus_csrf Cookieが無い場合、CsrfInvalidErrorを送出することを検証する。"""
		request = _request(headers={"x-csrf-token": "token-abc"})

		with pytest.raises(CsrfInvalidError):
			await verify_csrf(request, _strategy("jwt"), _settings())


class TestVerifyCsrfIfSessionForNormalApi:
	"""tasks/projects/comments等の通常APIが使う verify_csrf_if_session の認証方式別挙動。

	docs/detailed_design/auth/03_csrf.md §6: 通常APIのCSRF検証はsessionモードのみ必須、
	jwtモードでは検証自体を行わない。
	"""

	async def test_session_mode_matching_token_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
		"""sessionモードでヘッダーとRedis保存値が一致する場合に検証を通過し、
		Redisへセッションcookie値をキーとして問い合わせていることを検証する。
		"""
		get_csrf_token = AsyncMock(return_value="token-123")
		monkeypatch.setattr("app.core.deps.redis_store.get_csrf_token", get_csrf_token)
		request = _request(headers={"x-csrf-token": "token-123"}, cookies={"cerberus_sid": "sid-1"})

		await verify_csrf_if_session(request, _strategy("session"), _settings())

		get_csrf_token.assert_awaited_once_with("sid-1")

	async def test_session_mode_missing_header_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
		"""sessionモードでx-csrf-tokenヘッダーが無い場合、CsrfInvalidErrorを送出することを検証する。"""
		monkeypatch.setattr("app.core.deps.redis_store.get_csrf_token", AsyncMock(return_value="token-123"))
		request = _request(cookies={"cerberus_sid": "sid-1"})

		with pytest.raises(CsrfInvalidError):
			await verify_csrf_if_session(request, _strategy("session"), _settings())

	async def test_jwt_mode_skips_verification_even_without_header_or_cookie(
		self, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""jwtモードではヘッダー・Cookieが共に無くても検証自体をスキップし、
		例外を送出せずRedisへも問い合わせないことを検証する。
		"""
		get_csrf_token = AsyncMock()
		monkeypatch.setattr("app.core.deps.redis_store.get_csrf_token", get_csrf_token)
		request = _request()

		await verify_csrf_if_session(request, _strategy("jwt"), _settings())

		get_csrf_token.assert_not_awaited()

	async def test_jwt_mode_skips_verification_even_with_mismatched_cookie(self) -> None:
		"""jwtモードではヘッダーとCookieの値が一致しなくても検証自体をスキップし、例外を送出しないことを検証する。"""
		request = _request(headers={"x-csrf-token": "token-abc"}, cookies={"cerberus_csrf": "token-xyz"})

		await verify_csrf_if_session(request, _strategy("jwt"), _settings())


class TestCsrfTokensMatch:
	"""app.core.security.csrf_tokens_match（タイミング攻撃に配慮したトークン比較関数）の挙動を検証する。"""

	def test_equal_tokens_match(self) -> None:
		"""同一のトークン文字列同士を比較した場合、Trueを返すことを検証する。"""
		assert security.csrf_tokens_match("same-token", "same-token") is True

	def test_different_tokens_do_not_match(self) -> None:
		"""異なるトークン文字列を比較した場合、Falseを返すことを検証する。"""
		assert security.csrf_tokens_match("token-a", "token-b") is False
