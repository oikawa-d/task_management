"""users/me（プロフィール・パスワード・ログイン履歴）の業務ロジック。

参照設計書:
- docs/detailed_design/api/users/01_get_users_me.md
- docs/detailed_design/api/users/02_patch_users_me.md
- docs/detailed_design/api/users/03_put_users_me_password.md
- docs/detailed_design/api/users/04_get_users_me_login_history.md

パスワードのハッシュ化・検証はcore/security.py側の共通実装（#86/#87）を利用する。
"""

from datetime import date
from uuid import UUID

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
	InvalidCredentialsError,
	NotFoundError,
	ServiceUnavailableError,
	ValidationError,
	raise_database_error,
)
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.repository import login_history_repository, oauth_account_repository, redis_store, user_repository
from app.schemas.auth import CurrentUser
from app.schemas.user import (
	LoginHistoryItem,
	LoginHistoryListResponse,
	LoginHistoryMeta,
	PasswordChangeRequest,
	UserProfileResponse,
	UserProfileUpdateRequest,
)

_PROFILE_FIELDS = ("last_name", "first_name", "last_name_kana", "first_name_kana", "birth_date")


def _is_profile_completed(
	last_name: str | None,
	first_name: str | None,
	last_name_kana: str | None,
	first_name_kana: str | None,
	birth_date: date | None,
) -> bool:
	"""プロフィール入力必須項目がすべて埋まっているかを判定する。

	Args:
		last_name: 姓。
		first_name: 名。
		last_name_kana: 姓（カナ）。
		first_name_kana: 名（カナ）。
		birth_date: 生年月日。

	Returns:
		bool: 5項目すべてが`None`でなければ`True`。
	"""
	return all(value is not None for value in (last_name, first_name, last_name_kana, first_name_kana, birth_date))


def _build_profile_response(
	*,
	user_id: UUID,
	username: str,
	email: str,
	last_name: str | None,
	first_name: str | None,
	last_name_kana: str | None,
	first_name_kana: str | None,
	birth_date: date | None,
	role: str,
	has_password: bool,
	oauth_providers: list[str],
) -> UserProfileResponse:
	"""ユーザープロフィールの各フィールドからレスポンスを組み立てる。

	`profile_completed`はここで`_is_profile_completed`により算出する。

	Args:
		user_id: ユーザーID。
		username: ログインID。
		email: メールアドレス。
		last_name: 姓。
		first_name: 名。
		last_name_kana: 姓（カナ）。
		first_name_kana: 名（カナ）。
		birth_date: 生年月日。
		role: ロール（`admin`/`user`等）。
		has_password: パスワード認証を設定済みかどうか（OAuth限定登録では`False`）。
		oauth_providers: 連携済みOAuthプロバイダ名の一覧。

	Returns:
		UserProfileResponse: レスポンス表示用のプロフィール。
	"""
	return UserProfileResponse(
		id=user_id,
		username=username,
		email=email,
		last_name=last_name,
		first_name=first_name,
		last_name_kana=last_name_kana,
		first_name_kana=first_name_kana,
		birth_date=birth_date,
		profile_completed=_is_profile_completed(last_name, first_name, last_name_kana, first_name_kana, birth_date),
		role=role,
		has_password=has_password,
		oauth_providers=oauth_providers,
	)


async def _response_from_user(db: AsyncSession, user: User) -> UserProfileResponse:
	"""ユーザーモデルから連携OAuthプロバイダ一覧を取得し、プロフィールレスポンスを組み立てる。

	Args:
		db: OAuth連携情報取得に使用する非同期DBセッション。
		user: 対象ユーザー。

	Returns:
		UserProfileResponse: レスポンス表示用のプロフィール。
	"""
	providers = await oauth_account_repository.list_by_user_id(db, user.id)
	return _build_profile_response(
		user_id=user.id,
		username=user.username,
		email=user.email,
		last_name=user.last_name,
		first_name=user.first_name,
		last_name_kana=user.last_name_kana,
		first_name_kana=user.first_name_kana,
		birth_date=user.birth_date,
		role=user.role,
		has_password=user.password_hash is not None,
		oauth_providers=[account.provider for account in providers],
	)


async def get_profile(current_user: CurrentUser, db: AsyncSession) -> UserProfileResponse:
	"""ログインユーザー自身のプロフィールを取得する。

	Args:
		current_user: 取得対象のログインユーザー。
		db: ユーザー取得に使用する非同期DBセッション。

	Returns:
		UserProfileResponse: プロフィール情報。

	Raises:
		NotFoundError: トークンに含まれるユーザーがDB上に存在しない場合
			（削除済み等の想定外の不整合）。
	"""
	user = await user_repository.get_by_id(db, current_user.id)
	if user is None:
		raise NotFoundError()
	return await _response_from_user(db, user)


async def update_profile(
	current_user: CurrentUser, payload: UserProfileUpdateRequest, db: AsyncSession
) -> UserProfileResponse:
	"""ログインユーザー自身のプロフィールを部分更新する。

	リクエストで指定されたフィールドのみを更新し（`model_fields_set`による
	部分更新判定）、未指定フィールドは既存値を維持する。指定されたフィールドに
	`null`が渡された場合は必須項目のnull不可制約として`ValidationError`とする。
	プロフィール更新・OAuth連携一覧再取得・コミットが本関数のトランザクション境界である。

	Args:
		current_user: 更新対象のログインユーザー。
		payload: 更新したいフィールドを含むリクエスト（未指定フィールドは維持）。
		db: プロフィール取得・更新に使用する非同期DBセッション。

	Returns:
		UserProfileResponse: 更新後のプロフィール。

	Raises:
		NotFoundError: トークンに含まれるユーザーがDB上に存在しない場合
			（削除済み等の想定外の不整合）。
		ValidationError: 更新対象フィールドに`null`が指定された場合。
		app.core.exceptions.AppError: DB更新でSQLSTATEエラーが発生した場合、
			`raise_database_error`により業務例外へ変換されて送出される。
	"""
	user = await user_repository.get_by_id(db, current_user.id)
	if user is None:
		raise NotFoundError()

	fields_set = payload.model_fields_set
	merged: dict[str, str | date | None] = {}
	for field in _PROFILE_FIELDS:
		if field in fields_set:
			value = getattr(payload, field)
			if value is None:
				raise ValidationError(details=[{"field": field, "message": "null is not allowed"}])
			merged[field] = value
		else:
			merged[field] = getattr(user, field)

	try:
		await user_repository.update_profile(
			db,
			current_user.id,
			last_name=merged["last_name"],  # type: ignore[arg-type]
			first_name=merged["first_name"],  # type: ignore[arg-type]
			last_name_kana=merged["last_name_kana"],  # type: ignore[arg-type]
			first_name_kana=merged["first_name_kana"],  # type: ignore[arg-type]
			birth_date=merged["birth_date"],  # type: ignore[arg-type]
		)
		providers = await oauth_account_repository.list_by_user_id(db, current_user.id)
		await db.commit()
		return _build_profile_response(
			user_id=user.id,
			username=user.username,
			email=user.email,
			last_name=merged["last_name"],  # type: ignore[arg-type]
			first_name=merged["first_name"],  # type: ignore[arg-type]
			last_name_kana=merged["last_name_kana"],  # type: ignore[arg-type]
			first_name_kana=merged["first_name_kana"],  # type: ignore[arg-type]
			birth_date=merged["birth_date"],  # type: ignore[arg-type]
			role=user.role,
			has_password=user.password_hash is not None,
			oauth_providers=[account.provider for account in providers],
		)
	except DBAPIError as exc:
		await db.rollback()
		raise_database_error(exc)


async def change_password(
	current_user: CurrentUser,
	payload: PasswordChangeRequest,
	db: AsyncSession,
) -> None:
	"""ログインユーザー自身のパスワードを変更する。

	既にパスワードが設定済みの場合は現在のパスワードの一致を必須とし、
	未設定（OAuth限定登録）の場合は`current_password`を指定不可とする。
	処理順序はRedis操作が先行しDB更新が後続する。パスワードハッシュ更新の前に
	全セッション削除・全リフレッシュトークン失効をRedis上で行い（パスワード変更を
	トリガーとした強制再ログイン）、これに失敗した場合は`ServiceUnavailableError`
	（503）として送出しDB更新には進まない。パスワードハッシュ更新とコミットが
	本関数のトランザクション境界である。

	Args:
		current_user: 変更対象のログインユーザー。
		payload: 現在のパスワード（該当する場合）と新しいパスワードを含むリクエスト。
		db: パスワード取得・更新に使用する非同期DBセッション。

	Returns:
		None

	Raises:
		NotFoundError: トークンに含まれるユーザーがDB上に存在しない場合
			（削除済み等の想定外の不整合）。
		ValidationError: パスワード設定済みなのに`current_password`が未指定の場合、
			または未設定なのに`current_password`が指定された場合。
		InvalidCredentialsError: 現在のパスワードが一致しない場合。
		ServiceUnavailableError: Redisでのセッション削除・リフレッシュトークン失効に
			失敗した場合。
		app.core.exceptions.AppError: DB更新でSQLSTATEエラーが発生した場合、
			`raise_database_error`により業務例外へ変換されて送出される。
	"""
	user = await user_repository.get_by_id(db, current_user.id)
	if user is None:
		raise NotFoundError()

	has_password = user.password_hash is not None
	if has_password:
		if payload.current_password is None:
			raise ValidationError(details=[{"field": "current_password", "message": "current_password is required"}])
		if not verify_password(payload.current_password, user.password_hash):  # type: ignore[arg-type]
			raise InvalidCredentialsError(message="現在のパスワードが正しくありません")
	elif payload.current_password is not None:
		raise ValidationError(details=[{"field": "current_password", "message": "current_password is not allowed"}])

	new_password_hash = hash_password(payload.new_password)

	try:
		await redis_store.delete_all_sessions(current_user.id)
		await redis_store.revoke_all_refresh_tokens(current_user.id)
	except Exception as exc:
		raise ServiceUnavailableError() from exc

	try:
		await user_repository.update_password(db, current_user.id, new_password_hash)
		await db.commit()
	except DBAPIError as exc:
		await db.rollback()
		raise_database_error(exc)


async def get_login_history(current_user: CurrentUser, db: AsyncSession, limit: int) -> LoginHistoryListResponse:
	"""ログインユーザー自身のログイン履歴を新しい順に取得する。

	Args:
		current_user: 取得対象のログインユーザー。
		db: 履歴取得に使用する非同期DBセッション。
		limit: 取得件数上限。

	Returns:
		LoginHistoryListResponse: ログイン履歴一覧と取得件数。
	"""
	histories = await login_history_repository.list_by_user_id(db, current_user.id, limit=limit, offset=0)
	items = [
		LoginHistoryItem(
			id=history.id,
			login_method=history.login_method,
			ip_address=str(history.ip_address) if history.ip_address is not None else None,
			user_agent=history.user_agent,
			success=history.success,
			failure_reason=history.failure_reason,
			created_at=history.created_at,
		)
		for history in histories
	]
	return LoginHistoryListResponse(items=items, meta=LoginHistoryMeta(limit=limit, count=len(items)))
