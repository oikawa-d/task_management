import asyncio
import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlencode, urlsplit
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

import jwt
from fastapi import Request, Response

from app.core.config import BackendSettings, get_backend_settings
from app.core.exceptions import (
	InvalidStateError,
	NotSupportedInModeError,
	OAuthEmailUnverifiedError,
	OAuthFailedError,
	OAuthHandoffInvalidError,
	ServiceUnavailableError,
	UserInactiveError,
)
from app.repository import login_history_repository as default_login_history_repository
from app.repository import oauth_account_repository as default_oauth_account_repository
from app.repository import oauth_handoff_repository, oauth_state_repository
from app.repository import user_repository as default_user_repository
from app.schemas.oauth import OAuthCallbackResult, OAuthExchangeResponse, OAuthStartResult


@dataclass(frozen=True)
class OAuthTokenResponse:
	id_token: str
	access_token: str


@dataclass(frozen=True)
class OAuthIdTokenClaims:
	sub: str
	email: str
	email_verified: bool
	given_name: str | None
	family_name: str | None


@dataclass(frozen=True)
class OAuthUserInfo:
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


class _UrlResponse:
	def __init__(self, status_code: int, body: bytes) -> None:
		self.status_code = status_code
		self._body = body

	def json(self) -> dict[str, Any]:
		value = json.loads(self._body)
		if not isinstance(value, dict):
			raise ValueError("OAuth response must be an object")
		return value


class _UrlHttpClient:
	async def post(self, url: str, *, data: dict[str, str]) -> OAuthHttpResponse:
		encoded = urlencode(data).encode()
		return await asyncio.to_thread(self._request, "POST", url, encoded, None)

	async def get(self, url: str, *, headers: dict[str, str] | None = None) -> OAuthHttpResponse:
		return await asyncio.to_thread(self._request, "GET", url, None, headers)

	@staticmethod
	def _request(method: str, url: str, body: bytes | None, headers: dict[str, str] | None) -> _UrlResponse:
		request = UrlRequest(url, data=body, headers=headers or {}, method=method)
		try:
			with urlopen(request, timeout=10) as response:
				return _UrlResponse(response.status, response.read())
		except Exception as exc:
			raise OAuthFailedError() from exc


class GoogleOAuthProvider:
	def __init__(self, settings: BackendSettings | None = None, http_client: OAuthHttpClient | None = None) -> None:
		self._settings = settings or get_backend_settings()
		self._http = http_client or _UrlHttpClient()
		self._jwks: dict[str, Any] | None = None
		self._jwks_expires_at = 0.0

	def build_authorize_url(self, state: str, code_challenge: str, nonce: str) -> str:
		query = urlencode(
			{
				"client_id": self._settings.google_client_id,
				"redirect_uri": self._settings.google_redirect_uri,
				"response_type": "code",
				"scope": "openid email profile",
				"state": state,
				"code_challenge": code_challenge,
				"code_challenge_method": "S256",
				"nonce": nonce,
				"prompt": self._settings.google_oauth_prompt,
			}
		)
		return f"{self._settings.google_authorize_endpoint}?{query}"

	async def exchange_code(self, code: str, code_verifier: str) -> OAuthTokenResponse:
		response = await self._http.post(
			self._settings.google_token_endpoint,
			data={
				"code": code,
				"code_verifier": code_verifier,
				"client_id": self._settings.google_client_id,
				"client_secret": self._settings.google_client_secret,
				"redirect_uri": self._settings.google_redirect_uri,
				"grant_type": "authorization_code",
			},
		)
		if response.status_code >= 400:
			raise OAuthFailedError()
		try:
			body = response.json()
			id_token = body["id_token"]
			access_token = body["access_token"]
		except (KeyError, TypeError, ValueError) as exc:
			raise OAuthFailedError() from exc
		if not isinstance(id_token, str) or not isinstance(access_token, str):
			raise OAuthFailedError()
		return OAuthTokenResponse(id_token=id_token, access_token=access_token)

	async def fetch_userinfo(self, access_token: str) -> OAuthUserInfo:
		response = await self._http.get(
			self._settings.google_userinfo_endpoint,
			headers={"Authorization": f"Bearer {access_token}"},
		)
		if response.status_code >= 400:
			raise OAuthFailedError()
		try:
			body = response.json()
			return OAuthUserInfo(
				sub=_required_string(body, "sub"),
				email=_required_string(body, "email"),
				email_verified=body["email_verified"] is True,
				given_name=_optional_string(body, "given_name"),
				family_name=_optional_string(body, "family_name"),
			)
		except (KeyError, TypeError, ValueError) as exc:
			raise OAuthFailedError() from exc

	async def verify_id_token(self, id_token: str, expected_nonce: str) -> OAuthIdTokenClaims:
		try:
			header = jwt.get_unverified_header(id_token)
			if header.get("alg") != "RS256":
				raise ValueError("unexpected signing algorithm")
			key = await self._get_jwk(header.get("kid"))
			verified_key: Any = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key))
			claims = jwt.decode(
				id_token,
				verified_key,
				algorithms=["RS256"],
				audience=self._settings.google_client_id,
				options={"verify_iss": False},
			)
			if claims.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}:
				raise ValueError("unexpected issuer")
			if not secrets.compare_digest(str(claims.get("nonce", "")), expected_nonce):
				raise ValueError("nonce mismatch")
			return OAuthIdTokenClaims(
				sub=_required_string(claims, "sub"),
				email=_required_string(claims, "email"),
				email_verified=claims.get("email_verified") is True,
				given_name=_optional_string(claims, "given_name"),
				family_name=_optional_string(claims, "family_name"),
			)
		except Exception as exc:
			if isinstance(exc, OAuthFailedError):
				raise
			raise OAuthFailedError() from exc

	async def _get_jwk(self, key_id: object) -> dict[str, Any]:
		jwks = self._jwks
		if jwks is None or self._jwks_expires_at <= time.time():
			response = await self._http.get(self._settings.google_jwks_uri)
			if response.status_code >= 400:
				raise OAuthFailedError()
			body = response.json()
			if not isinstance(body.get("keys"), list):
				raise OAuthFailedError()
			self._jwks = body
			self._jwks_expires_at = time.time() + self._settings.google_jwks_cache_ttl_seconds
			jwks = body
		for candidate in jwks["keys"]:
			if isinstance(candidate, dict) and candidate.get("kid") == key_id:
				return candidate
		raise OAuthFailedError()


def _required_string(value: dict[str, Any], key: str) -> str:
	result = value.get(key)
	if not isinstance(result, str) or not result:
		raise ValueError(f"missing OAuth claim: {key}")
	return result


def _optional_string(value: dict[str, Any], key: str) -> str | None:
	result = value.get(key)
	return result if isinstance(result, str) else None


def normalize_redirect_to(raw: str | None, settings: BackendSettings | None = None) -> str:
	config = settings or get_backend_settings()
	if not raw:
		return config.oauth_default_redirect_to
	parsed = urlsplit(raw)
	if not raw.startswith("/") or raw.startswith("//") or parsed.scheme or parsed.netloc:
		return config.oauth_default_redirect_to
	return raw


class OAuthService:
	def __init__(
		self,
		db: Any,
		*,
		settings: BackendSettings | None = None,
		redis: Any = None,
		provider: GoogleOAuthProvider | None = None,
		state_repository: Any = oauth_state_repository,
		handoff_repository: Any = oauth_handoff_repository,
		users: Any = None,
		oauth_accounts: Any = None,
		login_history: Any = None,
		user_repository: Any = None,
		oauth_account_repository: Any = None,
		login_history_repository: Any = None,
		session_auth_service: Any = None,
		jwt_auth_service: Any = None,
	) -> None:
		self._db = db
		self._settings = settings or get_backend_settings()
		self._redis = redis
		self._provider = provider or GoogleOAuthProvider(self._settings)
		self._state_repository = state_repository
		self._handoff_repository = handoff_repository
		self._users = user_repository or users or default_user_repository
		self._oauth_accounts = oauth_account_repository or oauth_accounts or default_oauth_account_repository
		self._login_history = login_history_repository or login_history or default_login_history_repository
		self._session_auth = session_auth_service
		self._jwt_auth = jwt_auth_service

	async def oauth_start(self, redirect_to: str | None) -> OAuthStartResult:
		redirect = normalize_redirect_to(redirect_to, self._settings)
		state = secrets.token_urlsafe(32)
		verifier = secrets.token_urlsafe(64)
		nonce = secrets.token_urlsafe(32)
		challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
		try:
			await self._state_repository.save_oauth_state(
				state,
				redirect,
				verifier,
				nonce,
				self._settings.oauth_state_ttl_seconds,
				redis=self._redis,
			)
		except Exception as exc:
			raise ServiceUnavailableError() from exc
		return OAuthStartResult(
			authorize_url=self._provider.build_authorize_url(state, challenge, nonce),
			state=state,
		)

	async def oauth_callback(
		self,
		code: str,
		state: str,
		state_cookie: str | None,
		request: Request,
		response: Response,
	) -> OAuthCallbackResult:
		if not state or not state_cookie or not secrets.compare_digest(state, state_cookie):
			raise InvalidStateError()
		try:
			state_data = await self._state_repository.consume_oauth_state(state, redis=self._redis)
		except Exception as exc:
			raise ServiceUnavailableError() from exc
		if state_data is None or not code:
			raise InvalidStateError()
		tokens = await self._provider.exchange_code(code, state_data.code_verifier)
		claims = await self._provider.verify_id_token(tokens.id_token, state_data.nonce)
		userinfo = await self._provider.fetch_userinfo(tokens.access_token)
		if not secrets.compare_digest(claims.sub, userinfo.sub):
			raise OAuthFailedError()
		user = await self.resolve_or_create_user(userinfo)
		if self._settings.auth_mode == "session":
			if self._session_auth is None:
				raise OAuthFailedError()
			await self._session_auth.login(user, request, response)
			try:
				await self._record_login(user, request)
			except Exception as exc:
				raise ServiceUnavailableError() from exc
			response.delete_cookie(self._settings.cookie_name_oauth_state, path="/api/auth/oauth")
			return OAuthCallbackResult(auth_mode="session", redirect_to=state_data.redirect_to)
		handoff_code = secrets.token_urlsafe(32)
		try:
			await self._handoff_repository.save_oauth_handoff(
				handoff_code,
				user.id,
				state_data.redirect_to,
				self._settings.oauth_handoff_ttl_seconds,
				redis=self._redis,
			)
		except Exception as exc:
			raise ServiceUnavailableError() from exc
		response.delete_cookie(self._settings.cookie_name_oauth_state, path="/api/auth/oauth")
		return OAuthCallbackResult(auth_mode="jwt", redirect_to=state_data.redirect_to, handoff_code=handoff_code)

	async def resolve_or_create_user(self, userinfo: OAuthUserInfo) -> Any:
		account = await self._oauth_accounts.get_by_provider_identity(self._db, "google", userinfo.sub)
		if account is not None:
			return account.user or await self._users.get_by_id(self._db, account.user_id)
		existing = await self._users.get_by_email(self._db, userinfo.email)
		if existing is not None:
			if not userinfo.email_verified:
				raise OAuthEmailUnverifiedError()
			await self._oauth_accounts.upsert(self._db, existing.id, "google", userinfo.sub, userinfo.email)
			return existing
		if not userinfo.email_verified:
			raise OAuthEmailUnverifiedError()
		username = f"google_{hashlib.sha256(userinfo.sub.encode()).hexdigest()[:16]}"
		user_id = await self._users.create(self._db, username, userinfo.email, None)
		await self._oauth_accounts.upsert(self._db, user_id, "google", userinfo.sub, userinfo.email)
		if userinfo.given_name is not None or userinfo.family_name is not None:
			update_profile = getattr(self._users, "update_profile", None)
			if update_profile is not None:
				await update_profile(
					self._db,
					user_id,
					userinfo.family_name,
					userinfo.given_name,
					None,
					None,
					None,
				)
		user = await self._users.get_by_id(self._db, user_id)
		if user is None:
			raise OAuthFailedError()
		return user

	async def oauth_exchange(self, code: str, request: Request, response: Response) -> OAuthExchangeResponse:
		if self._settings.auth_mode != "jwt":
			raise NotSupportedInModeError()
		try:
			handoff = await self._handoff_repository.consume_oauth_handoff(code, redis=self._redis)
		except Exception as exc:
			raise ServiceUnavailableError() from exc
		if handoff is None:
			raise OAuthHandoffInvalidError()
		user = await self._users.get_by_id(self._db, handoff.user_id)
		if user is None or not user.is_active:
			raise UserInactiveError()
		if self._jwt_auth is None:
			raise OAuthFailedError()
		login_result = await self._jwt_auth.login(user, request, response)
		try:
			await self._record_login(user, request)
		except Exception as exc:
			raise ServiceUnavailableError() from exc
		return OAuthExchangeResponse(
			access_token=login_result.access_token,
			token_type="bearer",
			expires_in=login_result.expires_in,
			redirect_to=handoff.redirect_to,
		)

	async def _record_login(self, user: Any, request: Request) -> None:
		client_ip = request.client.host if request.client is not None else None
		await self._login_history.create(
			self._db,
			user_id=user.id,
			login_identifier=user.email,
			login_method="oauth_google",
			ip_address=client_ip,
			user_agent=request.headers.get("user-agent"),
			success=True,
			failure_reason=None,
		)
