"""プロジェクトメンバーの一覧・招待・招待候補検索・除名を扱うサービス。"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_backend_settings
from app.core.exceptions import AlreadyMemberError, NotFoundError, OwnerCannotBeRemovedError, raise_database_error
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.repository import project_member_repository, user_repository
from app.schemas.project_member import (
	CandidateListResponse,
	CandidateSummary,
	MemberListMeta,
	MemberListResponse,
	MemberResponse,
	MemberSummary,
)


def _display_name(member: ProjectMember) -> str | None:
	"""メンバーの表示名を組み立てる。

	Args:
		member: 表示名を求める対象のプロジェクトメンバー。

	Returns:
		str | None: 「姓 名」形式の表示名。姓名がいずれも未設定の場合は`None`。
	"""
	parts = (member.user.last_name, member.user.first_name)
	return " ".join(part for part in parts if part) or None


def _member_summary(member: ProjectMember, owner_id: UUID) -> MemberSummary:
	"""プロジェクトメンバーのレコードをレスポンス用の要約へ変換する。

	Args:
		member: 変換対象のプロジェクトメンバー。
		owner_id: 所属プロジェクトのオーナーID。オーナー判定に使用する。

	Returns:
		MemberSummary: レスポンス表示用のメンバー要約（オーナー判定を含む）。
	"""
	return MemberSummary(
		user_id=member.user_id,
		username=member.user.username,
		display_name=_display_name(member),
		role=member.user.role,
		is_owner=member.user_id == owner_id,
		is_active=member.user.is_active,
		joined_at=member.joined_at,
	)


async def list_members(project: Project, db: AsyncSession) -> MemberListResponse:
	"""プロジェクトの全メンバーを一覧取得する。

	権限チェックはルーター側の所属確認（プロジェクトアクセス権）に委ねる。

	Args:
		project: 対象プロジェクト。
		db: メンバー一覧取得に使用する非同期DBセッション。

	Returns:
		MemberListResponse: メンバー一覧と総件数。
	"""
	members = await project_member_repository.list_by_project(db, project.id)
	return MemberListResponse(
		items=[_member_summary(member, project.owner_id) for member in members],
		meta=MemberListMeta(total=len(members)),
	)


async def add_member(project: Project, user_id: UUID, invited_by: UUID, db: AsyncSession) -> MemberResponse:
	"""ユーザーをプロジェクトメンバーとして招待する。

	招待対象ユーザーの存在確認・既存メンバーか否かの確認はDB更新前に行う。
	メンバー追加とその後の再取得・コミットが本関数のトランザクション境界であり、
	いずれかで失敗した場合はロールバックする。

	Args:
		project: 招待先プロジェクト。
		user_id: 招待対象ユーザーのID。
		invited_by: 招待操作を行ったユーザーのID。
		db: メンバー追加・取得に使用する非同期DBセッション。

	Returns:
		MemberResponse: 追加されたメンバーの情報。

	Raises:
		NotFoundError: 招待対象ユーザーが存在しない場合、または追加後の
			再取得に失敗した場合（想定外の不整合）。
		AlreadyMemberError: 既にプロジェクトへ参加済みのユーザーを招待した場合。
		app.core.exceptions.AppError: DB更新でSQLSTATEエラーが発生した場合、
			`raise_database_error`により業務例外へ変換されて送出される。
	"""
	user = await user_repository.get_by_id(db, user_id)
	if user is None:
		raise NotFoundError()
	if await project_member_repository.exists(db, project.id, user_id):
		raise AlreadyMemberError()
	try:
		await project_member_repository.create(db, project.id, user_id, invited_by)
		members = await project_member_repository.list_by_project(db, project.id)
		created = next((member for member in members if member.user_id == user_id), None)
		if created is None:
			raise NotFoundError("追加したメンバーを取得できません")
		await db.commit()
		return MemberResponse(**_member_summary(created, project.owner_id).model_dump())
	except AlreadyMemberError:
		await db.rollback()
		raise
	except NotFoundError:
		await db.rollback()
		raise
	except DBAPIError as exc:
		await db.rollback()
		raise_database_error(exc)


async def search_candidates(project: Project, query: str, db: AsyncSession) -> CandidateListResponse:
	"""プロジェクトへ招待可能なユーザー候補を検索する。

	既にメンバーであるユーザーはリポジトリ側の検索条件で除外される想定。
	件数は設定のデフォルトページサイズで打ち切る。

	Args:
		project: 招待先プロジェクト。
		query: ユーザー名等の検索語。
		db: 候補検索に使用する非同期DBセッション。

	Returns:
		CandidateListResponse: 招待候補ユーザーの一覧。
	"""
	limit = get_backend_settings().pagination_default_per_page
	users = await project_member_repository.search_candidates(db, project.id, query, limit, 0)
	return CandidateListResponse(
		items=[
			CandidateSummary(
				user_id=user.id,
				username=user.username,
				display_name=" ".join(part for part in (user.last_name, user.first_name) if part) or None,
			)
			for user in users
		]
	)


async def remove_member(project: Project, user_id: UUID, db: AsyncSession) -> None:
	"""プロジェクトからメンバーを除名する。

	オーナーは除名対象にできない。除名とコミットが本関数のトランザクション境界である。

	Args:
		project: 対象プロジェクト。
		user_id: 除名対象ユーザーのID。
		db: メンバー削除に使用する非同期DBセッション。

	Returns:
		None

	Raises:
		OwnerCannotBeRemovedError: 除名対象がプロジェクトオーナー自身の場合。
		NotFoundError: 除名対象ユーザーがメンバーとして存在しない場合。
		app.core.exceptions.AppError: DB更新でSQLSTATEエラーが発生した場合、
			`raise_database_error`により業務例外へ変換されて送出される。
	"""
	if user_id == project.owner_id:
		raise OwnerCannotBeRemovedError()
	if not await project_member_repository.exists(db, project.id, user_id):
		raise NotFoundError()
	try:
		await project_member_repository.delete(db, project.id, user_id)
		await db.commit()
	except DBAPIError as exc:
		await db.rollback()
		raise_database_error(exc)
