"""管理者によるユーザー操作の業務ロジック。

参照設計書:
- docs/detailed_design/api/admin/01_get_admin_users.md
- docs/detailed_design/api/admin/02_patch_admin_user_role.md
- docs/detailed_design/api/admin/03_patch_admin_user_status.md
- docs/detailed_design/api/admin/04_post_admin_user_force_logout.md

DBの対象不存在（P0010）・自己変更禁止（P0007）・最後の管理者保護（P0008）は
sp_admin_update_user_role / sp_admin_update_user_status内部でadvisory lockとともに
一体実行される（#137、#347レビュー対応）。本サービスはSQLSTATEをアプリ例外へ
変換するだけで、判定ロジック自体は持たない。更新前の値（old_role/old_is_active）は
SPのOUTパラメータから受け取るため、事前の存在確認SELECTは行わない。
"""

import logging
from typing import NoReturn
from uuid import UUID

from redis.exceptions import RedisError
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

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

_NOT_FOUND_SQLSTATE = "P0010"
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


def _raise_for_sqlstate(
	exc: DBAPIError, *, not_found_message: str, self_message: str, last_admin_message: str
) -> NoReturn:
	sqlstate = getattr(exc.orig, "sqlstate", None)
	if sqlstate == _NOT_FOUND_SQLSTATE:
		raise NotFoundError(not_found_message) from exc
	if sqlstate == _SELF_MODIFICATION_SQLSTATE:
		raise SelfModificationError(self_message) from exc
	if sqlstate == _LAST_ADMIN_SQLSTATE:
		raise LastAdminRequiredError(last_admin_message) from exc
	raise ServiceUnavailableError() from exc


async def _fetch_user_or_error(db: AsyncSession, target_id: UUID) -> User:
	try:
		target = await user_repository.get_by_id(db, target_id)
	except DBAPIError as exc:
		raise ServiceUnavailableError() from exc
	if target is None:
		raise NotFoundError("ユーザーが見つかりません")
	return target


async def list_users(query: AdminUserListQuery, db: AsyncSession) -> AdminUserListResponse:
	"""検索・ページング条件で全ユーザーを一覧取得する（01_get_admin_users.md §6.2）。

	fn_admin_list_usersはウィンドウ関数count(*) OVER()でtotal_countを同時に返す。
	該当ページが0件（総件数を超えるページ指定等）の場合のみfn_count_admin_usersへ
	フォールバックする（#347レビュー対応。issue #143/PR #294と同一手法）。
	"""
	offset = (query.page - 1) * query.per_page
	try:
		rows = await admin_repository.list_users(db, query.q, query.role, query.is_active, query.per_page, offset)
		total = (
			rows[0].total_count
			if rows
			else await admin_repository.count_users(db, query.q, query.role, query.is_active)
		)
	except DBAPIError as exc:
		raise ServiceUnavailableError() from exc
	total_pages = (total + query.per_page - 1) // query.per_page if total else 0
	return AdminUserListResponse(
		items=[_to_item(row.user) for row in rows],
		meta=AdminUserListMeta(page=query.page, per_page=query.per_page, total=total, total_pages=total_pages),
	)


async def change_role(actor: CurrentUser, target_id: UUID, new_role: str, db: AsyncSession) -> AdminUserDetailResponse:
	try:
		old_role = await admin_repository.update_user_role(db, actor.id, target_id, new_role)
		await db.commit()
	except DBAPIError as exc:
		await db.rollback()
		try:
			_raise_for_sqlstate(
				exc,
				not_found_message="ユーザーが見つかりません",
				self_message="自分自身のロールは変更できません",
				last_admin_message="最後の管理者を降格することはできません",
			)
		except (SelfModificationError, LastAdminRequiredError) as app_error:
			logger.info(
				"admin changed user role",
				extra={
					"actor_id": str(actor.id),
					"target_id": str(target_id),
					"new_role": new_role,
					"result": app_error.code,
				},
			)
			raise
	updated = await _fetch_user_or_error(db, target_id)
	logger.info(
		"admin changed user role",
		extra={
			"actor_id": str(actor.id),
			"target_id": str(target_id),
			"old_role": old_role,
			"new_role": new_role,
			"result": "success",
		},
	)
	return _to_detail(updated)


async def change_status(
	actor: CurrentUser,
	target_id: UUID,
	new_is_active: bool,
	db: AsyncSession,
) -> AdminUserDetailResponse:
	try:
		old_is_active = await admin_repository.update_user_status(db, actor.id, target_id, new_is_active)
		await db.commit()
	except DBAPIError as exc:
		await db.rollback()
		_raise_for_sqlstate(
			exc,
			not_found_message="ユーザーが見つかりません",
			self_message="自分自身は無効化できません",
			last_admin_message="最後の管理者を無効化することはできません",
		)

	session_count = 0
	refresh_count = 0
	if not new_is_active:
		# DB更新のcommitを先に確定させたうえでRedisを失効させる（DB先行が正。#333）。
		# Redis失効が失敗してもDBの無効化はロールバックしない（フェイルセーフ側へ倒す）。
		# 失敗した操作を運用者が検知できるようERROR監査ログを出力してから503にする。
		try:
			session_count = await redis_store.delete_all_sessions(target_id)
		except RedisError as exc:
			logger.error(
				"admin status change: failed to revoke sessions",
				extra={"actor_id": str(actor.id), "target_id": str(target_id), "operation": "delete_all_sessions"},
			)
			raise ServiceUnavailableError() from exc
		try:
			refresh_count = await redis_store.revoke_all_refresh_tokens(target_id)
		except RedisError as exc:
			logger.error(
				"admin status change: failed to revoke refresh tokens",
				extra={
					"actor_id": str(actor.id),
					"target_id": str(target_id),
					"operation": "revoke_all_refresh_tokens",
				},
			)
			raise ServiceUnavailableError() from exc

	updated = await _fetch_user_or_error(db, target_id)
	logger.info(
		"admin changed user status",
		extra={
			"actor_id": str(actor.id),
			"target_id": str(target_id),
			"old_is_active": old_is_active,
			"new_is_active": new_is_active,
			"session_revoked_count": session_count,
			"refresh_revoked_count": refresh_count,
		},
	)
	return _to_detail(updated)


async def force_logout(actor: CurrentUser, target_id: UUID, db: AsyncSession) -> None:
	await _fetch_user_or_error(db, target_id)
	try:
		session_count = await redis_store.delete_all_sessions(target_id)
		refresh_count = await redis_store.revoke_all_refresh_tokens(target_id)
	except RedisError as exc:
		raise ServiceUnavailableError() from exc
	logger.info(
		"admin forced logout",
		extra={
			"actor_id": str(actor.id),
			"target_id": str(target_id),
			"session_revoked_count": session_count,
			"refresh_revoked_count": refresh_count,
		},
	)
