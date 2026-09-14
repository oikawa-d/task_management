"""会員登録・ログイン・ログアウト・セッション復元・公開設定と、token更新・メール認証・パスワード再設定のエンドポイント。

参照設計書: docs/detailed_design/api/auth/01_post_auth_register.md〜10_post_auth_password_reset.md
"""

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.base import AuthStrategy
from app.auth.factory import get_auth_strategy
from app.core.config import BackendSettings, get_backend_settings
from app.core.deps import enforce_rate_limit, get_current_user, verify_csrf, verify_csrf_for_logout, verify_origin
from app.core.exceptions import AppError
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
from app.service import auth_service, user_service

# フロントがそのまま表示する固定文言。ユーザー列挙を防ぐため、再送・再設定申請は結果によらず同一文言を返す。
REGISTER_ACCEPTED_MESSAGE = "確認メールを送信しました。メール内のリンクから認証を完了してください。"
RESEND_ACCEPTED_MESSAGE = (
	"確認メールを送信しました。しばらくしても届かない場合は、入力内容や迷惑メールフォルダをご確認ください。"
)
PASSWORD_FORGOT_ACCEPTED_MESSAGE = (
	"ご入力のメールアドレスが登録されている場合、パスワード再設定用のメールを送信しました。"
)

_register_rate_limit = enforce_rate_limit(
	"register", "rate_limit_register_max_requests", "rate_limit_register_window_seconds"
)
_verify_email_rate_limit = enforce_rate_limit(
	"verify_email", "rate_limit_email_verify_max_requests", "rate_limit_email_verify_window_seconds"
)
_verify_email_resend_rate_limit = enforce_rate_limit(
	"verify_email_resend",
	"rate_limit_email_verify_resend_max_requests",
	"rate_limit_email_verify_resend_window_seconds",
)
_password_forgot_rate_limit = enforce_rate_limit(
	"password_forgot", "rate_limit_password_forgot_max_requests", "rate_limit_password_forgot_window_seconds"
)
_password_reset_rate_limit = enforce_rate_limit(
	"password_reset", "rate_limit_password_reset_max_requests", "rate_limit_password_reset_window_seconds"
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post(
	"/register",
	response_model=RegisterResponse,
	status_code=status.HTTP_201_CREATED,
	dependencies=[Depends(verify_origin), Depends(_register_rate_limit)],
)
async def register(
	payload: RegisterRequest,
	background: BackgroundTasks,
	request: Request,
	db: AsyncSession = Depends(get_db_session),
) -> RegisterResponse:
	user = await auth_service.register(payload, background, request, db)
	return RegisterResponse(id=user.id, email=user.email, message=REGISTER_ACCEPTED_MESSAGE)


@router.post("/login", response_model=None)
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
		return _no_content_with_cookies(response)
	if result.access_token is None:
		# jwtモードでaccess tokenが発行されないのはStrategyの内部不整合であり、認証状態を返してはならない。
		raise AppError()
	return LoginResponse(access_token=result.access_token, token_type="bearer", expires_in=result.expires_in)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
	request: Request,
	response: Response,
	strategy: AuthStrategy = Depends(get_auth_strategy),
	_: None = Depends(verify_origin),
	__csrf: None = Depends(verify_csrf_for_logout),
) -> None:
	await auth_service.logout(request, response, strategy)


@router.get("/me", response_model=MeResponse)
async def get_me(
	current_user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
	settings: BackendSettings = Depends(get_backend_settings),
) -> MeResponse:
	profile = await user_service.get_profile(current_user, db)
	return MeResponse(**profile.model_dump(), auth_mode=settings.auth_mode)


@router.get("/config", response_model=AuthConfigResponse)
async def get_auth_config(
	response: Response,
	settings: BackendSettings = Depends(get_backend_settings),
) -> AuthConfigResponse:
	response.headers["Cache-Control"] = "no-store"
	return AuthConfigResponse(
		auth_mode=settings.auth_mode,
		google_login_enabled=bool(settings.google_client_id and settings.google_client_secret),
		csrf_cookie_name=settings.cookie_name_csrf,
	)


@router.post("/refresh", response_model=RefreshResponse, dependencies=[Depends(verify_origin), Depends(verify_csrf)])
async def refresh(
	request: Request,
	response: Response,
	strategy: AuthStrategy = Depends(get_auth_strategy),
) -> RefreshResponse:
	result = await auth_service.refresh(request, response, strategy)
	if result.access_token is None:
		# jwtモードのStrategyがaccess tokenを返さないのは内部不整合であり、成功応答にしてはならない。
		raise AppError()
	return RefreshResponse(access_token=result.access_token, token_type="bearer", expires_in=result.expires_in)


@router.post(
	"/verify-email",
	status_code=status.HTTP_204_NO_CONTENT,
	dependencies=[Depends(_verify_email_rate_limit)],
)
async def verify_email(payload: VerifyEmailRequest, db: AsyncSession = Depends(get_db_session)) -> None:
	await auth_service.verify_email(payload.token, db)


@router.post(
	"/verify-email/resend",
	response_model=ResendVerifyEmailResponse,
	status_code=status.HTTP_202_ACCEPTED,
	dependencies=[Depends(_verify_email_resend_rate_limit)],
)
async def resend_verify_email(
	payload: ResendVerifyEmailRequest,
	background: BackgroundTasks,
	db: AsyncSession = Depends(get_db_session),
) -> ResendVerifyEmailResponse:
	await auth_service.resend_verification(payload.email, background, db)
	return ResendVerifyEmailResponse(message=RESEND_ACCEPTED_MESSAGE)


@router.post(
	"/password/forgot",
	response_model=PasswordForgotResponse,
	status_code=status.HTTP_202_ACCEPTED,
	dependencies=[Depends(_password_forgot_rate_limit)],
)
async def password_forgot(
	payload: PasswordForgotRequest,
	background: BackgroundTasks,
	db: AsyncSession = Depends(get_db_session),
) -> PasswordForgotResponse:
	await auth_service.request_password_reset(payload.email, background, db)
	return PasswordForgotResponse(message=PASSWORD_FORGOT_ACCEPTED_MESSAGE)


@router.post(
	"/password/reset",
	status_code=status.HTTP_204_NO_CONTENT,
	dependencies=[Depends(_password_reset_rate_limit)],
)
async def password_reset(payload: PasswordResetRequest, db: AsyncSession = Depends(get_db_session)) -> None:
	await auth_service.reset_password(payload.token, payload.new_password, db)


def _no_content_with_cookies(response: Response) -> Response:
	"""sessionモードのログインを204で返す。

	FastAPIの戻り値シリアライズ経路ではbody無しの204を返せないため、
	依存性注入された`response`へStrategyが設定したSet-Cookieを引き継いだResponseを組み立てる。
	"""
	no_content = Response(status_code=status.HTTP_204_NO_CONTENT)
	no_content.raw_headers.extend(response.raw_headers)
	return no_content
