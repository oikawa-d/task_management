from collections.abc import Awaitable, Callable
from urllib.parse import urlparse
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.base import AuthStrategy
from app.auth.factory import get_auth_strategy
from app.core.client_ip import resolve_client_ip
from app.core.config import BackendSettings, get_backend_settings
from app.core.exceptions import (
	CsrfInvalidError,
	ForbiddenError,
	NotFoundError,
	ServiceUnavailableError,
	TooManyAttemptsError,
	UnauthenticatedError,
	UserInactiveError,
)
from app.core.security import csrf_tokens_match
from app.db import get_db_session
from app.models.project import Project
from app.models.task import Task
from app.models.task_comment import TaskComment
from app.repository import (
	project_member_repository,
	project_repository,
	redis_store,
	task_comment_repository,
	task_repository,
	user_repository,
)
from app.schemas.auth import CurrentUser


async def get_current_user(
	request: Request,
	strategy: AuthStrategy = Depends(get_auth_strategy),
	db: AsyncSession = Depends(get_db_session),
) -> CurrentUser:
	context = await strategy.authenticate(request)
	if context is None:
		raise UnauthenticatedError()
	user = await user_repository.get_by_id(db, context.user_id)
	if user is None:
		raise UnauthenticatedError()
	if not user.is_active:
		raise UserInactiveError()
	return CurrentUser(
		id=user.id,
		username=user.username,
		role=user.role,
		is_active=user.is_active,
		email_verified_at=user.email_verified_at,
	)


async def get_current_user_optional(
	request: Request,
	strategy: AuthStrategy = Depends(get_auth_strategy),
	db: AsyncSession = Depends(get_db_session),
) -> CurrentUser | None:
	try:
		return await get_current_user(request, strategy, db)
	except UnauthenticatedError:
		return None
	except UserInactiveError:
		return None


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
	if user.role != "admin":
		raise ForbiddenError()
	return user


async def require_project_member(
	project_id: UUID,
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
) -> Project:
	project = await project_repository.get_by_id(db, project_id)
	if project is None:
		raise NotFoundError()
	if not await project_repository.is_member(db, project_id, user.id):
		raise NotFoundError()
	return project


async def require_project_owner(
	project: Project = Depends(require_project_member), user: CurrentUser = Depends(get_current_user)
) -> Project:
	if user.role != "admin" and project.owner_id != user.id:
		raise ForbiddenError()
	return project


async def verify_origin(request: Request, settings: BackendSettings = Depends(get_backend_settings)) -> None:
	origin = request.headers.get("origin")
	if origin is None and request.url.scheme == "https" and settings.csrf_trust_referer_on_https:
		origin = _origin_from_referer(request.headers.get("referer"))
	if origin is None or origin not in settings.cors_allow_origins:
		raise CsrfInvalidError()


def _origin_from_referer(referer: str | None) -> str | None:
	if not referer:
		return None
	parsed = urlparse(referer)
	if not parsed.scheme or not parsed.netloc:
		return None
	return f"{parsed.scheme}://{parsed.netloc}"


async def verify_csrf(
	request: Request,
	strategy: AuthStrategy = Depends(get_auth_strategy),
	settings: BackendSettings = Depends(get_backend_settings),
) -> None:
	header = request.headers.get("x-csrf-token")
	if not header:
		raise CsrfInvalidError()
	if strategy.mode == "session":
		session_id = request.cookies.get(settings.cookie_name_session)
		if not session_id:
			raise CsrfInvalidError()
		cookie_token = await redis_store.get_csrf_token(session_id)
	else:
		cookie_token = request.cookies.get(settings.cookie_name_csrf)
	if cookie_token is None or not csrf_tokens_match(cookie_token, header):
		raise CsrfInvalidError()


async def verify_csrf_if_session(
	request: Request,
	strategy: AuthStrategy = Depends(get_auth_strategy),
	settings: BackendSettings = Depends(get_backend_settings),
) -> None:
	"""通常APIの更新系エンドポイント向けCSRF検証。

	CSRFはsessionモードの更新系エンドポイントでのみ必須であり、
	jwtモードの通常APIはAuthorizationヘッダで認証されるため検証しない。
	"""
	if strategy.mode != "session":
		return
	await verify_csrf(request, strategy, settings)


async def get_task_for_member(
	task_id: UUID,
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
) -> Task:
	task_with_status = await task_repository.get_by_id(db, task_id)
	if task_with_status is None:
		raise NotFoundError()
	task = task_with_status.task
	if user.role != "admin" and task.project_id is not None:
		if not await project_member_repository.exists(db, task.project_id, user.id):
			raise NotFoundError()
	return task


async def get_comment_for_member(
	comment_id: UUID,
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
) -> TaskComment:
	comment = await task_comment_repository.get_by_id(db, comment_id)
	if comment is None:
		raise NotFoundError()
	task_with_status = await task_repository.get_by_id(db, comment.task_id)
	if task_with_status is None:
		raise NotFoundError()
	task = task_with_status.task
	if user.role != "admin" and task.project_id is not None:
		if not await project_member_repository.exists(db, task.project_id, user.id):
			raise NotFoundError()
	comment.task = task
	return comment


async def verify_csrf_for_logout(
	request: Request,
	strategy: AuthStrategy = Depends(get_auth_strategy),
	settings: BackendSettings = Depends(get_backend_settings),
) -> None:
	"""ログアウト専用のCSRF検証。

	ログアウトは冪等APIであり、認証Cookieが無い場合はCookie破棄だけを行って204を返す。
	そのため検証対象のCookie（session:`cookie_name_session` / jwt:`cookie_name_refresh`）が
	存在する場合に限りCSRFトークンを検証する（03_post_auth_logout.md §1）。
	"""
	cookie_name = settings.cookie_name_session if strategy.mode == "session" else settings.cookie_name_refresh
	if not request.cookies.get(cookie_name):
		return
	await verify_csrf(request, strategy, settings)


def enforce_rate_limit(scope: str, max_requests_field: str, window_field: str) -> Callable[..., Awaitable[None]]:
	"""公開APIのIP単位レート制限を行う依存性を生成する。

	`scope`はRedisキー`rate_limit:{scope}:{key_hash}`の名前空間、
	`max_requests_field`/`window_field`は`BackendSettings`の属性名を指す
	（上限・時間窓はすべて環境変数で外部化する）。Redis障害時はfail-closeで503を返す。
	"""

	async def _enforce(
		request: Request,
		settings: BackendSettings = Depends(get_backend_settings),
	) -> None:
		max_requests: int = getattr(settings, max_requests_field)
		window: int = getattr(settings, window_field)
		client_ip = resolve_client_ip(request, settings.trusted_proxy_cidrs).client_ip
		try:
			count = await redis_store.check_rate_limit(scope, client_ip, max_requests, window)
		except Exception as exc:
			raise ServiceUnavailableError() from exc
		if count > max_requests:
			raise TooManyAttemptsError()

	return _enforce
