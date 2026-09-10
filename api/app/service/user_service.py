"""users/me（プロフィール・パスワード・ログイン履歴）の業務ロジック。

参照設計書:
- docs/detailed_design/api/users/01_get_users_me.md
- docs/detailed_design/api/users/02_patch_users_me.md
- docs/detailed_design/api/users/03_put_users_me_password.md
- docs/detailed_design/api/users/04_get_users_me_login_history.md

パスワードのハッシュ化・検証はcore/security.py側の実装（#86/#87）に依存するため、
本サービスは関数引数(verify_password/hash_password)としてのみ受け取り、
argon2等の具体実装には一切依存しない。
"""

from collections.abc import Callable
from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidCredentialsError, NotFoundError, ServiceUnavailableError, ValidationError
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

PasswordVerifier = Callable[[str, str], bool]
PasswordHasher = Callable[[str], str]

_PROFILE_FIELDS = ("last_name", "first_name", "last_name_kana", "first_name_kana", "birth_date")


def _is_profile_completed(
	last_name: str | None,
	first_name: str | None,
	last_name_kana: str | None,
	first_name_kana: str | None,
	birth_date: date | None,
) -> bool:
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
	user = await user_repository.get_by_id(db, current_user.id)
	if user is None:
		raise NotFoundError()
	return await _response_from_user(db, user)


async def update_profile(
	current_user: CurrentUser, payload: UserProfileUpdateRequest, db: AsyncSession
) -> UserProfileResponse:
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


async def change_password(
	current_user: CurrentUser,
	payload: PasswordChangeRequest,
	db: AsyncSession,
	*,
	verify_password: PasswordVerifier,
	hash_password: PasswordHasher,
) -> None:
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

	await user_repository.update_password(db, current_user.id, new_password_hash)


async def get_login_history(current_user: CurrentUser, db: AsyncSession, limit: int) -> LoginHistoryListResponse:
	histories = await login_history_repository.list_by_user_id(db, current_user.id, limit=limit, offset=0)
	items = [LoginHistoryItem.model_validate(history) for history in histories]
	return LoginHistoryListResponse(items=items, meta=LoginHistoryMeta(limit=limit, count=len(items)))
