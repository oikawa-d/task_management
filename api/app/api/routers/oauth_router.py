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
	OAuthDisabledError,
	OAuthEmailUnverifiedError,
	ServiceUnavailableError,
	TooManyAttemptsError,
)
from app.db import get_db_session
from app.schemas.oauth import OAuthCallbackQuery, OAuthExchangeRequest, OAuthExchangeResponse
from app.service import auth_service, oauth_service

logger = logging.getLogger("app.oauth")

# ブラウザ直接遷移のためJSONエラーではなく /login?error=... へ誘導する（12番設計書 §3）。
OAUTH_ERROR_DENIED = "oauth_denied"
OAUTH_ERROR_INVALID_STATE = "invalid_state"
OAUTH_ERROR_EMAIL_UNVERIFIED = "oauth_email_unverified"
OAUTH_ERROR_TOO_MANY_ATTEMPTS = "too_many_attempts"
OAUTH_ERROR_FAILED = "oauth_failed"
OAUTH_ERROR_DISABLED = "oauth_disabled"

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
	settings: BackendSettings = Depends(get_backend_settings),
) -> RedirectResponse:
	"""GET /api/auth/oauth/google: GoogleのOAuth認可画面へリダイレクトする。

	認可: 不要（未認証で呼び出し可能）。Googleログインが無効な設定の場合は404 NOT_FOUNDを返す。
	CSRF対策のstate・PKCE用のcode_verifier・nonceをCookieに設定してから認可URLへ302する。

	Args:
		response: state等のCookie設定先のResponse。
		request: リクエスト情報取得用のRequest。
		redirect_to: 認証完了後にフロントで復元する遷移先パス。
		settings: Googleログイン有効可否・OAuthエンドポイント設定。

	Returns:
		302でGoogleの認可エンドポイントへリダイレクトする。

	Raises:
		OAuthDisabledError: Googleログインが無効な場合（404 OAUTH_DISABLED）。
	"""
	_ensure_google_login_enabled(settings)
	result = await oauth_service.oauth_start(redirect_to, request, response)
	redirect = RedirectResponse(result.authorize_url, status_code=_HTTP_FOUND)
	redirect.raw_headers.extend(response.raw_headers)
	return redirect


@router.get("/google/callback")
async def oauth_google_callback(
	request: Request,
	response: Response,
	query: OAuthCallbackQuery = Depends(),
	db: AsyncSession = Depends(get_db_session),
	settings: BackendSettings = Depends(get_backend_settings),
) -> RedirectResponse:
	"""GET /api/auth/oauth/google/callback: GoogleのOAuth認可後のcallbackを処理する。

	認可: 不要（未認証で呼び出し可能。ブラウザからの直接遷移のため認可ヘッダは使わない）。
	正常系・異常系ともに基本的にJSONエラーではなく`/login?error=...`または
	`/oauth/callback#...`へ302リダイレクトする（ブラウザの直接遷移のため）。
	ただし、Redis障害等によるServiceUnavailableErrorとレート制限超過のTooManyAttemptsErrorは
	リダイレクトに変換せずそのまま送出する。

	Args:
		request: state Cookie等の読み取りに用いるRequest。
		response: state/nonce等のCookie削除を反映するResponse。
		query: Googleから付与される`code`・`state`・`error`クエリ。
		db: DBセッション。
		settings: Googleログイン有効可否・フロントURL等の設定。

	Returns:
		302で`/login?error=...`（拒否・失敗時）または`/oauth/callback#...`（成功時）へリダイレクトする。

	Raises:
		ServiceUnavailableError: Redis等の基盤障害時（503 SERVICE_UNAVAILABLE）。
		TooManyAttemptsError: レート制限超過時（429 TOO_MANY_ATTEMPTS）。
	"""
	code = query.code
	state = query.state
	error = query.error
	if not _is_google_login_enabled(settings):
		return _login_error_redirect(OAUTH_ERROR_DISABLED, settings, response)
	if error:
		state_cookie = request.cookies.get(settings.cookie_name_oauth_state)
		try:
			await oauth_service.oauth_callback_denied(state, state_cookie, request, response, settings=settings)
		except ServiceUnavailableError:
			raise
		except TooManyAttemptsError:
			raise
		except Exception as exc:
			logger.warning(
				"OAuth callback denial cleanup failed",
				extra={
					"operation": "oauth_callback",
					"event": "oauth_callback_failed",
					"failure_reason": type(exc).__name__,
				},
			)
			return _login_error_redirect(_callback_error_value(exc), settings, response)
		return _login_error_redirect(OAUTH_ERROR_DENIED, settings, response)
	state_cookie = request.cookies.get(settings.cookie_name_oauth_state)
	try:
		result = await oauth_service.oauth_callback(code, state, state_cookie, request, response, db)
	except ServiceUnavailableError:
		raise
	except TooManyAttemptsError:
		raise
	except Exception as exc:
		logger.warning(
			"OAuth callback failed",
			extra={
				"operation": "oauth_callback",
				"event": "oauth_callback_failed",
				"failure_reason": type(exc).__name__,
			},
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
	"""POST /api/auth/oauth/exchange: OAuth callback発行のhandoff codeをaccess tokenへ交換する（jwtモード専用）。

	認可: 不要な認証ヘッダの代わりにhandoff codeを検証する。Origin検証を課す。
	sessionモードでの呼び出しは405を返す。レスポンスは`Cache-Control: no-store`とする。

	Args:
		payload: callbackで発行されたhandoff code。
		request: リクエスト情報取得用のRequest。
		response: refresh/csrf tokenのCookie設定先のResponse。
		db: DBセッション。
		settings: Googleログイン有効可否・`auth_mode`設定。

	Returns:
		200 OKでaccess tokenを返す。

	Raises:
		OAuthDisabledError: Googleログインが無効な場合（404 OAUTH_DISABLED）。
		NotSupportedInModeError: sessionモードで呼び出された場合（405 NOT_SUPPORTED_IN_MODE）。
		OAuthHandoffInvalidError: handoff codeが無効・期限切れの場合（400 OAUTH_HANDOFF_INVALID）。
	"""
	_ensure_google_login_enabled(settings)
	if settings.auth_mode != "jwt":
		raise NotSupportedInModeError()
	result = await oauth_service.oauth_exchange(payload.code, request, response, db)
	response.headers["Cache-Control"] = "no-store"
	return result


def _callback_error_value(exc: Exception) -> str:
	"""callback処理中の例外を、`/login?error=...`へ渡すフロント向けエラー種別文字列へ変換する。

	Args:
		exc: callback処理中に捕捉した例外。

	Returns:
		対応するエラー種別が定義されていればそれを、無ければ`OAUTH_ERROR_FAILED`を返す。
	"""
	for exception_type, error_value in _CALLBACK_ERROR_BY_EXCEPTION:
		if isinstance(exc, exception_type):
			return error_value
	return OAUTH_ERROR_FAILED


def _is_google_login_enabled(settings: BackendSettings) -> bool:
	"""現在の設定でGoogleログインが有効かどうかを判定する。"""
	return auth_service.get_auth_config(settings).google_login_enabled


def _ensure_google_login_enabled(settings: BackendSettings) -> None:
	"""Googleログインが無効な場合にOAuthDisabledError（404 OAUTH_DISABLED）を送出する。

	Raises:
		OAuthDisabledError: Googleログインが無効な場合。
	"""
	if not _is_google_login_enabled(settings):
		raise OAuthDisabledError()


def _login_error_redirect(error_value: str, settings: BackendSettings, response: Response) -> RedirectResponse:
	"""フロントのログイン画面へエラー種別付きでリダイレクトするResponseを組み立てる。

	Args:
		error_value: フロントに伝えるエラー種別文字列。
		settings: リダイレクト先ベースURLの設定。
		response: 引き継ぐSet-Cookieを保持するResponse。

	Returns:
		`/login?error=...`への302 RedirectResponse。
	"""
	location = f"{settings.frontend_base_url}/login?{urlencode({'error': error_value})}"
	return _redirect_with_cookies(location, response)


def _redirect_with_cookies(location: str, response: Response) -> RedirectResponse:
	"""service層が`response`へ設定したSet-Cookie（発行・削除）を引き継いだリダイレクトを返す。"""
	redirect = RedirectResponse(location, status_code=_HTTP_FOUND)
	redirect.raw_headers.extend(response.raw_headers)
	return redirect
