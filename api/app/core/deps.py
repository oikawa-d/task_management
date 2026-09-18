"""FastAPIルーター共通のDependsで使う依存性関数群（認証・認可・CSRF/Origin検証・レート制限）。"""

from collections.abc import Awaitable, Callable
from urllib.parse import urlparse
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

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
	"""現在の認証方式でリクエストを認証し、有効なユーザーを`CurrentUser`として返す。

	認証結果は`request.state.current_user`にも格納し、後段の履歴ミドルウェア等が
	参照できるようにする。

	Args:
		request: 認証対象のHTTPリクエスト。
		strategy: セッション/JWTいずれかの認証戦略（`get_auth_strategy`で解決）。
		db: ユーザー取得に使う非同期DBセッション。

	Returns:
		認証済みユーザー情報。

	Raises:
		UnauthenticatedError: 未認証、またはトークン/セッションに対応するユーザーが存在しない場合。
		UserInactiveError: ユーザーが無効化されている場合。
	"""
	context = await strategy.authenticate(request)
	if context is None:
		raise UnauthenticatedError()
	user = await user_repository.get_by_id(db, context.user_id)
	if user is None:
		raise UnauthenticatedError()
	if not user.is_active:
		raise UserInactiveError()
	current_user = CurrentUser(
		id=user.id,
		username=user.username,
		role=user.role,
		is_active=user.is_active,
		email_verified_at=user.email_verified_at,
	)
	if request is not None:
		request.state.current_user = current_user
	return current_user


async def get_current_user_optional(
	request: Request,
	strategy: AuthStrategy = Depends(get_auth_strategy),
	db: AsyncSession = Depends(get_db_session),
) -> CurrentUser | None:
	"""`get_current_user`のオプショナル版。未認証・無効ユーザーの場合は例外を送出せずNoneを返す。

	Args:
		request: 認証対象のHTTPリクエスト。
		strategy: セッション/JWTいずれかの認証戦略。
		db: ユーザー取得に使う非同期DBセッション。

	Returns:
		認証できた場合はユーザー情報、それ以外はNone。
	"""
	try:
		return await get_current_user(request, strategy, db)
	except UnauthenticatedError:
		return None
	except UserInactiveError:
		return None


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
	"""管理者専用エンドポイント向けに、認証済みユーザーが`admin`ロールであることを要求する。

	Args:
		user: `get_current_user`で解決した認証済みユーザー。

	Returns:
		そのまま渡された`user`（管理者ロールであることを保証済み）。

	Raises:
		ForbiddenError: `admin`ロールでない場合。
	"""
	if user.role != "admin":
		raise ForbiddenError()
	return user


async def require_project_member(
	project_id: UUID,
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
) -> Project:
	"""パスパラメータのプロジェクトが存在し、かつ認証ユーザーがメンバーであることを要求する。

	非メンバーへの存在有無の漏洩を避けるため、プロジェクト不存在時とメンバー外時の
	いずれも同一の`NotFoundError`（404）を返す。

	Args:
		project_id: 対象プロジェクトのID。
		user: 認証済みユーザー。
		db: 非同期DBセッション。

	Returns:
		対象のプロジェクト。

	Raises:
		NotFoundError: プロジェクトが存在しない、またはユーザーがメンバーでない場合。
	"""
	project = await project_repository.get_by_id(db, project_id)
	if project is None:
		raise NotFoundError()
	if not await project_repository.is_member(db, project_id, user.id):
		raise NotFoundError()
	return project


async def require_project_owner(
	project: Project = Depends(require_project_member), user: CurrentUser = Depends(get_current_user)
) -> Project:
	"""プロジェクトメンバーであることに加え、オーナーまたは管理者であることを要求する。

	Args:
		project: `require_project_member`で解決済みのプロジェクト。
		user: 認証済みユーザー。

	Returns:
		そのまま渡された`project`。

	Raises:
		ForbiddenError: ユーザーが管理者でも当該プロジェクトのオーナーでもない場合。
	"""
	if user.role != "admin" and project.owner_id != user.id:
		raise ForbiddenError()
	return project


async def verify_origin(request: Request, settings: BackendSettings = Depends(get_backend_settings)) -> None:
	"""OriginヘッダがCORS許可オリジンに含まれることを検証する（CSRF対策）。

	Originヘッダが無くHTTPSかつ`csrf_trust_referer_on_https`が有効な場合のみ、
	Refererヘッダから代替のオリジンを導出して検証する。

	Args:
		request: 検証対象のHTTPリクエスト。
		settings: `cors_allow_origins`等を保持するバックエンド設定。

	Raises:
		CsrfInvalidError: オリジンを特定できない、または許可オリジンに含まれない場合。
	"""
	origin = request.headers.get("origin")
	if origin is None and request.url.scheme == "https" and settings.csrf_trust_referer_on_https:
		origin = _origin_from_referer(request.headers.get("referer"))
	if origin is None or origin not in settings.cors_allow_origins:
		raise CsrfInvalidError()


async def verify_origin_if_session(
	request: Request,
	strategy: AuthStrategy = Depends(get_auth_strategy),
	settings: BackendSettings = Depends(get_backend_settings),
) -> None:
	"""通常APIの更新系エンドポイント向けOrigin検証。JWT方式では認証ヘッダのみのため検証しない。"""
	if strategy.mode != "session":
		return
	await verify_origin(request, settings)


def _origin_from_referer(referer: str | None) -> str | None:
	"""RefererヘッダからスキームとホストのみのオリジンURLを抽出する。解析できない場合はNoneを返す。"""
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
	"""Double Submit CookieパターンでCSRFトークンを検証する。

	sessionモードではRedisに保存済みのCSRFトークン（セッションIDに紐づく）と、
	jwtモードではCookieに保存されたCSRFトークンと、それぞれリクエストヘッダの
	`X-CSRF-Token`を定数時間比較する。

	Args:
		request: 検証対象のHTTPリクエスト。
		strategy: セッション/JWTいずれかの認証戦略。
		settings: Cookie名等を保持するバックエンド設定。

	Raises:
		CsrfInvalidError: ヘッダ・Cookie・保存済みトークンのいずれかが欠落、または不一致の場合。
	"""
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
	db: AsyncSession = Depends(get_db_session),
) -> Task:
	"""パスパラメータのタスクIDから、存在確認済みのタスクを取得する。

	Args:
		task_id: 対象タスクのID。
		db: 非同期DBセッション。

	Returns:
		対象のタスク。

	Raises:
		NotFoundError: タスクが存在しない場合。
	"""
	task_with_status = await task_repository.get_by_id(db, task_id)
	if task_with_status is None:
		raise NotFoundError()
	return task_with_status.task


async def get_comment_for_member(
	comment_id: UUID,
	db: AsyncSession = Depends(get_db_session),
) -> TaskComment:
	"""パスパラメータのコメントIDから、紐づくタスクを事前ロード済みのコメントを取得する。

	`set_committed_value`でコメントの`task`関連をキャッシュしておくことで、
	呼び出し元が追加のクエリなしに紐づくタスクへアクセスできるようにする。

	Args:
		comment_id: 対象コメントのID。
		db: 非同期DBセッション。

	Returns:
		`task`関連を設定済みのコメント。

	Raises:
		NotFoundError: コメント、または紐づくタスクが存在しない場合。
	"""
	comment = await task_comment_repository.get_by_id(db, comment_id)
	if comment is None:
		raise NotFoundError()
	task_with_status = await task_repository.get_by_id(db, comment.task_id)
	if task_with_status is None:
		raise NotFoundError()
	task = task_with_status.task
	set_committed_value(comment, "task", task)
	return comment


def _resolved_client_ip(request: Request, settings: BackendSettings) -> str:
	"""信頼済みプロキシ設定を考慮して、レート制限キーに使うクライアントIPを解決する。"""
	return resolve_client_ip(request, settings.trusted_proxy_cidrs).client_ip


async def _enforce_rate_limit_by_key(
	scope: str,
	value: str,
	max_requests: int,
	window: int,
) -> None:
	"""Redisベースのレート制限を判定する共通処理。Redis障害時はfail-closeで503を返す。"""
	try:
		count = await redis_store.check_rate_limit(scope, value, max_requests, window)
		if count <= max_requests:
			return
		retry_after = await redis_store.get_rate_limit_ttl(scope, value)
	except Exception as exc:
		raise ServiceUnavailableError() from exc
	if count > max_requests:
		raise TooManyAttemptsError(retry_after=retry_after if retry_after > 0 else window)


async def _enforce_rate_limit(
	request: Request,
	user: CurrentUser,
	settings: BackendSettings,
	scope: str,
	max_requests: int,
	window: int,
) -> None:
	"""ユーザーID＋解決済みクライアントIPを鍵として、認証済みAPI向けのレート制限を適用する。

	Args:
		request: レート制限対象のHTTPリクエスト。
		user: 認証済みユーザー。
		settings: 信頼済みプロキシ設定を含むバックエンド設定。
		scope: レート制限のスコープ名（Redisキーの名前空間）。
		max_requests: `window`秒間に許可する最大リクエスト数。
		window: レート制限の時間窓（秒）。

	Raises:
		TooManyAttemptsError: 上限を超えた場合。
		ServiceUnavailableError: Redis障害時（fail-close）。
	"""
	value = f"{user.id}:{_resolved_client_ip(request, settings)}"
	await _enforce_rate_limit_by_key(scope, value, max_requests, window)


async def enforce_notification_read_rate_limit(
	request: Request,
	user: CurrentUser = Depends(get_current_user),
	settings: BackendSettings = Depends(get_backend_settings),
) -> None:
	"""通知参照系（一覧・未読件数）APIのレート制限。user_id+解決済みIP単位で判定する。"""
	await _enforce_rate_limit(
		request,
		user,
		settings,
		"notification_read",
		settings.rate_limit_notification_read_max_requests,
		settings.rate_limit_notification_window_seconds,
	)


async def enforce_notification_write_rate_limit(
	request: Request,
	user: CurrentUser = Depends(get_current_user),
	settings: BackendSettings = Depends(get_backend_settings),
) -> None:
	"""通知更新系（個別既読・全既読）APIのレート制限。user_id+解決済みIP単位で判定する。"""
	await _enforce_rate_limit(
		request,
		user,
		settings,
		"notification_write",
		settings.rate_limit_notification_write_max_requests,
		settings.rate_limit_notification_window_seconds,
	)


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
		await _enforce_rate_limit_by_key(scope, client_ip, max_requests, window)

	return _enforce
