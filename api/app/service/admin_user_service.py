"""管理者によるユーザー操作の業務ロジック。

参照設計書:
- docs/detailed_design/api/admin/01_get_admin_users.md
- docs/detailed_design/api/admin/02_patch_admin_user_role.md
- docs/detailed_design/api/admin/03_patch_admin_user_status.md
- docs/detailed_design/api/admin/04_post_admin_user_force_logout.md

DBの自己変更禁止（P0007）・最後の管理者保護（P0008）はsp_admin_update_user_role /
sp_admin_update_user_status内部でadvisory lockとともに一体実行される（#137）。
本サービスはSQLSTATEをアプリ例外へ変換するだけで、判定ロジック自体は持たない。
"""

import logging
from uuid import UUID

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_backend_settings
from app.core.exceptions import LastAdminRequiredError, NotFoundError, SelfModificationError, ServiceUnavailableError
from app.models.user import User
from app.repository import admin_repository, redis_store, user_repository
from app.schemas.admin import (
	AdminUserDetailResponse,
	AdminUserItem,
	AdminUserListMeta,
	AdminUserListQuery,
	AdminUserListResponse,
)
from app.schemas.auth import CurrentUser

logger = logging.getLogger("app.audit")

_SELF_MODIFICATION_SQLSTATE = "P0007"
_LAST_ADMIN_SQLSTATE = "P0008"


def _display_name(user: User) -> str:
	return " ".join(part for part in (user.last_name, user.first_name) if part) or user.username


def _to_item(user: User) -> AdminUserItem:
	return AdminUserItem(
		id=user.id,
		username=user.username,
		email=user.email,
		display_name=_display_name(user),
		role=user.role,
		is_active=user.is_active,
		email_verified_at=user.email_verified_at,
		created_at=user.created_at,
	)


def _to_detail(user: User) -> AdminUserDetailResponse:
	return AdminUserDetailResponse(**_to_item(user).model_dump(), updated_at=user.updated_at)


def _raise_for_sqlstate(exc: DBAPIError, *, self_message: str, last_admin_message: str) -> None:
	sqlstate = getattr(exc.orig, "sqlstate", None)
	if sqlstate == _SELF_MODIFICATION_SQLSTATE:
		raise SelfModificationError(self_message) from exc
	if sqlstate == _LAST_ADMIN_SQLSTATE:
		raise LastAdminRequiredError(last_admin_message) from exc
	raise ServiceUnavailableError() from exc


async def _get_existing_user(db: AsyncSession, target_id: UUID) -> User:
	try:
		target = await user_repository.get_by_id(db, target_id)
	except DBAPIError as exc:
		raise ServiceUnavailableError() from exc
	if target is None:
		raise NotFoundError("ユーザーが見つかりません")
	return target


async def list_users(query: AdminUserListQuery, db: AsyncSession) -> AdminUserListResponse:
	"""検索・ページング条件で全ユーザーを一覧取得する（01_get_admin_users.md §6.2）。

	fn_admin_list_usersは合計件数を返さないため、上限件数までを1回で取得し、
	総件数とページ分の切り出しをアプリ側で行う（要検討: 大量データ時はDB側の
	件数専用FN追加が望ましい）。
	"""
	settings = get_backend_settings()
	offset = (query.page - 1) * query.per_page
	try:
		matched = await admin_repository.list_users(
			db, query.q, query.role, query.is_active, settings.admin_list_count_query_limit, 0
		)
	except DBAPIError as exc:
		raise ServiceUnavailableError() from exc
	total = len(matched)
	page_users = matched[offset : offset + query.per_page]
	total_pages = (total + query.per_page - 1) // query.per_page if total else 0
	return AdminUserListResponse(
		items=[_to_item(user) for user in page_users],
		meta=AdminUserListMeta(page=query.page, per_page=query.per_page, total=total, total_pages=total_pages),
	)


async def change_role(actor: CurrentUser, target_id: UUID, new_role: str, db: AsyncSession) -> AdminUserDetailResponse:
	await _get_existing_user(db, target_id)
	try:
		await admin_repository.update_user_role(db, actor.id, target_id, new_role)
		await db.commit()
	except DBAPIError as exc:
		await db.rollback()
		_raise_for_sqlstate(
			exc,
			self_message="自分自身のロールは変更できません",
			last_admin_message="最後の管理者を降格することはできません",
		)
	updated = await _get_existing_user(db, target_id)
	logger.info(
		"admin changed user role",
		extra={"actor_id": str(actor.id), "target_id": str(target_id), "new_role": new_role},
	)
	return _to_detail(updated)


async def change_status(
	actor: CurrentUser,
	target_id: UUID,
	new_is_active: bool,
	db: AsyncSession,
) -> AdminUserDetailResponse:
	await _get_existing_user(db, target_id)
	try:
		await admin_repository.update_user_status(db, actor.id, target_id, new_is_active)
		await db.commit()
	except DBAPIError as exc:
		await db.rollback()
		_raise_for_sqlstate(
			exc,
			self_message="自分自身は無効化できません",
			last_admin_message="最後の管理者を無効化することはできません",
		)
	if not new_is_active:
		# DB更新のcommitを先に確定させたうえでRedisを失効させる（DB先行が正。#333）。
		# Redis失効が失敗してもDBの無効化はロールバックしない（フェイルセーフ側へ倒す）。
		try:
			await redis_store.delete_all_sessions(target_id)
			await redis_store.revoke_all_refresh_tokens(target_id)
		except Exception as exc:  # noqa: BLE001
			raise ServiceUnavailableError() from exc
	updated = await _get_existing_user(db, target_id)
	logger.info(
		"admin changed user status",
		extra={"actor_id": str(actor.id), "target_id": str(target_id), "new_is_active": new_is_active},
	)
	return _to_detail(updated)


async def force_logout(actor: CurrentUser, target_id: UUID, db: AsyncSession) -> None:
	await _get_existing_user(db, target_id)
	try:
		await redis_store.delete_all_sessions(target_id)
		await redis_store.revoke_all_refresh_tokens(target_id)
	except Exception as exc:  # noqa: BLE001
		raise ServiceUnavailableError() from exc
	logger.info("admin forced logout", extra={"actor_id": str(actor.id), "target_id": str(target_id)})
