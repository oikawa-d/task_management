"""Google OAuthの認可開始・callback・handoff交換のサービス。"""

from __future__ import annotations

import base64
import hashlib
import secrets
from typing import Any

from fastapi import Request, Response
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.factory import get_auth_strategy
from app.auth.jwt_auth import JwtAuthStrategy
from app.auth.oauth import GoogleOAuthProvider, GoogleUserInfo
from app.auth.session_auth import SessionAuthStrategy
from app.core.config import BackendSettings, get_backend_settings
from app.core.constants import TOKEN_URLSAFE_BYTES
from app.core.exceptions import (
	InvalidStateError,
	NotSupportedInModeError,
	OAuthEmailUnverifiedError,
	OAuthFailedError,
	OAuthHandoffInvalidError,
	ServiceUnavailableError,
	UserInactiveError,
	raise_database_error,
)
from app.models.user import User
from app.repository import login_history_repository as _login_history_repository
from app.repository import oauth_account_repository, redis_store, user_repository
from app.schemas.oauth import OAuthCallbackResult, OAuthExchangeResponse, OAuthStartResult
from app.service.auth_logging import log_login_history_write_failed
from app.service.oauth_support import (
	OAUTH_RATE_LIMIT_SCOPE,
	check_oauth_rate_limit,
	complete_oauth_session_login,
	delete_oauth_state_cookie,
	is_valid_jwt_login_result,
	normalize_redirect_to,
	record_oauth_login,
	rollback_oauth_login,
	set_oauth_state_cookie,
)

_record_oauth_login = record_oauth_login
login_history_repository = _login_history_repository


async def oauth_start(
	redirect_to: str | None,
	request: Request | Response | None = None,
	response: Response | None = None,
	*,
	settings: BackendSettings | None = None,
	provider: GoogleOAuthProvider | None = None,
) -> OAuthStartResult:
	config = settings or get_backend_settings()
	if isinstance(request, Request):
		await check_oauth_rate_limit(request, OAUTH_RATE_LIMIT_SCOPE["start"], "/api/auth/oauth/google", config)
	if isinstance(request, Response) and response is None:
		response = request
	redirect = normalize_redirect_to(redirect_to, config)
	state = secrets.token_urlsafe(TOKEN_URLSAFE_BYTES)
	code_verifier = secrets.token_urlsafe(64)
	nonce = secrets.token_urlsafe(TOKEN_URLSAFE_BYTES)
	code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).rstrip(b"=").decode()
	try:
		await redis_store.save_oauth_state(state, redirect, code_verifier, nonce, config.oauth_state_ttl_seconds)
	except Exception as exc:
		raise ServiceUnavailableError() from exc
	if response is not None:
		set_oauth_state_cookie(response, state, config)
	oauth_provider = provider or GoogleOAuthProvider(config)
	return OAuthStartResult(authorize_url=oauth_provider.build_authorize_url(state, code_challenge, nonce), state=state)


async def _resolve_or_create_user(db: AsyncSession, userinfo: GoogleUserInfo) -> User:
	account = await oauth_account_repository.get_by_provider_identity(db, "google", userinfo.sub)
	if account is not None:
		user = account.user or await user_repository.get_by_id(db, account.user_id)
		if user is None:
			raise OAuthFailedError()
		if not user.is_active:
			raise UserInactiveError()
		return user
	existing = await user_repository.get_by_email(db, userinfo.email)
	if existing is not None:
		if not userinfo.email_verified:
			raise OAuthEmailUnverifiedError()
		if not existing.is_active:
			raise UserInactiveError()
		try:
			await oauth_account_repository.upsert(db, existing.id, "google", userinfo.sub)
			if existing.email_verified_at is None:
				await user_repository.mark_email_verified(db, existing.id)
			await db.commit()
		except DBAPIError as exc:
			await db.rollback()
			raise_database_error(exc)
		return existing
	if not userinfo.email_verified:
		raise OAuthEmailUnverifiedError()
	username = f"google_{hashlib.sha256(userinfo.sub.encode()).hexdigest()[:16]}"
	try:
		user_id = await user_repository.create(db, username, userinfo.email, None)
		await oauth_account_repository.upsert(db, user_id, "google", userinfo.sub)
		await user_repository.mark_email_verified(db, user_id)
		if userinfo.given_name is not None or userinfo.family_name is not None:
			await user_repository.update_profile(
				db, user_id, userinfo.family_name, userinfo.given_name, None, None, None
			)
		await db.commit()
	except DBAPIError as exc:
		await db.rollback()
		raise_database_error(exc)
	user = await user_repository.get_by_id(db, user_id)
	if user is None:
		raise OAuthFailedError()
	if not user.is_active:
		raise UserInactiveError()
	return user


async def resolve_or_create_user(
	db: AsyncSession,
	sub: str,
	email: str,
	email_verified: bool,
	given_name: str | None,
	family_name: str | None,
) -> User:
	return await _resolve_or_create_user(db, GoogleUserInfo(sub, email, email_verified, given_name, family_name))


def _auth_strategy(settings: BackendSettings, strategy: Any | None) -> Any:
	if strategy is not None:
		return strategy
	configured = get_auth_strategy()
	if configured.mode == settings.auth_mode:
		return configured
	return SessionAuthStrategy(settings) if settings.auth_mode == "session" else JwtAuthStrategy(settings)


async def oauth_callback_denied(
	state: str | None,
	state_cookie: str | None,
	request: Request,
	response: Response,
	*,
	settings: BackendSettings | None = None,
) -> None:
	config = settings or get_backend_settings()
	try:
		await check_oauth_rate_limit(
			request, OAUTH_RATE_LIMIT_SCOPE["callback"], "/api/auth/oauth/google/callback", config
		)
		if not state or not state_cookie or not secrets.compare_digest(state, state_cookie):
			raise InvalidStateError()
		try:
			state_data = await redis_store.consume_oauth_state(state)
		except Exception as exc:
			raise ServiceUnavailableError() from exc
		if state_data is None:
			raise InvalidStateError()
	finally:
		delete_oauth_state_cookie(response, config)


async def _oauth_callback_impl(
	code: str | None,
	state: str | None,
	state_cookie: str | None,
	request: Request,
	response: Response,
	db: AsyncSession | None = None,
	*,
	settings: BackendSettings | None = None,
	provider: GoogleOAuthProvider | None = None,
	strategy: Any | None = None,
) -> OAuthCallbackResult:
	config = settings or get_backend_settings()
	client_info = await check_oauth_rate_limit(
		request, OAUTH_RATE_LIMIT_SCOPE["callback"], "/api/auth/oauth/google/callback", config
	)
	if not state or not state_cookie or not secrets.compare_digest(state, state_cookie):
		raise InvalidStateError()
	try:
		state_data = await redis_store.consume_oauth_state(state)
	except Exception as exc:
		raise ServiceUnavailableError() from exc
	if state_data is None:
		raise InvalidStateError()
	if not code or db is None:
		raise OAuthFailedError()
	oauth_provider = provider or GoogleOAuthProvider(config)
	tokens = await oauth_provider.exchange_code(code, state_data.code_verifier)
	claims = await oauth_provider.verify_id_token(tokens.id_token, state_data.nonce)
	userinfo = await oauth_provider.fetch_userinfo(tokens.access_token)
	if not secrets.compare_digest(claims.sub, userinfo.sub):
		raise OAuthFailedError()
	user = await _resolve_or_create_user(db, userinfo)
	if not user.is_active:
		raise UserInactiveError()
	if config.auth_mode == "session":
		configured_strategy = _auth_strategy(config, strategy)
		login_result = await configured_strategy.login(user, request, response)
		await complete_oauth_session_login(
			db, user, request, response, config, client_info, configured_strategy, login_result, _record_oauth_login
		)
		return OAuthCallbackResult(auth_mode="session", redirect_to=state_data.redirect_to)
	handoff_code = secrets.token_urlsafe(TOKEN_URLSAFE_BYTES)
	try:
		await redis_store.save_oauth_handoff(
			handoff_code, user.id, state_data.redirect_to, config.oauth_handoff_ttl_seconds
		)
	except Exception as exc:
		raise ServiceUnavailableError() from exc
	delete_oauth_state_cookie(response, config)
	return OAuthCallbackResult(auth_mode="jwt", redirect_to=state_data.redirect_to, handoff_code=handoff_code)


async def oauth_callback(
	code: str | None,
	state: str | None,
	state_cookie: str | None,
	request: Request,
	response: Response,
	db: AsyncSession | None = None,
	*,
	settings: BackendSettings | None = None,
	provider: GoogleOAuthProvider | None = None,
	strategy: Any | None = None,
) -> OAuthCallbackResult:
	config = settings or get_backend_settings()
	try:
		return await _oauth_callback_impl(
			code, state, state_cookie, request, response, db, settings=config, provider=provider, strategy=strategy
		)
	finally:
		delete_oauth_state_cookie(response, config)


async def oauth_exchange(
	code: str,
	request: Request,
	response: Response,
	db: AsyncSession | None = None,
	*,
	settings: BackendSettings | None = None,
	strategy: Any | None = None,
) -> OAuthExchangeResponse:
	config = settings or get_backend_settings()
	client_info = await check_oauth_rate_limit(
		request, OAUTH_RATE_LIMIT_SCOPE["exchange"], "/api/auth/oauth/exchange", config
	)
	if config.auth_mode != "jwt":
		raise NotSupportedInModeError()
	try:
		handoff = await redis_store.consume_oauth_handoff(code)
	except Exception as exc:
		raise ServiceUnavailableError() from exc
	if handoff is None:
		raise OAuthHandoffInvalidError()
	if db is None:
		raise OAuthFailedError()
	user = await user_repository.get_by_id(db, handoff.user_id)
	if user is None or not user.is_active:
		raise UserInactiveError()
	configured_strategy = _auth_strategy(config, strategy)
	login_result = await configured_strategy.login(user, request, response)
	if not is_valid_jwt_login_result(login_result):
		try:
			await rollback_oauth_login(
				configured_strategy,
				user,
				login_result,
				response,
				config,
				clear_state_cookie=False,
				request=request,
				client_info=client_info,
				operation="oauth_exchange_invalid_login_result",
			)
		except Exception as rollback_exc:
			raise ServiceUnavailableError() from rollback_exc
		raise OAuthFailedError()
	login_user_id = str(user.id)
	try:
		await _record_oauth_login(db, user, request, client_info)
	except Exception as exc:
		log_login_history_write_failed(request, user, client_info, user_id=login_user_id)
		try:
			await rollback_oauth_login(
				configured_strategy,
				user,
				login_result,
				response,
				config,
				clear_state_cookie=False,
				request=request,
				client_info=client_info,
				operation="oauth_exchange_login_history",
			)
		except Exception as rollback_exc:
			raise ServiceUnavailableError() from rollback_exc
		raise ServiceUnavailableError() from exc
	return OAuthExchangeResponse(
		access_token=login_result.access_token,
		token_type="bearer",
		expires_in=login_result.expires_in,
		redirect_to=handoff.redirect_to,
	)
