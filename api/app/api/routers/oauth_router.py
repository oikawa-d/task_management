"""Google OAuth2の認可開始・callback・token交換のエンドポイント。

参照設計書:
- docs/detailed_design/api/auth/11_get_auth_oauth_google.md
- docs/detailed_design/api/auth/12_get_auth_oauth_google_callback.md
- docs/detailed_design/api/auth/13_post_auth_oauth_exchange.md
"""

import logging
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import BackendSettings, get_backend_settings
from app.core.deps import verify_origin
from app.core.exceptions import (
	InvalidStateError,
	NotSupportedInModeError,
	OAuthEmailUnverifiedError,
	ServiceUnavailableError,
	TooManyAttemptsError,
)
from app.db import get_db_session
from app.schemas.oauth import OAuthExchangeRequest, OAuthExchangeResponse
from app.service import auth_service

logger = logging.getLogger("app.oauth")

# ブラウザ直接遷移のためJSONエラーではなく /login?error=... へ誘導する（12番設計書 §3）。
OAUTH_ERROR_DENIED = "oauth_denied"
OAUTH_ERROR_INVALID_STATE = "invalid_state"
OAUTH_ERROR_EMAIL_UNVERIFIED = "oauth_email_unverified"
OAUTH_ERROR_TOO_MANY_ATTEMPTS = "too_many_attempts"
OAUTH_ERROR_FAILED = "oauth_failed"

_CALLBACK_ERROR_BY_EXCEPTION: tuple[tuple[type[Exception], str], ...] = (
	(InvalidStateError, OAUTH_ERROR_INVALID_STATE),
	(OAuthEmailUnverifiedError, OAUTH_ERROR_EMAIL_UNVERIFIED),
	(TooManyAttemptsError, OAUTH_ERROR_TOO_MANY_ATTEMPTS),
)

_HTTP_FOUND = 302

router = APIRouter(prefix="/api/auth/oauth", tags=["auth"])


@router.get("/google")
async def oauth_google_start(
	response: Response,
	request: Request,
	redirect_to: str | None = Query(default=None),
) -> RedirectResponse:
	result = await auth_service.oauth_start(redirect_to, request, response)
	redirect = RedirectResponse(result.authorize_url, status_code=_HTTP_FOUND)
	redirect.raw_headers.extend(response.raw_headers)
	return redirect


@router.get("/google/callback")
async def oauth_google_callback(
	request: Request,
	response: Response,
	code: str | None = Query(default=None),
	state: str | None = Query(default=None),
	error: str | None = Query(default=None),
	db: AsyncSession = Depends(get_db_session),
	settings: BackendSettings = Depends(get_backend_settings),
) -> RedirectResponse:
	if error:
		state_cookie = request.cookies.get(settings.cookie_name_oauth_state)
		try:
			await auth_service.oauth_callback_denied(state, state_cookie, request, response, settings=settings)
		except ServiceUnavailableError:
			raise
		except TooManyAttemptsError:
			raise
		except Exception as exc:
			logger.warning(
				"OAuth callback denial cleanup failed",
				extra={"operation": "oauth_callback", "event": "oauth_callback_failed", "error": type(exc).__name__},
			)
			return _login_error_redirect(_callback_error_value(exc), settings, response)
		return _login_error_redirect(OAUTH_ERROR_DENIED, settings, response)
	state_cookie = request.cookies.get(settings.cookie_name_oauth_state)
	try:
		result = await auth_service.oauth_callback(code, state, state_cookie, request, response, db)
	except ServiceUnavailableError:
		raise
	except TooManyAttemptsError:
		raise
	except Exception as exc:
		logger.warning(
			"OAuth callback failed",
			extra={"operation": "oauth_callback", "event": "oauth_callback_failed", "error": type(exc).__name__},
		)
		return _login_error_redirect(_callback_error_value(exc), settings, response)

	if result.auth_mode != settings.auth_mode or (result.auth_mode == "jwt") != (result.handoff_code is not None):
		logger.error(
			"OAuth callback returned inconsistent auth state",
			extra={"operation": "oauth_callback", "event": "oauth_callback_invalid_result"},
		)
		return _login_error_redirect(OAUTH_ERROR_FAILED, settings, response)

	fragment = {"redirect_to": result.redirect_to}
	if result.handoff_code is not None:
		fragment = {"code": result.handoff_code, **fragment}
	# redirect_toは正規化済みの相対パスのため、可読性を保つよう"/"はエスケープしない（12番設計書 §2.2）。
	location = f"{settings.frontend_base_url}/oauth/callback#{urlencode(fragment, safe='/', quote_via=quote)}"
	return _redirect_with_cookies(location, response)


@router.post("/exchange", response_model=OAuthExchangeResponse, dependencies=[Depends(verify_origin)])
async def oauth_exchange(
	payload: OAuthExchangeRequest,
	request: Request,
	response: Response,
	db: AsyncSession = Depends(get_db_session),
	settings: BackendSettings = Depends(get_backend_settings),
) -> OAuthExchangeResponse:
	if settings.auth_mode != "jwt":
		raise NotSupportedInModeError()
	result = await auth_service.oauth_exchange(payload.code, request, response, db)
	response.headers["Cache-Control"] = "no-store"
	return result


def _callback_error_value(exc: Exception) -> str:
	for exception_type, error_value in _CALLBACK_ERROR_BY_EXCEPTION:
		if isinstance(exc, exception_type):
			return error_value
	return OAUTH_ERROR_FAILED


def _login_error_redirect(error_value: str, settings: BackendSettings, response: Response) -> RedirectResponse:
	location = f"{settings.frontend_base_url}/login?{urlencode({'error': error_value})}"
	return _redirect_with_cookies(location, response)


def _redirect_with_cookies(location: str, response: Response) -> RedirectResponse:
	"""service層が`response`へ設定したSet-Cookie（発行・削除）を引き継いだリダイレクトを返す。"""
	redirect = RedirectResponse(location, status_code=_HTTP_FOUND)
	redirect.raw_headers.extend(response.raw_headers)
	return redirect
