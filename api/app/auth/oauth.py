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


@dataclass(frozen=True)
class OAuthTokenResponse:
	id_token: str
	access_token: str


@dataclass(frozen=True)
class IdTokenClaims:
	sub: str
	email: str
	email_verified: bool
	given_name: str | None
	family_name: str | None


@dataclass(frozen=True)
class GoogleUserInfo:
	sub: str
	email: str
	email_verified: bool
	given_name: str | None = None
	family_name: str | None = None


class OAuthHttpResponse(Protocol):
	status_code: int

	def json(self) -> dict[str, Any]: ...


class OAuthHttpClient(Protocol):
	async def post(self, url: str, *, data: dict[str, str]) -> OAuthHttpResponse: ...

	async def get(self, url: str, *, headers: dict[str, str] | None = None) -> OAuthHttpResponse: ...


_jwks_cache: tuple[str, dict[str, Any], float] | None = None


class GoogleOAuthProvider:
	def __init__(self, settings: BackendSettings | None = None, http_client: OAuthHttpClient | None = None) -> None:
		self.settings = settings or get_backend_settings()
		self._http_client = http_client

	def build_authorize_url(self, state: str, code_challenge: str, nonce: str) -> str:
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
			logger.warning("OAuth token exchange failed", extra={"operation": "token_exchange"})
			raise
		except Exception as exc:
			logger.warning("OAuth token exchange failed", extra={"operation": "token_exchange"})
			raise OAuthFailedError() from exc

	async def fetch_userinfo(self, access_token: str) -> GoogleUserInfo:
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
			logger.warning("OAuth userinfo request failed", extra={"operation": "userinfo"})
			raise
		except Exception as exc:
			logger.warning("OAuth userinfo request failed", extra={"operation": "userinfo"})
			raise OAuthFailedError() from exc

	async def verify_id_token(self, id_token: str, expected_nonce: str) -> IdTokenClaims:
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
			logger.warning("OAuth ID token verification failed", extra={"operation": "id_token_verify"})
			raise OAuthFailedError() from exc

	async def _get_jwks(self) -> dict[str, Any]:
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
			logger.warning("OAuth JWKS request failed", extra={"operation": "jwks"})
			raise OAuthFailedError() from exc

	async def _verify_id_token(self, id_token: str, expected_nonce: str) -> IdTokenClaims:
		return await self.verify_id_token(id_token, expected_nonce)

	async def _post(self, url: str, *, data: dict[str, str]) -> OAuthHttpResponse:
		if self._http_client is not None:
			return await self._http_client.post(url, data=data)
		async with httpx.AsyncClient() as client:
			return cast(OAuthHttpResponse, await client.post(url, data=data))

	async def _get(self, url: str, *, headers: dict[str, str] | None = None) -> OAuthHttpResponse:
		if self._http_client is not None:
			return await self._http_client.get(url, headers=headers)
		async with httpx.AsyncClient() as client:
			return cast(OAuthHttpResponse, await client.get(url, headers=headers))


def _required_string(value: dict[str, Any], key: str) -> str:
	result = value.get(key)
	if not isinstance(result, str) or not result:
		raise ValueError(f"missing OAuth value: {key}")
	return result


def _validate_audience(claims: dict[str, Any], client_id: str) -> None:
	audience = claims.get("aud")
	if isinstance(audience, str):
		if audience != client_id:
			raise ValueError("unexpected audience")
		return
	if not isinstance(audience, list) or not all(isinstance(value, str) for value in audience):
		raise ValueError("invalid audience")
	if client_id not in audience:
		raise ValueError("unexpected audience")
	if len(audience) > 1 and claims.get("azp") != client_id:
		raise ValueError("unexpected authorized party")


def _optional_string(value: dict[str, Any], key: str) -> str | None:
	result = value.get(key)
	return result if isinstance(result, str) else None
