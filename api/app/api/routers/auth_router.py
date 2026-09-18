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
from app.service import auth_service, email_verification_service, user_service

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
	"""POST /api/auth/register: メールアドレス・パスワードで新規会員登録を行う。

	認可: 不要（未認証で呼び出し可能）。Origin検証とレート制限（登録用）を課す。
	ユーザー列挙を防ぐため、確認メール送信の成否によらず同一メッセージを返す。

	Args:
		payload: 登録情報（メールアドレス・パスワード等）。
		background: 確認メール送信をバックグラウンド実行するためのタスクキュー。
		request: クライアントIP解決等に用いるRequest。
		db: DBセッション。

	Returns:
		201 Createdで登録受付メッセージを返す。

	Raises:
		DuplicateUsernameError: ユーザーIDが既に使用されている場合（409 DUPLICATE_USERNAME）。
		DuplicateEmailError: メールアドレスが既に使用されている場合（409 DUPLICATE_EMAIL）。
		TooManyAttemptsError: レート制限超過時（429 TOO_MANY_ATTEMPTS）。
	"""
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
	"""POST /api/auth/login: ユーザーIDまたはメールアドレスとパスワードでログインする。

	認可: 不要（未認証で呼び出し可能）。Origin検証を課す。
	sessionモードではCookie（session/csrf）を発行し204を返し、
	jwtモードではrefresh/csrf tokenをCookieに設定した上でaccess tokenをJSONで返す。

	Args:
		payload: ログイン識別子とパスワード。
		request: レート制限判定用のクライアントIP解決等に用いるRequest。
		response: Set-Cookie設定先のResponse。
		db: DBセッション。
		strategy: 現在の認証方式（session/jwt）に対応するStrategy。

	Returns:
		sessionモードは204 No Content、jwtモードは200 OKでaccess tokenを返す。

	Raises:
		InvalidCredentialsError: ID・パスワードが一致しない場合（401 INVALID_CREDENTIALS）。
		UserInactiveError: アカウントが無効化されている場合（403 USER_INACTIVE）。
		EmailNotVerifiedError: メール未認証の場合（403 EMAIL_NOT_VERIFIED）。
		TooManyAttemptsError: 連続失敗によるロック中の場合（429 TOO_MANY_ATTEMPTS）。
		AppError: jwtモードでStrategyがaccess tokenを発行できなかった内部不整合の場合（500 INTERNAL_ERROR）。
	"""
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
	"""POST /api/auth/logout: ログアウトし認証状態を破棄する。

	認可: 不要（未認証状態での呼び出しも許容し、その場合は何もしない）。
	Origin検証と、ログアウト専用のCSRF検証（`verify_csrf_for_logout`）を課す。
	sessionモードはセッションを削除し、jwtモードはrefresh tokenを失効させる。いずれもCookieを削除する。

	Args:
		request: Cookie読み取りに用いるRequest。
		response: Cookie削除を反映するResponse。
		strategy: 現在の認証方式に対応するStrategy。

	Returns:
		204 No Contentを返す。
	"""
	await auth_service.logout(request, response, strategy)


@router.get("/me", response_model=MeResponse)
async def get_me(
	current_user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
	settings: BackendSettings = Depends(get_backend_settings),
) -> MeResponse:
	"""GET /api/auth/me: ログイン中ユーザー自身のプロフィールと現在の認証方式を取得する。

	認可: 認証必須（`get_current_user`、未認証は401 UNAUTHENTICATED）。

	Args:
		current_user: 認証済みユーザー。
		db: DBセッション。
		settings: 現在の`auth_mode`取得用の設定。

	Returns:
		200 OKでプロフィールと`auth_mode`を返す。
	"""
	profile = await user_service.get_profile(current_user, db)
	return MeResponse(**profile.model_dump(), auth_mode=settings.auth_mode)


@router.get("/config", response_model=AuthConfigResponse)
async def get_auth_config(
	response: Response,
	settings: BackendSettings = Depends(get_backend_settings),
) -> AuthConfigResponse:
	"""GET /api/auth/config: フロントが認証UIを出し分けるための公開設定を取得する。

	認可: 不要（未認証で呼び出し可能）。レスポンスは`Cache-Control: no-store`とする。

	Args:
		response: no-storeヘッダ設定先のResponse。
		settings: `auth_mode`やGoogleログイン有効可否を含む設定。

	Returns:
		200 OKで認証方式・OAuth有効可否等を返す。
	"""
	response.headers["Cache-Control"] = "no-store"
	return auth_service.get_auth_config(settings)


@router.post("/refresh", response_model=RefreshResponse, dependencies=[Depends(verify_origin), Depends(verify_csrf)])
async def refresh(
	request: Request,
	response: Response,
	strategy: AuthStrategy = Depends(get_auth_strategy),
) -> RefreshResponse:
	"""POST /api/auth/refresh: refresh tokenを用いてaccess tokenを再発行する（jwtモード専用）。

	認可: 不要な認証ヘッダの代わりにrefresh token Cookieを検証する。
	Origin検証・CSRF検証を課す（不正時403 CSRF_INVALID）。
	refresh tokenはローテーションされ、再利用検知時はトークンファミリー全体を失効させる。

	Args:
		request: refresh token Cookie読み取りに用いるRequest。
		response: 新しいCookie設定先のResponse。
		strategy: 現在の認証方式に対応するStrategy。

	Returns:
		200 OKで新しいaccess tokenを返す。

	Raises:
		TokenInvalidError: refresh token Cookieが存在しない場合（401 TOKEN_INVALID）。
		TokenRevokedError: 既に失効・再利用検知済みのtokenの場合（401 TOKEN_REVOKED）。
		NotSupportedInModeError: sessionモードで呼び出された場合（405 NOT_SUPPORTED_IN_MODE）。
		AppError: Strategyがaccess tokenを発行できなかった内部不整合の場合（500 INTERNAL_ERROR）。
	"""
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
	"""POST /api/auth/verify-email: メール内リンクのトークンでメールアドレス認証を完了する。

	認可: 不要（未認証で呼び出し可能）。メール認証用のレート制限を課す。

	Args:
		payload: 確認メールに含まれる検証トークン。
		db: DBセッション。

	Returns:
		204 No Contentを返す。

	Raises:
		InvalidVerifyTokenError: トークンが無効または期限切れの場合（400 INVALID_VERIFY_TOKEN）。
		TooManyAttemptsError: レート制限超過時（429 TOO_MANY_ATTEMPTS）。
	"""
	await email_verification_service.verify_email(payload.token, db)


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
	"""POST /api/auth/verify-email/resend: 確認メールを再送する。

	認可: 不要（未認証で呼び出し可能）。再送用のレート制限を課す。
	ユーザー列挙を防ぐため、対象メールアドレスの存在有無に関わらず同一メッセージを返す。

	Args:
		payload: 再送先メールアドレス。
		background: メール送信をバックグラウンド実行するためのタスクキュー。
		db: DBセッション。

	Returns:
		202 Acceptedで再送受付メッセージを返す。

	Raises:
		TooManyAttemptsError: レート制限超過時（429 TOO_MANY_ATTEMPTS）。
	"""
	await email_verification_service.resend_verification(payload.email, background, db)
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
	"""POST /api/auth/password/forgot: パスワード再設定メールの送信を申請する。

	認可: 不要（未認証で呼び出し可能）。申請用のレート制限を課す。
	ユーザー列挙を防ぐため、対象メールアドレスの登録有無に関わらず同一メッセージを返す。

	Args:
		payload: 再設定対象のメールアドレス。
		background: メール送信をバックグラウンド実行するためのタスクキュー。
		db: DBセッション。

	Returns:
		202 Acceptedで受付メッセージを返す。

	Raises:
		TooManyAttemptsError: レート制限超過時（429 TOO_MANY_ATTEMPTS）。
	"""
	await email_verification_service.request_password_reset(payload.email, background, db)
	return PasswordForgotResponse(message=PASSWORD_FORGOT_ACCEPTED_MESSAGE)


@router.post(
	"/password/reset",
	status_code=status.HTTP_204_NO_CONTENT,
	dependencies=[Depends(_password_reset_rate_limit)],
)
async def password_reset(payload: PasswordResetRequest, db: AsyncSession = Depends(get_db_session)) -> None:
	"""POST /api/auth/password/reset: メール内リンクのトークンで新しいパスワードを設定する。

	認可: 不要（未認証で呼び出し可能）。パスワード再設定用のレート制限を課す。

	Args:
		payload: 再設定トークンと新しいパスワード。
		db: DBセッション。

	Returns:
		204 No Contentを返す。

	Raises:
		InvalidResetTokenError: トークンが無効または期限切れの場合（400 INVALID_RESET_TOKEN）。
		TooManyAttemptsError: レート制限超過時（429 TOO_MANY_ATTEMPTS）。
	"""
	await email_verification_service.reset_password(payload.token, payload.new_password, db)


def _no_content_with_cookies(response: Response) -> Response:
	"""sessionモードのログインを204で返す。

	FastAPIの戻り値シリアライズ経路ではbody無しの204を返せないため、
	依存性注入された`response`へStrategyが設定したSet-Cookieを引き継いだResponseを組み立てる。
	"""
	no_content = Response(status_code=status.HTTP_204_NO_CONTENT)
	no_content.raw_headers.extend(response.raw_headers)
	return no_content
