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
	"""Google OAuth認可フローを開始し、認可URLとCSRF対策用stateを発行する。

	PKCE用のcode_verifier/code_challengeとID Token検証用のnonceを生成し、
	stateとともにRedisへ保存したうえで、state値をHttpOnly Cookieにも設定する
	（callback側でCookie値とcrequest値の一致を照合するため）。

	Args:
		redirect_to: ログイン後にリダイレクトしたいパス（未検証、`normalize_redirect_to`で正規化）。
		request: レート制限判定用のリクエスト（`Request`の場合のみ判定する）。
			互換性のため`Response`が渡された場合は`response`引数として扱う。
		response: state Cookieを設定するレスポンス。
		settings: 使用する設定。省略時はプロセス共通設定を取得する。
		provider: 使用するGoogle OAuthプロバイダ。省略時は設定から生成する。

	Returns:
		OAuthStartResult: 認可URLと発行したstate。

	Raises:
		TooManyAttemptsError: OAuthエンドポイントへのレート制限上限を超過した場合。
		ServiceUnavailableError: Redisへのstate保存に失敗した場合。
	"""
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
	"""Googleユーザー情報からログイン対象ユーザーを解決し、必要なら新規登録・連携する。

	解決順序は次のとおり。(1) 既にGoogleアカウントと連携済みのユーザーがいればそれを使う。
	(2) 未連携だが同一メールアドレスの既存ユーザーがいれば、Google側でメール検証済みの場合に
	限りアカウントを連携し、未認証だったメールアドレスは認証済みへ更新する。
	(3) いずれにも該当しなければ、Google側でメール検証済みの場合に限り新規ユーザーを
	`google_<subのSHA-256先頭16文字>`というusernameで作成し、メール認証済みとして登録する。
	いずれの経路でも無効化済みユーザーへの解決は`UserInactiveError`とする。
	既存ユーザーとの連携、新規作成のいずれもDB更新とコミットが本関数のトランザクション境界である。

	Args:
		db: ユーザー検索・作成・連携に使用する非同期DBセッション。
		userinfo: Googleから取得したユーザー情報（sub・email・email_verified・氏名）。

	Returns:
		User: ログイン対象として解決されたユーザー。

	Raises:
		OAuthFailedError: 連携済みアカウントに紐づくユーザーが取得できない場合、
			または新規作成後の再取得に失敗した場合（想定外の不整合）。
		UserInactiveError: 解決されたユーザーが無効化されている場合。
		OAuthEmailUnverifiedError: Google側でメールアドレスが未検証のため、
			既存アカウントとの連携・新規登録のいずれも行えない場合。
		app.core.exceptions.AppError: DB更新でSQLSTATEエラーが発生した場合、
			`raise_database_error`により業務例外へ変換されて送出される。
	"""
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
	"""`_resolve_or_create_user`のテスト・外部呼び出し用の公開ラッパー。

	個々の引数から`GoogleUserInfo`を組み立てて委譲するのみで、業務ルールは同一。

	Args:
		db: ユーザー検索・作成・連携に使用する非同期DBセッション。
		sub: GoogleアカウントのユーザーID（subject claim）。
		email: Googleアカウントのメールアドレス。
		email_verified: Google側でメールアドレスが検証済みかどうか。
		given_name: Googleアカウントの名（名前）。
		family_name: Googleアカウントの姓。

	Returns:
		User: ログイン対象として解決されたユーザー。

	Raises:
		OAuthFailedError: 連携済みアカウントに紐づくユーザーが取得できない場合、
			または新規作成後の再取得に失敗した場合（想定外の不整合）。
		UserInactiveError: 解決されたユーザーが無効化されている場合。
		OAuthEmailUnverifiedError: Google側でメールアドレスが未検証の場合。
		app.core.exceptions.AppError: DB更新でSQLSTATEエラーが発生した場合、
			`raise_database_error`により業務例外へ変換されて送出される。
	"""
	return await _resolve_or_create_user(db, GoogleUserInfo(sub, email, email_verified, given_name, family_name))


def _auth_strategy(settings: BackendSettings, strategy: Any | None) -> Any:
	"""使用する認証戦略を解決する。

	明示的に`strategy`が渡された場合はそれを優先する。次に、DIコンテナから
	取得した既定の戦略が現在の設定の`auth_mode`と一致すればそれを使う。
	いずれにも該当しない場合は、`settings.auth_mode`に応じて
	`SessionAuthStrategy`または`JwtAuthStrategy`を新規に構築する
	（テストでの`auth_mode`切り替え等、動的な整合性確保のため）。

	Args:
		settings: 現在の`auth_mode`を含むバックエンド設定。
		strategy: 明示的に指定された認証戦略（優先される）。

	Returns:
		Any: 使用する認証戦略インスタンス。
	"""
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
	"""Google側で認可が拒否された場合のcallback処理を行う（state検証とCookie後始末のみ）。

	認可コードが無い（＝Google側で拒否・キャンセルされた）呼び出しに対しても、
	通常のcallbackと同様にstate値の一致検証・Redis上のstate消費を行うことで、
	CSRF対策としてのstate検証を一貫させる。ユーザー解決やログインは行わない。
	stateの照合・消費に成功しても失敗しても、必ずstate Cookieを削除する。

	Args:
		state: クエリパラメータのstate値。
		state_cookie: state Cookieの値。
		request: レート制限判定に使用する現在のリクエスト。
		response: state Cookie削除に使用するレスポンス。
		settings: 使用する設定。省略時はプロセス共通設定を取得する。

	Returns:
		None

	Raises:
		TooManyAttemptsError: OAuthエンドポイントへのレート制限上限を超過した場合。
		InvalidStateError: state値がCookieと一致しない、またはRedis上に存在しない場合
			（400相当 INVALID_STATE。callbackは302リダイレクト）。
		ServiceUnavailableError: Redisへのアクセスに失敗した場合。
	"""
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
	"""Google OAuth callbackの本体処理（state検証・コード交換・ユーザー解決・ログイン）を行う。

	検証順序は (1) レート制限 (2) state値のCookie一致検証・Redis上のstate消費
	(3) 認可コードの有無、の順。認可コード交換で得たID Tokenのsubと
	UserInfoエンドポイントのsubが一致しない場合は`OAuthFailedError`とする
	（トークン置換攻撃対策）。認証モードにより後続処理が分岐する。
	`auth_mode="session"`の場合はその場でセッションを発行しログイン履歴を記録する
	（`complete_oauth_session_login`）。`jwt`モードの場合はセッションを発行せず、
	フロントエンドとのやり取り用にhandoffコードをRedisへ保存して返す
	（実際のトークン発行は`oauth_exchange`で行う）。

	Args:
		code: Googleから返された認可コード。
		state: クエリパラメータのstate値。
		state_cookie: state Cookieの値。
		request: レート制限判定・IP解決に使用する現在のリクエスト。
		response: セッションCookie・state Cookie操作に使用するレスポンス。
		db: ユーザー解決・ログイン履歴記録に使用する非同期DBセッション。
		settings: 使用する設定。省略時はプロセス共通設定を取得する。
		provider: 使用するGoogle OAuthプロバイダ。省略時は設定から生成する。
		strategy: 使用する認証戦略。省略時は`_auth_strategy`で解決する。

	Returns:
		OAuthCallbackResult: 認証モードとリダイレクト先（jwtモードはhandoffコードを含む）。

	Raises:
		TooManyAttemptsError: OAuthエンドポイントへのレート制限上限を超過した場合。
		InvalidStateError: state値がCookieと一致しない、またはRedis上に存在しない場合。
		OAuthFailedError: 認可コード・DBセッションが渡されていない場合、
			ID TokenのsubとUserInfoのsubが一致しない場合、または
			ユーザー解決に失敗した場合（`_resolve_or_create_user`参照）。
		UserInactiveError: 解決されたユーザーが無効化されている場合。
		OAuthEmailUnverifiedError: Google側でメールアドレスが未検証の場合。
		ServiceUnavailableError: Redisへのアクセス失敗、またはセッションモードでの
			ログイン履歴記録失敗によりロールバックした場合。
	"""
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
	"""Google OAuth callbackのエントリポイント。

	`_oauth_callback_impl`へ処理を委譲し、成功・失敗いずれの場合も
	必ずstate Cookieを削除する（`finally`）。業務ルールは`_oauth_callback_impl`と同一。

	Args:
		code: Googleから返された認可コード。
		state: クエリパラメータのstate値。
		state_cookie: state Cookieの値。
		request: レート制限判定・IP解決に使用する現在のリクエスト。
		response: セッションCookie・state Cookie操作に使用するレスポンス。
		db: ユーザー解決・ログイン履歴記録に使用する非同期DBセッション。
		settings: 使用する設定。省略時はプロセス共通設定を取得する。
		provider: 使用するGoogle OAuthプロバイダ。省略時は設定から生成する。
		strategy: 使用する認証戦略。省略時は`_auth_strategy`で解決する。

	Returns:
		OAuthCallbackResult: 認証モードとリダイレクト先（jwtモードはhandoffコードを含む）。

	Raises:
		TooManyAttemptsError: OAuthエンドポイントへのレート制限上限を超過した場合。
		InvalidStateError: state値がCookieと一致しない、またはRedis上に存在しない場合。
		OAuthFailedError: 認可コード・DBセッションが渡されていない場合、
			ID TokenのsubとUserInfoのsubが一致しない場合、または
			ユーザー解決に失敗した場合。
		UserInactiveError: 解決されたユーザーが無効化されている場合。
		OAuthEmailUnverifiedError: Google側でメールアドレスが未検証の場合。
		ServiceUnavailableError: Redisへのアクセス失敗、またはセッションモードでの
			ログイン履歴記録失敗によりロールバックした場合。
	"""
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
	"""JWTモードにおけるOAuth handoffコードをアクセストークンへ交換する。

	handoffコードはRedisから一度きり消費し、対応するユーザーIDを取得する。
	発行されたログイン結果がJWTモードとして必要な項目を満たさない場合
	（`is_valid_jwt_login_result`）は、発行済みトークンを取り消したうえで
	`OAuthFailedError`とする。ログイン履歴の記録に失敗した場合も同様に
	取り消したうえで`ServiceUnavailableError`とする。

	Args:
		code: 交換対象のhandoffコード。
		request: レート制限判定・IP解決に使用する現在のリクエスト。
		response: リフレッシュトークンCookie設定に使用するレスポンス。
		db: ユーザー取得・ログイン履歴記録に使用する非同期DBセッション。
		settings: 使用する設定。省略時はプロセス共通設定を取得する。
		strategy: 使用する認証戦略。省略時は`_auth_strategy`で解決する。

	Returns:
		OAuthExchangeResponse: アクセストークン・有効期限・リダイレクト先。

	Raises:
		TooManyAttemptsError: OAuthエンドポイントへのレート制限上限を超過した場合。
		NotSupportedInModeError: 現在の`AUTH_MODE`がjwtでない場合（405 NOT_SUPPORTED_IN_MODE）。
		OAuthHandoffInvalidError: handoffコードが無効・期限切れ・使用済みの場合。
		OAuthFailedError: DBセッションが渡されていない場合、またはログイン結果が
			JWTモードとして不正な場合（取り消し後に送出）。
		UserInactiveError: handoffに紐づくユーザーが存在しない、または無効化されている場合。
		ServiceUnavailableError: Redisへのアクセス失敗、またはログイン履歴記録の失敗により
			ロールバックした場合。
	"""
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
