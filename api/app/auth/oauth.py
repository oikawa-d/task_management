"""Google OAuth2（Authorization Code + PKCE）のトークン交換・ユーザー情報取得・ID token検証。

認可コードの交換、userinfoエンドポイントからのプロフィール取得、GoogleのJWKSを用いた
ID tokenの署名・audience・issuer・nonce検証を行う。ネットワーク・検証エラーは
すべて`OAuthFailedError`（400 OAUTH_FAILED）に正規化して送出する。
"""

from __future__ import annotations

import json
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any, Protocol, cast
from urllib.parse import urlencode

import httpx2 as httpx
import jwt

from app.core.config import BackendSettings, get_backend_settings
from app.core.exceptions import OAuthFailedError

_GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
_GOOGLE_SCOPE = "openid email profile"
logger = logging.getLogger("app.oauth")


def _log_oauth_failure(operation: str) -> None:
	"""OAuth処理の失敗を、詳細情報を含めずイベント種別のみでログ出力する（機微情報の漏洩防止）。

	Args:
		operation: 失敗した処理を識別する文字列（例: `token_exchange`）。
	"""
	logger.warning(
		"OAuth operation failed",
		extra={"operation": operation, "event": "oauth_failure"},
	)


@dataclass(frozen=True)
class OAuthTokenResponse:
	"""Googleのtokenエンドポイントから取得した、認可コード交換結果。"""

	id_token: str
	access_token: str


@dataclass(frozen=True)
class IdTokenClaims:
	"""検証済みID tokenから取り出したクレーム。"""

	sub: str
	email: str
	email_verified: bool
	given_name: str | None
	family_name: str | None


@dataclass(frozen=True)
class GoogleUserInfo:
	"""Googleのuserinfoエンドポイントから取得したユーザープロフィール。"""

	sub: str
	email: str
	email_verified: bool
	given_name: str | None = None
	family_name: str | None = None


class OAuthHttpResponse(Protocol):
	"""テスト用のHTTPクライアント差し替えを可能にする、HTTPレスポンスの最小プロトコル。"""

	status_code: int

	def json(self) -> dict[str, Any]: ...


class OAuthHttpClient(Protocol):
	"""テスト用のHTTPクライアント差し替えを可能にする、HTTPクライアントの最小プロトコル。"""

	async def post(self, url: str, *, data: dict[str, str]) -> OAuthHttpResponse: ...

	async def get(self, url: str, *, headers: dict[str, str] | None = None) -> OAuthHttpResponse: ...


_jwks_cache: tuple[str, dict[str, Any], float] | None = None


class GoogleOAuthProvider:
	"""Google OAuth2の認可URL組み立て・トークン交換・userinfo取得・ID token検証を提供する。"""

	def __init__(self, settings: BackendSettings | None = None, http_client: OAuthHttpClient | None = None) -> None:
		"""設定とHTTPクライアントを保持して初期化する。

		Args:
			settings: Google OAuthのクライアントID・エンドポイント等の設定。未指定時はグローバル設定を使う。
			http_client: テスト用に差し替えるHTTPクライアント。未指定時は`httpx.AsyncClient`を都度生成する。
		"""
		self.settings = settings or get_backend_settings()
		self._http_client = http_client

	def build_authorize_url(self, state: str, code_challenge: str, nonce: str) -> str:
		"""PKCE・CSRF対策のstate・nonceを含む、Googleの認可エンドポイントURLを組み立てる。

		Args:
			state: CSRF対策用のランダム値（callbackで照合する）。
			code_challenge: PKCEのcode_challenge（S256方式）。
			nonce: ID tokenのリプレイ対策用のランダム値。

		Returns:
			ブラウザをリダイレクトさせるGoogleの認可URL。
		"""
		query = urlencode(
			{
				"client_id": self.settings.google_client_id,
				"redirect_uri": self.settings.google_redirect_uri,
				"response_type": "code",
				"scope": _GOOGLE_SCOPE,
				"state": state,
				"code_challenge": code_challenge,
				"code_challenge_method": "S256",
				"nonce": nonce,
				"prompt": self.settings.google_oauth_prompt,
			}
		)
		return f"{self.settings.google_authorize_endpoint}?{query}"

	async def exchange_code(self, code: str, code_verifier: str) -> OAuthTokenResponse:
		"""認可コードとPKCE code_verifierをGoogleのtokenエンドポイントでid/access tokenに交換する。

		Args:
			code: 認可コード（callbackで受け取ったもの）。
			code_verifier: 認可開始時に生成したPKCE code_verifier。

		Returns:
			id tokenとaccess tokenを含む`OAuthTokenResponse`。

		Raises:
			OAuthFailedError: Googleがエラー応答を返した場合、または通信・応答形式の異常時（400 OAUTH_FAILED）。
		"""
		try:
			response = await self._post(
				self.settings.google_token_endpoint,
				data={
					"code": code,
					"code_verifier": code_verifier,
					"client_id": self.settings.google_client_id,
					"client_secret": self.settings.google_client_secret,
					"redirect_uri": self.settings.google_redirect_uri,
					"grant_type": "authorization_code",
				},
			)
			if response.status_code >= 400:
				raise OAuthFailedError()
			body = response.json()
			return OAuthTokenResponse(_required_string(body, "id_token"), _required_string(body, "access_token"))
		except OAuthFailedError:
			_log_oauth_failure("token_exchange")
			raise
		except Exception as exc:
			_log_oauth_failure("token_exchange")
			raise OAuthFailedError() from exc

	async def fetch_userinfo(self, access_token: str) -> GoogleUserInfo:
		"""access tokenを用いてGoogleのuserinfoエンドポイントからプロフィールを取得する。

		Args:
			access_token: `exchange_code`で取得したaccess token。

		Returns:
			ユーザーのsub・email・email_verified等を含む`GoogleUserInfo`。

		Raises:
			OAuthFailedError: Googleがエラー応答を返した場合、または応答形式が不正な場合（400 OAUTH_FAILED）。
		"""
		try:
			response = await self._get(
				self.settings.google_userinfo_endpoint,
				headers={"Authorization": f"Bearer {access_token}"},
			)
			if response.status_code >= 400:
				raise OAuthFailedError()
			body = response.json()
			email_verified = body.get("email_verified")
			if not isinstance(email_verified, bool):
				raise ValueError("invalid email_verified claim")
			return GoogleUserInfo(
				_required_string(body, "sub"),
				_required_string(body, "email"),
				email_verified,
				_optional_string(body, "given_name"),
				_optional_string(body, "family_name"),
			)
		except OAuthFailedError:
			_log_oauth_failure("userinfo")
			raise
		except Exception as exc:
			_log_oauth_failure("userinfo")
			raise OAuthFailedError() from exc

	async def verify_id_token(self, id_token: str, expected_nonce: str) -> IdTokenClaims:
		"""GoogleのJWKSでID tokenの署名を検証し、audience・issuer・nonceの整合性を確認する。

		署名アルゴリズムはRS256のみを許容し、`aud`/`azp`がクライアントIDと一致すること、
		`iss`が既知のGoogle issuerであること、`nonce`が認可開始時に発行した値と
		一致することを検証する。

		Args:
			id_token: `exchange_code`で取得したID token。
			expected_nonce: 認可開始時に発行したnonce（定数時間比較で照合する）。

		Returns:
			検証済みクレームを含む`IdTokenClaims`。

		Raises:
			OAuthFailedError: 署名・audience・issuer・nonce・必須クレームのいずれかが不正な場合（400 OAUTH_FAILED）。
		"""
		try:
			header = jwt.get_unverified_header(id_token)
			if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
				raise ValueError("unexpected signing algorithm or key id")
			jwks = await self._get_jwks()
			jwk = next((key for key in jwks["keys"] if key.get("kid") == header["kid"]), None)
			if not isinstance(jwk, dict):
				raise ValueError("signing key not found")
			public_key: Any = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
			claims = jwt.decode(
				id_token,
				public_key,
				algorithms=["RS256"],
				audience=self.settings.google_client_id,
				options={"require": ["sub", "email", "email_verified", "iss", "aud", "exp", "nonce"]},
			)
			_validate_audience(claims, self.settings.google_client_id)
			if claims.get("iss") not in _GOOGLE_ISSUERS:
				raise ValueError("unexpected issuer")
			nonce = claims.get("nonce")
			if not isinstance(nonce, str) or not secrets.compare_digest(nonce, expected_nonce):
				raise ValueError("nonce mismatch")
			email_verified = claims["email_verified"]
			if not isinstance(email_verified, bool):
				raise ValueError("invalid email_verified claim")
			return IdTokenClaims(
				_required_string(claims, "sub"),
				_required_string(claims, "email"),
				email_verified,
				_optional_string(claims, "given_name"),
				_optional_string(claims, "family_name"),
			)
		except OAuthFailedError:
			raise
		except Exception as exc:
			_log_oauth_failure("id_token_verify")
			raise OAuthFailedError() from exc

	async def _get_jwks(self) -> dict[str, Any]:
		"""GoogleのJWKS（署名検証鍵集合）を取得する。プロセス内キャッシュがあればそれを使う。

		Returns:
			`keys`配列を含むJWKSのJSON。

		Raises:
			OAuthFailedError: JWKSの取得に失敗した場合、または応答形式が不正な場合（400 OAUTH_FAILED）。
		"""
		global _jwks_cache
		now = time.monotonic()
		if _jwks_cache is not None and _jwks_cache[0] == self.settings.google_jwks_uri and _jwks_cache[2] > now:
			return _jwks_cache[1]
		try:
			response = await self._get(self.settings.google_jwks_uri)
			if response.status_code >= 400:
				raise ValueError("JWKS request failed")
			body = response.json()
			keys = body.get("keys")
			if not isinstance(keys, list) or not all(isinstance(key, dict) for key in keys):
				raise ValueError("invalid JWKS")
			_jwks_cache = (self.settings.google_jwks_uri, body, now + self.settings.google_jwks_cache_ttl_seconds)
			return body
		except Exception as exc:
			_log_oauth_failure("jwks")
			raise OAuthFailedError() from exc

	async def _verify_id_token(self, id_token: str, expected_nonce: str) -> IdTokenClaims:
		"""`verify_id_token`への後方互換用の内部エイリアス。"""
		return await self.verify_id_token(id_token, expected_nonce)

	async def _post(self, url: str, *, data: dict[str, str]) -> OAuthHttpResponse:
		"""テスト用クライアントがあればそれを、無ければ`httpx.AsyncClient`でPOSTする。

		Args:
			url: リクエスト先URL。
			data: フォームエンコードするリクエストボディ。

		Returns:
			HTTPレスポンス。
		"""
		if self._http_client is not None:
			return await self._http_client.post(url, data=data)
		async with httpx.AsyncClient() as client:
			return cast(OAuthHttpResponse, await client.post(url, data=data))

	async def _get(self, url: str, *, headers: dict[str, str] | None = None) -> OAuthHttpResponse:
		"""テスト用クライアントがあればそれを、無ければ`httpx.AsyncClient`でGETする。

		Args:
			url: リクエスト先URL。
			headers: 付与するリクエストヘッダ。

		Returns:
			HTTPレスポンス。
		"""
		if self._http_client is not None:
			return await self._http_client.get(url, headers=headers)
		async with httpx.AsyncClient() as client:
			return cast(OAuthHttpResponse, await client.get(url, headers=headers))


def _required_string(value: dict[str, Any], key: str) -> str:
	"""辞書から必須の文字列フィールドを取り出す。空文字列や非文字列は不正値として扱う。

	Args:
		value: レスポンスボディ等の辞書。
		key: 取り出すフィールド名。

	Returns:
		取り出した文字列値。

	Raises:
		ValueError: フィールドが存在しない、文字列でない、または空文字列の場合。
	"""
	result = value.get(key)
	if not isinstance(result, str) or not result:
		raise ValueError(f"missing OAuth value: {key}")
	return result


def _validate_audience(claims: dict[str, Any], client_id: str) -> None:
	"""ID tokenの`aud`（audience）と`azp`（authorized party）がクライアントIDと一致するか検証する。

	Args:
		claims: 検証対象のID tokenクレーム。
		client_id: 自アプリケーションのGoogle OAuthクライアントID。

	Raises:
		ValueError: `aud`が不正な型・値の場合、または`azp`がクライアントIDと一致しない場合。
	"""
	audience = claims.get("aud")
	if isinstance(audience, str):
		if audience != client_id:
			raise ValueError("unexpected audience")
	elif isinstance(audience, list):
		if not audience or not all(isinstance(value, str) for value in audience):
			raise ValueError("invalid audience")
		if client_id not in audience:
			raise ValueError("unexpected audience")
	else:
		raise ValueError("invalid audience")
	azp = claims.get("azp")
	if azp is not None and (not isinstance(azp, str) or azp != client_id):
		raise ValueError("unexpected authorized party")
	if isinstance(audience, list) and len(audience) > 1 and azp != client_id:
		raise ValueError("unexpected authorized party")


def _optional_string(value: dict[str, Any], key: str) -> str | None:
	"""辞書から任意の文字列フィールドを取り出す。存在しない・文字列でない場合は`None`を返す。

	Args:
		value: レスポンスボディ等の辞書。
		key: 取り出すフィールド名。

	Returns:
		文字列値、または存在しない・型が異なる場合は`None`。
	"""
	result = value.get(key)
	return result if isinstance(result, str) else None
