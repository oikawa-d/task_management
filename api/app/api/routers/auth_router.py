"""会員登録・ログイン・ログアウト・セッション復元・公開設定のエンドポイント。

参照設計書: docs/detailed_design/api/auth/01_post_auth_register.md〜05_get_auth_config.md
"""

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.base import AuthStrategy
from app.auth.factory import get_auth_strategy
from app.core.config import BackendSettings, get_backend_settings
from app.core.deps import get_current_user, verify_csrf_for_logout, verify_origin
from app.core.exceptions import AppError
from app.db import get_db_session
from app.schemas.auth import (
	AuthConfigResponse,
	CurrentUser,
	LoginRequest,
	LoginResponse,
	MeResponse,
	RegisterRequest,
	RegisterResponse,
)
from app.service import auth_service, user_service

# 登録完了時にフロントがトースト表示する固定文言（01_post_auth_register.md §2.2）。
REGISTER_ACCEPTED_MESSAGE = "確認メールを送信しました。メール内のリンクから認証を完了してください。"

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
	payload: RegisterRequest,
	background: BackgroundTasks,
	request: Request,
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(verify_origin),
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


def _no_content_with_cookies(response: Response) -> Response:
	"""sessionモードのログインを204で返す。

	FastAPIの戻り値シリアライズ経路ではbody無しの204を返せないため、
	依存性注入された`response`へStrategyが設定したSet-Cookieを引き継いだResponseを組み立てる。
	"""
	no_content = Response(status_code=status.HTTP_204_NO_CONTENT)
	no_content.raw_headers.extend(response.raw_headers)
	return no_content
