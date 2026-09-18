"""プロジェクトメンバー(project_members テーブル)へのデータアクセス層。

各関数はトランザクションのcommit/rollbackを行わない。呼び出し元のservice層が
同一セッションのcommitを担う。
"""

import uuid

from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AlreadyMemberError
from app.models.project_member import ProjectMember
from app.models.user import User


async def create(db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID, invited_by: uuid.UUID | None) -> None:
	"""プロジェクトへユーザーをメンバーとして追加する。

	ストアドプロシージャ `sp_add_project_member` を呼び出し、project_members テーブルに
	1行挿入する副作用を持つ。本関数自体はcommitを行わず、呼び出し元のservice層が
	同一セッションでcommitする。

	Args:
		db: 更新に使用する非同期DBセッション。
		project_id: 追加先のプロジェクトID。
		user_id: 追加するユーザーID。
		invited_by: 招待を行ったユーザーID。招待経由でない場合はNone。

	Returns:
		None。

	Raises:
		AlreadyMemberError: 対象ユーザーが既にプロジェクトのメンバーである場合
			(DBが返すSQLSTATE `P0003`を変換して送出する)。
		sqlalchemy.exc.DBAPIError: 上記以外のDB操作エラーが発生した場合、そのまま送出する。
	"""
	try:
		await db.execute(
			text("CALL sp_add_project_member(:project_id, :user_id, :invited_by)"),
			{"project_id": project_id, "user_id": user_id, "invited_by": invited_by},
		)
	except DBAPIError as exc:
		if getattr(exc.orig, "sqlstate", None) == "P0003":
			raise AlreadyMemberError() from exc
		raise


async def exists(db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID) -> bool:
	"""指定ユーザーが指定プロジェクトのメンバーかどうかを判定する。

	DB関数 `fn_is_project_member` を呼び出す。

	Args:
		db: 検索に使用する非同期DBセッション。
		project_id: 判定対象のプロジェクトID。
		user_id: 判定対象のユーザーID。

	Returns:
		メンバーであればTrue、そうでなければFalse。
	"""
	result = await db.execute(
		text("SELECT fn_is_project_member(:project_id, :user_id) AS is_member"),
		{"project_id": project_id, "user_id": user_id},
	)
	return bool(result.scalar_one())


async def list_by_project(db: AsyncSession, project_id: uuid.UUID) -> list[ProjectMember]:
	"""指定プロジェクトのメンバー一覧を、紐づくユーザー情報付きで取得する。

	DB関数 `fn_list_project_members` を呼び出し、project_members テーブルを検索する。
	`selectinload`によりユーザー情報を追加でロードする。

	Args:
		db: 検索に使用する非同期DBセッション。
		project_id: 検索対象のプロジェクトID。

	Returns:
		該当するProjectMemberのリスト(各要素は`user`をロード済み)。
		該当行が無い場合は空リスト。
	"""
	result = await db.execute(
		select(ProjectMember)
		.from_statement(text("SELECT * FROM fn_list_project_members(:project_id)"))
		.params(project_id=project_id)
		.options(selectinload(ProjectMember.user))
		.execution_options(populate_existing=True)
	)
	return list(result.scalars().all())


async def search_candidates(
	db: AsyncSession, project_id: uuid.UUID, query: str | None, limit: int, offset: int
) -> list[User]:
	"""プロジェクトへ招待可能なメンバー候補ユーザーを検索する。

	DB関数 `fn_search_member_candidates` を呼び出し、既にメンバーのユーザーを除いた
	候補をusersテーブルから検索する。

	Args:
		db: 検索に使用する非同期DBセッション。
		project_id: 招待先のプロジェクトID。
		query: 氏名・メールアドレス等の絞り込みキーワード。指定しない場合はNone。
		limit: 取得件数の上限。
		offset: 取得開始位置(ページング用)。

	Returns:
		候補となるUserのリスト。該当が無い場合は空リスト。
	"""
	result = await db.execute(
		select(User)
		.from_statement(text("SELECT * FROM fn_search_member_candidates(:project_id, :query, :limit, :offset)"))
		.params(project_id=project_id, query=query, limit=limit, offset=offset)
		.execution_options(populate_existing=True)
	)
	return list(result.scalars().all())


async def delete(db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID) -> None:
	"""プロジェクトからメンバーを削除する。

	ストアドプロシージャ `sp_remove_project_member` を呼び出し、project_members
	テーブルから該当行を削除する副作用を持つ。本関数自体はcommitを行わず、
	呼び出し元のservice層が同一セッションでcommitする。

	Args:
		db: 更新に使用する非同期DBセッション。
		project_id: 削除対象のプロジェクトID。
		user_id: 削除対象のユーザーID。

	Returns:
		None。
	"""
	await db.execute(
		text("CALL sp_remove_project_member(:project_id, :user_id)"),
		{"project_id": project_id, "user_id": user_id},
	)
