import logging
from urllib.parse import urlencode

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.base import AuthStrategy, LoginResult
from app.auth.factory import get_auth_strategy
from app.core.config import BackendSettings, get_backend_settings
from app.core.deps import get_current_user, verify_csrf, verify_origin
from app.core.exceptions import (
	InvalidStateError,
	OAuthEmailUnverifiedError,
	OAuthFailedError,
	ServiceUnavailableError,
	TooManyAttemptsError,
)
from app.db import get_db_session
from app.schemas.auth import (
	AuthConfigResponse,
	CurrentUser,
	LoginRequest,
	LoginResponse,
	MeResponse,
	PasswordForgotRequest,
	PasswordForgotResponse,
	PasswordResetRequest,
	RefreshResponse,
	RegisterRequest,
	RegisterResponse,
	ResendVerifyEmailRequest,
	ResendVerifyEmailResponse,
	VerifyEmailRequest,
)
from app.schemas.oauth import OAuthExchangeRequest, OAuthExchangeResponse, OAuthStartResult
from app.service import auth_service

logger = logging.getLogger("app.oauth")

router = APIRouter(prefix="/api/auth", tags=["auth"])

REGISTER_MESSAGE = "確認メールを送信しました。メール内のリンクから認証を完了してください。"
RESEND_MESSAGE = (
	"確認メールを送信しました。しばらくしても届かない場合は、入力内容や迷惑メールフォルダをご確認ください。"
)
FORGOT_MESSAGE = "ご入力のメールアドレスが登録されている場合、パスワード再設定用のメールを送信しました。"


def _token_response(result: LoginResult) -> LoginResponse | RefreshResponse:
	if result.access_token is None or result.expires_in is None:
		raise ServiceUnavailableError()
	return LoginResponse(access_token=result.access_token, token_type="bearer", expires_in=result.expires_in)


def _set_no_store(response: Response) -> None:
	response.headers["Cache-Control"] = "no-store"


async def _verify_logout_csrf(
	request: Request,
	strategy: AuthStrategy = Depends(get_auth_strategy),
	settings: BackendSettings = Depends(get_backend_settings),
) -> None:
	if strategy.mode == "jwt" and not request.cookies.get(settings.cookie_name_refresh):
		return
	await verify_csrf(request, strategy, settings)


def _complete_redirect(response: Response, location: str) -> Response:
	response.status_code = status.HTTP_302_FOUND
	response.headers["Location"] = location
	return response


def _oauth_callback_location(settings: BackendSettings, result: object) -> str:
	auth_mode = getattr(result, "auth_mode")
	redirect_to = getattr(result, "redirect_to")
	fragment: dict[str, str] = {"redirect_to": redirect_to}
	if auth_mode == "jwt":
		handoff_code = getattr(result, "handoff_code", None)
		if not isinstance(handoff_code, str) or not handoff_code:
			raise OAuthFailedError()
		fragment = {"code": handoff_code, "redirect_to": redirect_to}
	return f"{settings.frontend_base_url.rstrip('/')}/oauth/callback#{urlencode(fragment)}"


def _oauth_error_location(settings: BackendSettings, error: str) -> str:
	return f"{settings.frontend_base_url.rstrip('/')}/login?{urlencode({'error': error})}"


def _oauth_error_code(exc: Exception) -> str:
	if isinstance(exc, InvalidStateError):
		return "invalid_state"
	if isinstance(exc, OAuthEmailUnverifiedError):
		return "oauth_email_unverified"
	if isinstance(exc, (OAuthFailedError, TooManyAttemptsError)):
		return "oauth_failed"
	return "oauth_failed"


def _request_id(request: Request) -> str | None:
	request_state = getattr(request, "state", None)
	value = getattr(request_state, "request_id", None)
	return value if isinstance(value, str) else None


def _log_oauth_callback_failed(request: Request, exc: Exception) -> None:
	logger.warning(
		"OAuth callback failed",
		extra={
			"operation": "oauth_callback",
			"event": "oauth_callback_failed",
			"failure_reason": type(exc).__name__,
			"request_id": _request_id(request),
		},
	)


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
	payload: RegisterRequest,
	background: BackgroundTasks,
	request: Request,
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(verify_origin),
) -> RegisterResponse:
	user = await auth_service.register(payload, background, request, db)
	return RegisterResponse(id=user.id, email=user.email, message=REGISTER_MESSAGE)


@router.post("/login", response_model=LoginResponse)
async def login(
	payload: LoginRequest,
	request: Request,
	response: Response,
	db: AsyncSession = Depends(get_db_session),
	strategy: AuthStrategy = Depends(get_auth_strategy),
	_: None = Depends(verify_origin),
) -> LoginResponse | Response:
	result = await auth_service.login(payload.identifier, payload.password, request, response, db, strategy)
	if result.auth_mode == "session":
		response.status_code = status.HTTP_204_NO_CONTENT
		return response
	return _token_response(result)  # type: ignore[return-value]


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
	request: Request,
	response: Response,
	strategy: AuthStrategy = Depends(get_auth_strategy),
	_: None = Depends(verify_origin),
	__csrf: None = Depends(_verify_logout_csrf),
) -> Response:
	await auth_service.logout(request, response, strategy)
	response.status_code = status.HTTP_204_NO_CONTENT
	return response


@router.get("/me", response_model=MeResponse)
async def get_me(
	response: Response,
	current_user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
	settings: BackendSettings = Depends(get_backend_settings),
) -> MeResponse:
	_set_no_store(response)
	return await auth_service.get_me(current_user, db, settings)


@router.get("/config", response_model=AuthConfigResponse)
async def get_auth_config(
	response: Response,
	settings: BackendSettings = Depends(get_backend_settings),
) -> AuthConfigResponse:
	_set_no_store(response)
	return auth_service.get_auth_config(settings)


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(
	request: Request,
	response: Response,
	strategy: AuthStrategy = Depends(get_auth_strategy),
	_: None = Depends(verify_origin),
	__csrf: None = Depends(verify_csrf),
) -> RefreshResponse:
	result = await strategy.refresh(request, response)
	_set_no_store(response)
	return _token_response(result)  # type: ignore[return-value]


@router.post("/verify-email", status_code=status.HTTP_204_NO_CONTENT)
async def verify_email(
	payload: VerifyEmailRequest,
	db: AsyncSession = Depends(get_db_session),
) -> Response:
	await auth_service.verify_email(payload.token, db)
	return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
	"/verify-email/resend",
	response_model=ResendVerifyEmailResponse,
	status_code=status.HTTP_202_ACCEPTED,
)
async def resend_verify_email(
	payload: ResendVerifyEmailRequest,
	background: BackgroundTasks,
	db: AsyncSession = Depends(get_db_session),
) -> ResendVerifyEmailResponse:
	await auth_service.resend_verification(payload.email, background, db)
	return ResendVerifyEmailResponse(message=RESEND_MESSAGE)


@router.post("/password/forgot", response_model=PasswordForgotResponse, status_code=status.HTTP_202_ACCEPTED)
async def password_forgot(
	payload: PasswordForgotRequest,
	background: BackgroundTasks,
	db: AsyncSession = Depends(get_db_session),
) -> PasswordForgotResponse:
	await auth_service.request_password_reset(payload.email, background, db)
	return PasswordForgotResponse(message=FORGOT_MESSAGE)


@router.post("/password/reset", status_code=status.HTTP_204_NO_CONTENT)
async def password_reset(
	payload: PasswordResetRequest,
	db: AsyncSession = Depends(get_db_session),
) -> Response:
	await auth_service.reset_password(payload.token, payload.new_password, db)
	return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/oauth/google")
async def oauth_google_start(
	request: Request,
	response: Response,
	redirect_to: str | None = Query(default=None),
	settings: BackendSettings = Depends(get_backend_settings),
) -> Response:
	result: OAuthStartResult = await auth_service.oauth_start(
		redirect_to, request=request, response=response, settings=settings
	)
	return _complete_redirect(response, result.authorize_url)


@router.get("/oauth/google/callback")
async def oauth_google_callback(
	request: Request,
	response: Response,
	db: AsyncSession = Depends(get_db_session),
	settings: BackendSettings = Depends(get_backend_settings),
	code: str | None = Query(default=None),
	state: str | None = Query(default=None),
	error: str | None = Query(default=None),
) -> Response:
	if error is not None:
		return _complete_redirect(response, _oauth_error_location(settings, "oauth_denied"))
	try:
		result = await auth_service.oauth_callback(
			code,
			state,
			request.cookies.get(settings.cookie_name_oauth_state),
			request,
			response,
			db,
			settings=settings,
		)
		return _complete_redirect(response, _oauth_callback_location(settings, result))
	except Exception as exc:
		_log_oauth_callback_failed(request, exc)
		response.delete_cookie(
			settings.cookie_name_oauth_state,
			secure=settings.cookie_secure,
			httponly=True,
			samesite=settings.cookie_samesite,
			path="/api/auth/oauth",
			domain=settings.cookie_domain or None,
		)
		return _complete_redirect(response, _oauth_error_location(settings, _oauth_error_code(exc)))


@router.post("/oauth/exchange", response_model=OAuthExchangeResponse)
async def oauth_exchange(
	payload: OAuthExchangeRequest,
	request: Request,
	response: Response,
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(verify_origin),
) -> OAuthExchangeResponse:
	result = await auth_service.oauth_exchange(payload.code, request, response, db)
	_set_no_store(response)
	return result
