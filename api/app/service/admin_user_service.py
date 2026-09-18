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

from app.core.config import get_backend_settings
from app.core.exceptions import (
	LastAdminRequiredError,
	NotFoundError,
	SelfModificationError,
	ServiceUnavailableError,
	raise_database_error,
)
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
	"""ユーザーの表示名を組み立てる。

	姓名が設定されていれば「姓 名」を、いずれも未設定であればログインIDである
	`username`を表示名として用いる。

	Args:
		user: 表示名を求める対象のユーザー。

	Returns:
		str: 表示に用いるユーザー名。
	"""
	return " ".join(part for part in (user.last_name, user.first_name) if part) or user.username


def _to_item(user: User) -> AdminUserItem:
	"""ユーザーを管理者向け一覧のレスポンス要素へ変換する。

	Args:
		user: 変換対象のユーザー。

	Returns:
		AdminUserItem: レスポンス表示用のユーザー要素。
	"""
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
	"""ユーザーを管理者向け詳細のレスポンスへ変換する。

	Args:
		user: 変換対象のユーザー。

	Returns:
		AdminUserDetailResponse: レスポンス表示用のユーザー詳細（更新日時を含む）。
	"""
	return AdminUserDetailResponse(**_to_item(user).model_dump(), updated_at=user.updated_at)


def _raise_for_sqlstate(
	exc: DBAPIError, *, not_found_message: str, self_message: str, last_admin_message: str
) -> NoReturn:
	"""ロール・ステータス更新SPが返すSQLSTATEを対応する業務例外へ変換して送出する。

	`sp_admin_update_user_role` / `sp_admin_update_user_status`はadvisory lockのもとで
	対象不存在（P0010）・自己変更禁止（P0007）・最後の管理者保護（P0008）の判定を
	一体的に行い、違反時はSQLSTATEとして返す。本関数はその変換のみを担い、
	判定ロジック自体は持たない。上記3種以外のSQLSTATEは`raise_database_error`に委譲する。

	Args:
		exc: SPから送出されたDBAPIError。
		not_found_message: 対象ユーザーが存在しない場合のメッセージ。
		self_message: 自分自身を対象にした場合のメッセージ。
		last_admin_message: 最後の有効な管理者を対象にした場合のメッセージ。

	Raises:
		NotFoundError: SQLSTATEが`P0010`（対象ユーザー不存在）の場合。
		SelfModificationError: SQLSTATEが`P0007`（自己変更禁止）の場合。
		LastAdminRequiredError: SQLSTATEが`P0008`（最後の管理者保護）の場合。
		app.core.exceptions.AppError: 上記以外のSQLSTATEの場合、
			`raise_database_error`により対応する業務例外へ変換されて送出される。
	"""
	sqlstate = getattr(exc.orig, "sqlstate", None)
	if sqlstate == _NOT_FOUND_SQLSTATE:
		raise NotFoundError(not_found_message) from exc
	if sqlstate == _SELF_MODIFICATION_SQLSTATE:
		raise SelfModificationError(self_message) from exc
	if sqlstate == _LAST_ADMIN_SQLSTATE:
		raise LastAdminRequiredError(last_admin_message) from exc
	raise_database_error(exc)


async def _fetch_user_or_error(db: AsyncSession, target_id: UUID) -> User:
	"""指定IDのユーザーを取得し、存在しなければ`NotFoundError`とする。

	Args:
		db: ユーザー取得に使用する非同期DBセッション。
		target_id: 取得対象のユーザーID。

	Returns:
		User: 取得したユーザー。

	Raises:
		NotFoundError: 対象ユーザーが存在しない場合。
		app.core.exceptions.AppError: DB問い合わせでSQLSTATEエラーが発生した場合、
			`raise_database_error`により業務例外へ変換されて送出される。
	"""
	try:
		target = await user_repository.get_by_id(db, target_id)
	except DBAPIError as exc:
		raise_database_error(exc)
	if target is None:
		raise NotFoundError("ユーザーが見つかりません")
	return target


async def list_users(query: AdminUserListQuery, db: AsyncSession) -> AdminUserListResponse:
	"""検索・ページング条件で全ユーザーを一覧取得する（01_get_admin_users.md §6.2）。

	`fn_admin_list_users`はウィンドウ関数`count(*) OVER()`で`total_count`を同時に返す。
	該当ページが0件（総件数を超えるページ指定等）の場合のみ`fn_count_admin_users`へ
	フォールバックして総件数を取得する（#347レビュー対応。issue #143/PR #294と同一手法）。

	Args:
		query: 検索語・ロール・有効状態・ページ指定を含む検索条件。
		db: 検索に使用する非同期DBセッション。

	Returns:
		AdminUserListResponse: 該当ページのユーザー一覧とページングメタ情報。

	Raises:
		app.core.exceptions.AppError: DB問い合わせでSQLSTATEエラーが発生した場合、
			`raise_database_error`によりSQLSTATEに対応する業務例外へ変換されて送出される。
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
		raise_database_error(exc)
	total_pages = (total + query.per_page - 1) // query.per_page if total else 0
	return AdminUserListResponse(
		items=[_to_item(row.user) for row in rows],
		meta=AdminUserListMeta(page=query.page, per_page=query.per_page, total=total, total_pages=total_pages),
	)


async def change_role(
	actor: CurrentUser, target_id: UUID, new_role: str, db: AsyncSession, request_id: str | None = None
) -> AdminUserDetailResponse:
	"""管理者が対象ユーザーのロールを変更する（02_patch_admin_user_role.md）。

	対象不存在・自己変更禁止・最後の管理者保護は`sp_admin_update_user_role`が
	advisory lockのもとで一体的に判定し、SQLSTATEとして返す（`_raise_for_sqlstate`参照）。
	SP呼び出しとコミットが本関数のトランザクション境界である。結果（成功・拒否）は
	いずれも監査ログへ記録する。

	Args:
		actor: ロール変更操作を行った管理者ユーザー。
		target_id: 変更対象ユーザーのID。
		new_role: 変更後のロール。
		db: SP呼び出しに使用する非同期DBセッション。
		request_id: 監査ログに紐づけるリクエストID。

	Returns:
		AdminUserDetailResponse: 変更後のユーザー詳細。

	Raises:
		NotFoundError: 対象ユーザーが存在しない場合。
		SelfModificationError: 自分自身のロールを変更しようとした場合。
		LastAdminRequiredError: 最後の有効な管理者を降格しようとした場合。
		app.core.exceptions.AppError: 上記以外のSQLSTATEエラーが発生した場合、
			`raise_database_error`により業務例外へ変換されて送出される。
	"""
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
					"actor_user_id": str(actor.id),
					"target_user_id": str(target_id),
					"request_id": request_id,
					"new_role": new_role,
					"result": app_error.code,
				},
			)
			raise
	updated = await _fetch_user_or_error(db, target_id)
	logger.info(
		"admin changed user role",
		extra={
			"actor_user_id": str(actor.id),
			"target_user_id": str(target_id),
			"request_id": request_id,
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
	request_id: str | None = None,
) -> AdminUserDetailResponse:
	"""管理者が対象ユーザーの有効/無効状態を変更する（03_patch_admin_user_status.md）。

	対象不存在・自己変更禁止・最後の管理者保護は`sp_admin_update_user_status`が
	advisory lockのもとで一体的に判定し、SQLSTATEとして返す（`_raise_for_sqlstate`参照）。
	SP呼び出しとコミットが本関数のトランザクション境界である。無効化（`new_is_active=False`）の
	場合のみ、DBコミット確定後にRedis上の全セッション削除・全リフレッシュトークン失効を行う
	（DB先行・Redis後続が正。#333）。Redis失効に失敗してもDBの無効化はロールバックせず
	フェイルセーフ側へ倒すが、運用者が検知できるようERROR監査ログを出力したうえで
	`ServiceUnavailableError`（503）を送出する。

	Args:
		actor: ステータス変更操作を行った管理者ユーザー。
		target_id: 変更対象ユーザーのID。
		new_is_active: 変更後の有効状態。
		db: SP呼び出しに使用する非同期DBセッション。
		request_id: 監査ログに紐づけるリクエストID。

	Returns:
		AdminUserDetailResponse: 変更後のユーザー詳細。

	Raises:
		NotFoundError: 対象ユーザーが存在しない場合。
		SelfModificationError: 自分自身を無効化しようとした場合。
		LastAdminRequiredError: 最後の有効な管理者を無効化しようとした場合。
		ServiceUnavailableError: 無効化後のRedisセッション削除・リフレッシュトークン
			失効に失敗した場合（DB上の無効化は成功済み）。
		app.core.exceptions.AppError: 上記以外のSQLSTATEエラーが発生した場合、
			`raise_database_error`により業務例外へ変換されて送出される。
	"""
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
				extra={
					"actor_user_id": str(actor.id),
					"target_user_id": str(target_id),
					"request_id": request_id,
					"operation": "delete_all_sessions",
				},
			)
			raise ServiceUnavailableError() from exc
		try:
			refresh_count = await redis_store.revoke_all_refresh_tokens(target_id)
		except RedisError as exc:
			logger.error(
				"admin status change: failed to revoke refresh tokens",
				extra={
					"actor_user_id": str(actor.id),
					"target_user_id": str(target_id),
					"request_id": request_id,
					"operation": "revoke_all_refresh_tokens",
				},
			)
			raise ServiceUnavailableError() from exc

	updated = await _fetch_user_or_error(db, target_id)
	logger.info(
		"admin changed user status",
		extra={
			"actor_user_id": str(actor.id),
			"target_user_id": str(target_id),
			"request_id": request_id,
			"old_is_active": old_is_active,
			"new_is_active": new_is_active,
			"session_revoked_count": session_count,
			"refresh_revoked_count": refresh_count,
		},
	)
	return _to_detail(updated)


async def force_logout(actor: CurrentUser, target_id: UUID, db: AsyncSession, request_id: str | None = None) -> None:
	"""管理者が対象ユーザーを強制ログアウトさせる（04_post_admin_user_force_logout.md）。

	対象ユーザーの存在確認後、Redis上の全セッション削除・全リフレッシュトークン
	失効を行う。DB更新は行わない（本操作はRedis状態のみを変更する）。
	JWTモードの場合、既発行のアクセストークンはリフレッシュトークン失効後も
	有効期限（`access_token_ttl_seconds`）まで利用可能である旨を監査ログへ記録する。

	Args:
		actor: 強制ログアウト操作を行った管理者ユーザー。
		target_id: 対象ユーザーのID。
		db: 対象ユーザー存在確認に使用する非同期DBセッション。
		request_id: 監査ログに紐づけるリクエストID。

	Returns:
		None

	Raises:
		NotFoundError: 対象ユーザーが存在しない場合。
		ServiceUnavailableError: Redisでのセッション削除・リフレッシュトークン失効に
			失敗した場合。
	"""
	await _fetch_user_or_error(db, target_id)
	try:
		session_count = await redis_store.delete_all_sessions(target_id)
		refresh_count = await redis_store.revoke_all_refresh_tokens(target_id)
	except RedisError as exc:
		raise ServiceUnavailableError() from exc
	settings = get_backend_settings()
	logger.info(
		"admin forced logout",
		extra={
			"actor_user_id": str(actor.id),
			"target_user_id": str(target_id),
			"request_id": request_id,
			"mode": settings.auth_mode,
			"access_token_revocation_delay_seconds": (
				settings.access_token_ttl_seconds if settings.auth_mode == "jwt" else 0
			),
			"session_revoked_count": session_count,
			"refresh_revoked_count": refresh_count,
		},
	)
