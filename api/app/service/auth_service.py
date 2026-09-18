"""基本認証（登録・ログイン・ログアウト・更新・公開設定）のサービス。"""

from __future__ import annotations

from fastapi import BackgroundTasks, Request, Response
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.base import AuthStrategy, LoginResult
from app.core.client_ip import ClientIpInfo, resolve_client_ip
from app.core.config import BackendSettings, get_backend_settings
from app.core.exceptions import (
	DuplicateEmailError,
	DuplicateUsernameError,
	EmailNotVerifiedError,
	InvalidCredentialsError,
	ServiceUnavailableError,
	TooManyAttemptsError,
	UserInactiveError,
	is_service_unavailable_database_error,
	raise_database_error,
)
from app.core.security import get_dummy_password_hash, hash_password, verify_password
from app.models.user import User
from app.repository import login_history_repository, redis_store, user_repository
from app.schemas.auth import AuthConfigResponse, RegisterRequest
from app.service import email_verification_service
from app.service.auth_logging import (
	SERVICE_UNAVAILABLE_FAILURE_REASON,
	log_auth_state_revoke_failed,
	log_login_attempt,
	log_login_history_write_failed,
	log_user_registered,
)

_SQLSTATE_DUPLICATE_USERNAME = "P0001"
_SQLSTATE_DUPLICATE_EMAIL = "P0002"
_LOGIN_FAILURE_INVALID_CREDENTIALS = "invalid_credentials"
_LOGIN_FAILURE_USER_INACTIVE = "user_inactive"
_LOGIN_FAILURE_EMAIL_NOT_VERIFIED = "email_not_verified"
_LOGIN_FAILURE_TOO_MANY_ATTEMPTS = "too_many_attempts"


def get_auth_config(settings: BackendSettings | None = None) -> AuthConfigResponse:
	"""フロントエンド向けの認証設定（認証モード・Google連携可否・CSRF Cookie名）を返す。

	Google連携の有効判定は、設定フラグに加えクライアントID・シークレットが
	いずれも設定されていることを条件とする。

	Args:
		settings: 使用する設定。省略時はプロセス共通設定を取得する。

	Returns:
		AuthConfigResponse: フロントエンド向けの認証設定。
	"""
	config = settings or get_backend_settings()
	return AuthConfigResponse(
		auth_mode=config.auth_mode,
		google_login_enabled=bool(
			config.google_login_enabled and config.google_client_id and config.google_client_secret
		),
		csrf_cookie_name=config.cookie_name_csrf,
	)


async def ensure_login_not_rate_limited(identifier: str, client_ip: str, settings: BackendSettings) -> None:
	"""識別子とIPの組み合わせに対するログイン試行回数制限（Rate Limit）を検証する。

	失敗回数はRedisで管理し、上限に達している場合は残りロック時間を
	`Retry-After`として`TooManyAttemptsError`に含める。

	Args:
		identifier: ログインに使用された識別子（メールアドレス等）。
		client_ip: クライアントの送信元IPアドレス。
		settings: ログイン試行上限・ロック時間窓を含むバックエンド設定。

	Returns:
		None: 制限に達していない場合は何もしない。

	Raises:
		TooManyAttemptsError: 失敗回数が上限に達している場合（429 TOO_MANY_ATTEMPTS）。
	"""
	failure_count = await redis_store.get_login_failure_count(identifier, client_ip)
	if failure_count >= settings.login_max_attempts:
		ttl = await redis_store.get_login_failure_ttl(identifier, client_ip)
		raise TooManyAttemptsError(retry_after=ttl if ttl > 0 else settings.login_lock_window_seconds)


async def record_login_failure(identifier: str, client_ip: str, settings: BackendSettings) -> int:
	"""ログイン失敗回数をRedis上でインクリメントする。

	Args:
		identifier: ログインに使用された識別子（メールアドレス等）。
		client_ip: クライアントの送信元IPアドレス。
		settings: ロック時間窓（TTL）を含むバックエンド設定。

	Returns:
		int: インクリメント後の失敗回数。
	"""
	return await redis_store.incr_login_failure(identifier, client_ip, settings.login_lock_window_seconds)


async def record_login_success(identifier: str, client_ip: str) -> None:
	"""ログイン成功時にRedis上の失敗回数カウンタをリセットする。

	Args:
		identifier: ログインに使用された識別子（メールアドレス等）。
		client_ip: クライアントの送信元IPアドレス。

	Returns:
		None
	"""
	await redis_store.reset_login_failure(identifier, client_ip)


def _duplicate_error_for(exc: DBAPIError) -> DuplicateUsernameError | DuplicateEmailError | None:
	"""ユーザー登録時のDB一意制約違反を、SQLSTATEに応じた業務例外へ変換する。

	Args:
		exc: `user_repository.create`等から送出されたDBAPIError。

	Returns:
		DuplicateUsernameError | DuplicateEmailError | None: 対応する重複エラー。
			一意制約違反以外のSQLSTATEの場合は`None`。
	"""
	sqlstate = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)
	if sqlstate == _SQLSTATE_DUPLICATE_USERNAME:
		return DuplicateUsernameError()
	if sqlstate == _SQLSTATE_DUPLICATE_EMAIL:
		return DuplicateEmailError()
	return None


async def register(payload: RegisterRequest, background: BackgroundTasks, request: Request, db: AsyncSession) -> User:
	"""新規ユーザーを登録し、メール認証トークンの発行と監査ログ記録を行う。

	ユーザー名・メールアドレスの重複はDB制約違反発生前に事前チェックで検出するが、
	競合による制約違反発生時（DB制約違反のフォールバック）はSQLSTATEから
	`DuplicateUsernameError` / `DuplicateEmailError`へ変換する。
	ユーザー作成・プロフィール登録・コミットが本関数のトランザクション境界である。
	コミット後、登録直後のユーザーが再取得できない場合は`ServiceUnavailableError`とする。

	Args:
		payload: ユーザー名・メール・パスワード・プロフィールを含む登録リクエスト。
		background: メール認証送信タスクを積むFastAPIのバックグラウンドタスク。
		request: 監査ログに記録する現在のリクエスト。
		db: ユーザー作成に使用する非同期DBセッション。

	Returns:
		User: 登録されたユーザー。

	Raises:
		DuplicateUsernameError: ユーザー名が既に使用されている場合。
		DuplicateEmailError: メールアドレスが既に使用されている場合。
		ServiceUnavailableError: 登録後の再取得に失敗した場合（想定外の不整合）。
		app.core.exceptions.AppError: 一意制約違反以外のSQLSTATEエラーが発生した場合、
			`raise_database_error`により業務例外へ変換されて送出される。
	"""
	if await user_repository.get_by_login_identifier(db, payload.username) is not None:
		raise DuplicateUsernameError()
	if await user_repository.get_by_email(db, payload.email) is not None:
		raise DuplicateEmailError()
	password_hash = hash_password(payload.password)
	try:
		user_id = await user_repository.create(db, payload.username, payload.email, password_hash)
		await user_repository.update_profile(
			db,
			user_id,
			payload.last_name,
			payload.first_name,
			payload.last_name_kana,
			payload.first_name_kana,
			payload.birth_date,
		)
		await db.commit()
	except DBAPIError as exc:
		await db.rollback()
		duplicate = _duplicate_error_for(exc)
		if duplicate is None:
			raise_database_error(exc)
		raise duplicate from exc
	user = await user_repository.get_by_id(db, user_id)
	if user is None:
		raise ServiceUnavailableError()
	await email_verification_service.issue_email_verify_token(user, background)
	log_user_registered(request, user)
	return user


async def _record_login_attempt(
	db: AsyncSession,
	user: User | None,
	identifier: str,
	request: Request,
	login_method: str,
	client_ip: str,
	*,
	success: bool,
	failure_reason: str | None,
) -> None:
	"""ログイン試行結果をログイン履歴テーブルへ記録する。

	記録とコミットが本関数のトランザクション境界である。

	Args:
		db: 履歴登録に使用する非同期DBセッション。
		user: ログイン試行対象として特定できたユーザー。未特定の場合は`None`。
		identifier: ログインに使用された識別子（メールアドレス等）。
		request: User-Agent取得に使用する現在のリクエスト。
		login_method: ログイン方式（`session`/`jwt`等）。
		client_ip: クライアントの送信元IPアドレス。
		success: ログインが成功したかどうか。
		failure_reason: 失敗理由（成功時は`None`）。

	Returns:
		None

	Raises:
		app.core.exceptions.AppError: DB登録でSQLSTATEエラーが発生した場合、
			`raise_database_error`により業務例外へ変換されて送出される。
	"""
	try:
		await login_history_repository.create(
			db,
			user_id=user.id if user is not None else None,
			login_identifier=identifier,
			login_method=login_method,
			ip_address=client_ip,
			user_agent=request.headers.get("user-agent"),
			success=success,
			failure_reason=failure_reason,
		)
		await db.commit()
	except DBAPIError as exc:
		await db.rollback()
		raise_database_error(exc)


async def login(
	identifier: str,
	password: str,
	request: Request,
	response: Response,
	db: AsyncSession,
	strategy: AuthStrategy,
) -> LoginResult:
	"""ID/パスワードによるログインを実行する。

	検証順序は (1) Rate Limit（識別子×IP単位） (2) ユーザー存在・パスワード一致
	（存在しない場合もタイミング攻撃対策としてダミーハッシュで検証を行う）
	(3) 有効状態(`is_active`) (4) メール認証済み状態、の順。いずれかで失敗した場合は
	ログイン履歴への記録と監査ログ出力を行ったうえで対応する例外を送出する。
	認証方式固有のセッション/トークン発行は`strategy.login`に委譲し、
	その後のログイン履歴記録に失敗した場合は`strategy.rollback_login`で
	発行済みセッション/トークンを取り消す。

	Args:
		identifier: ログインに使用する識別子（メールアドレス等）。
		password: 平文パスワード。
		request: クライアントIP解決・監査ログに使用する現在のリクエスト。
		response: 認証方式によるCookie設定等に使用するレスポンス。
		db: ユーザー取得・ログイン履歴登録に使用する非同期DBセッション。
		strategy: 認証方式固有の処理（セッション/JWT発行等）を担う戦略。

	Returns:
		LoginResult: ログイン成功時の認証結果（トークン・セッション情報等）。

	Raises:
		TooManyAttemptsError: Rate Limit上限に達している場合（429 TOO_MANY_ATTEMPTS）。
		InvalidCredentialsError: 識別子またはパスワードが一致しない場合。
		UserInactiveError: ユーザーが無効化されている場合。
		EmailNotVerifiedError: メール認証が完了していない場合。
		ServiceUnavailableError: Redis/DBの障害によりログイン処理を継続できない場合、
			またはログイン成功後の履歴記録失敗によりロールバックを行った場合。
	"""
	settings = get_backend_settings()
	client_info = resolve_client_ip(request, settings.trusted_proxy_cidrs)
	client_ip = client_info.client_ip
	try:
		await ensure_login_not_rate_limited(identifier, client_ip, settings)
	except TooManyAttemptsError:
		log_login_attempt(
			request, None, client_info, identifier, strategy.mode, False, _LOGIN_FAILURE_TOO_MANY_ATTEMPTS
		)
		raise
	except Exception as exc:
		log_login_attempt(
			request, None, client_info, identifier, strategy.mode, False, SERVICE_UNAVAILABLE_FAILURE_REASON
		)
		raise ServiceUnavailableError() from exc
	try:
		user = await user_repository.get_by_login_identifier(db, identifier)
	except ServiceUnavailableError:
		log_login_attempt(
			request, None, client_info, identifier, strategy.mode, False, SERVICE_UNAVAILABLE_FAILURE_REASON
		)
		raise
	except Exception as exc:
		if not is_service_unavailable_database_error(exc):
			raise
		log_login_attempt(
			request, None, client_info, identifier, strategy.mode, False, SERVICE_UNAVAILABLE_FAILURE_REASON
		)
		raise ServiceUnavailableError() from exc
	stored_hash = user.password_hash if user is not None and user.password_hash is not None else None
	password_matched = verify_password(password, stored_hash or get_dummy_password_hash())
	if user is None or stored_hash is None or not password_matched:
		login_user_id = str(user.id) if user is not None else None
		try:
			await record_login_failure(identifier, client_ip, settings)
		except Exception as exc:
			log_login_attempt(
				request, user, client_info, identifier, strategy.mode, False, SERVICE_UNAVAILABLE_FAILURE_REASON
			)
			raise ServiceUnavailableError() from exc
		try:
			await _record_login_attempt(
				db,
				user,
				identifier,
				request,
				strategy.mode,
				client_ip,
				success=False,
				failure_reason=_LOGIN_FAILURE_INVALID_CREDENTIALS,
			)
		except Exception as exc:
			log_login_history_write_failed(
				request,
				user,
				client_info,
				user_id=login_user_id,
				operation="login",
				login_method=strategy.mode,
			)
			raise ServiceUnavailableError() from exc
		log_login_attempt(
			request, user, client_info, identifier, strategy.mode, False, _LOGIN_FAILURE_INVALID_CREDENTIALS
		)
		raise InvalidCredentialsError()
	try:
		await record_login_success(identifier, client_ip)
	except Exception as exc:
		log_login_attempt(
			request, user, client_info, identifier, strategy.mode, False, SERVICE_UNAVAILABLE_FAILURE_REASON
		)
		raise ServiceUnavailableError() from exc
	if not user.is_active:
		await _record_login_failure_or_unavailable(
			db, user, identifier, request, client_info, strategy.mode, client_ip, _LOGIN_FAILURE_USER_INACTIVE
		)
		log_login_attempt(request, user, client_info, identifier, strategy.mode, False, _LOGIN_FAILURE_USER_INACTIVE)
		raise UserInactiveError()
	if user.email_verified_at is None:
		await _record_login_failure_or_unavailable(
			db, user, identifier, request, client_info, strategy.mode, client_ip, _LOGIN_FAILURE_EMAIL_NOT_VERIFIED
		)
		log_login_attempt(
			request, user, client_info, identifier, strategy.mode, False, _LOGIN_FAILURE_EMAIL_NOT_VERIFIED
		)
		raise EmailNotVerifiedError()
	try:
		login_result = await strategy.login(user, request, response)
	except Exception as exc:
		log_login_attempt(
			request, user, client_info, identifier, strategy.mode, False, SERVICE_UNAVAILABLE_FAILURE_REASON
		)
		raise ServiceUnavailableError() from exc
	login_user_id = str(user.id)
	try:
		await _record_login_attempt(
			db, user, identifier, request, strategy.mode, client_ip, success=True, failure_reason=None
		)
	except Exception as exc:
		log_login_history_write_failed(
			request,
			user,
			client_info,
			user_id=login_user_id,
			operation="login",
			login_method=strategy.mode,
		)
		try:
			await strategy.rollback_login(user, login_result, response)
		except Exception as rollback_exc:
			log_auth_state_revoke_failed(request, user, "login_rollback", client_info, user_id=login_user_id)
			raise ServiceUnavailableError() from rollback_exc
		raise ServiceUnavailableError() from exc
	log_login_attempt(request, user, client_info, identifier, strategy.mode, True, None)
	return login_result


async def _record_login_failure_or_unavailable(
	db: AsyncSession,
	user: User,
	identifier: str,
	request: Request,
	client_info: ClientIpInfo,
	login_method: str,
	client_ip: str,
	reason: str,
) -> None:
	"""ログイン失敗（無効ユーザー・メール未認証）を履歴へ記録し、失敗時は503へ変換する。

	Args:
		db: 履歴登録に使用する非同期DBセッション。
		user: ログイン試行対象のユーザー。
		identifier: ログインに使用された識別子（メールアドレス等）。
		request: 監査ログに使用する現在のリクエスト。
		client_info: クライアントIP等の接続元情報。
		login_method: ログイン方式（`session`/`jwt`等）。
		client_ip: クライアントの送信元IPアドレス。
		reason: 記録する失敗理由。

	Returns:
		None

	Raises:
		ServiceUnavailableError: ログイン履歴の記録自体に失敗した場合。
	"""
	login_user_id = str(user.id)
	try:
		await _record_login_attempt(
			db, user, identifier, request, login_method, client_ip, success=False, failure_reason=reason
		)
	except Exception as exc:
		log_login_history_write_failed(
			request,
			user,
			client_info,
			user_id=login_user_id,
			operation="login",
			login_method=login_method,
			failure_reason=SERVICE_UNAVAILABLE_FAILURE_REASON,
		)
		raise ServiceUnavailableError() from exc


async def logout(request: Request, response: Response, strategy: AuthStrategy) -> None:
	"""ログアウトを実行する。

	セッション/トークンの失効処理自体は認証方式固有の`strategy.logout`に委譲する。

	Args:
		request: ログアウト対象の現在のリクエスト。
		response: Cookie削除等に使用するレスポンス。
		strategy: 認証方式固有の処理を担う戦略。

	Returns:
		None
	"""
	await strategy.logout(request, response)


async def refresh(request: Request, response: Response, strategy: AuthStrategy) -> LoginResult:
	"""アクセストークン/セッションの更新を実行する。

	更新処理自体は認証方式固有の`strategy.refresh`に委譲する。セッション認証モードでは
	`NOT_SUPPORTED_IN_MODE`（405）として拒否される（`strategy`実装側の責務）。

	Args:
		request: 更新対象の現在のリクエスト。
		response: Cookie更新等に使用するレスポンス。
		strategy: 認証方式固有の処理を担う戦略。

	Returns:
		LoginResult: 更新後の認証結果。

	Raises:
		NotSupportedInModeError: セッション認証モードで呼び出された場合（405 NOT_SUPPORTED_IN_MODE）。
		TokenInvalidError: リフレッシュトークンCookieが無い場合（JWTモード）。
		TokenRevokedError: リフレッシュトークンが失効済み、または再利用が検知された場合（JWTモード）。
	"""
	return await strategy.refresh(request, response)
