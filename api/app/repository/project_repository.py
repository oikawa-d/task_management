"""プロジェクト(projects テーブル)へのデータアクセス層。

各関数はトランザクションのcommit/rollbackを行わない。呼び出し元のservice層が
同一セッションのcommitを担う。
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.user import User
from app.repository import project_member_repository


@dataclass(frozen=True)
class ProjectListItem:
	"""fn_list_projects の1行分（プロジェクト本体＋集計値）。"""

	project: Project
	member_count: int
	task_count_todo: int
	task_count_in_progress: int
	task_count_done: int
	total_count: int


async def create(
	db: AsyncSession,
	owner_id: uuid.UUID,
	name: str,
	description: str | None,
	start_at: datetime | None,
	end_at: datetime | None,
) -> uuid.UUID:
	"""プロジェクトを新規作成する。

	ストアドプロシージャ `sp_create_project` を呼び出し、projects テーブルに1行挿入する
	副作用を持つ。本関数自体はcommitを行わず、呼び出し元のservice層が同一セッションで
	commitする。

	Args:
		db: 更新に使用する非同期DBセッション。
		owner_id: プロジェクトオーナーとなるユーザーID。
		name: プロジェクト名。
		description: プロジェクトの説明。指定しない場合はNone。
		start_at: 開始日時。指定しない場合はNone。
		end_at: 終了日時。指定しない場合はNone。

	Returns:
		作成されたプロジェクトのID。

	Raises:
		sqlalchemy.exc.DBAPIError: `end_at`が`start_at`より前の場合(SQLSTATE `P0009`)、
			元の例外を再送出する(通常はAPIスキーマの`ProjectCreateRequest`側で事前に
			検証されるため、本関数まで到達するのはSP側の不変条件チェックとして働く)。
	"""
	result = await db.execute(
		text("CALL sp_create_project(:owner_id, :name, :description, :start_at, :end_at, NULL)"),
		{
			"owner_id": owner_id,
			"name": name,
			"description": description,
			"start_at": start_at,
			"end_at": end_at,
		},
	)
	project_id: uuid.UUID = result.mappings().one()["p_project_id"]
	return project_id


async def get_by_id(db: AsyncSession, project_id: uuid.UUID) -> Project | None:
	"""プロジェクトIDを指定して1件取得する。

	DB関数 `fn_get_project` を呼び出し、projects テーブルを検索する。

	Args:
		db: 検索に使用する非同期DBセッション。
		project_id: 検索対象のプロジェクトID。

	Returns:
		該当するProject。該当行が存在しない場合はNone。
	"""
	result = await db.execute(
		select(Project)
		.from_statement(text("SELECT * FROM fn_get_project(:project_id)"))
		.params(project_id=project_id)
		.execution_options(populate_existing=True)
	)
	return result.scalars().one_or_none()


async def is_member(db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID) -> bool:
	"""指定ユーザーが指定プロジェクトのメンバーかどうかを判定する。

	`project_member_repository.exists`(DB関数`fn_is_project_member`)の薄いラッパー。
	admin bypassの判定もDB関数側の戻り値に含まれる。

	Args:
		db: 検索に使用する非同期DBセッション。
		project_id: 判定対象のプロジェクトID。
		user_id: 判定対象のユーザーID。

	Returns:
		メンバーであればTrue、そうでなければFalse。
	"""
	return await project_member_repository.exists(db, project_id, user_id)


async def list_for_user(
	db: AsyncSession, user_id: uuid.UUID, include_inactive: bool, limit: int, offset: int
) -> list[ProjectListItem]:
	"""指定ユーザーが参照可能なプロジェクト一覧を、集計値付きで取得する。

	DB関数 `fn_list_projects` を呼び出し、projects テーブルをメンバー数・タスク集計と
	ともに検索したうえで、各プロジェクトのオーナー情報(usersテーブル)を追加で取得する。

	Args:
		db: 検索に使用する非同期DBセッション。
		user_id: 検索対象のユーザーID。
		include_inactive: Trueの場合、非アクティブなプロジェクトも含める。
		limit: 取得件数の上限。
		offset: 取得開始位置(ページング用)。

	Returns:
		プロジェクトと集計値を含むProjectListItemのリスト(各要素は`project.owner`を
		設定済み)。該当行が無い場合は空リスト。
	"""
	result = await db.execute(
		text(
			"SELECT (project).*, member_count, task_count_todo, task_count_in_progress, "
			"task_count_done, total_count "
			"FROM fn_list_projects(:user_id, :include_inactive, :limit, :offset)"
		),
		{"user_id": user_id, "include_inactive": include_inactive, "limit": limit, "offset": offset},
	)
	rows = result.mappings().all()
	items = [
		ProjectListItem(
			project=Project(
				id=row["id"],
				name=row["name"],
				description=row["description"],
				owner_id=row["owner_id"],
				is_active=row["is_active"],
				start_at=row["start_at"],
				end_at=row["end_at"],
				created_at=row["created_at"],
				updated_at=row["updated_at"],
			),
			member_count=row["member_count"],
			task_count_todo=row["task_count_todo"],
			task_count_in_progress=row["task_count_in_progress"],
			task_count_done=row["task_count_done"],
			total_count=row["total_count"],
		)
		for row in rows
	]
	if not items:
		return items
	owner_ids = {item.project.owner_id for item in items}
	owner_result = await db.execute(select(User).where(User.id.in_(owner_ids)))
	owners = {owner.id: owner for owner in owner_result.scalars().all()}
	for item in items:
		item.project.owner = owners[item.project.owner_id]
	return items


async def update(
	db: AsyncSession,
	project_id: uuid.UUID,
	name: str,
	description: str | None,
	start_at: datetime | None,
	end_at: datetime | None,
) -> None:
	"""プロジェクトの情報を更新する。

	ストアドプロシージャ `sp_update_project` を呼び出し、projects テーブルの該当行を
	更新する副作用を持つ。本関数自体はcommitを行わず、呼び出し元のservice層が
	同一セッションでcommitする。

	Args:
		db: 更新に使用する非同期DBセッション。
		project_id: 更新対象のプロジェクトID。
		name: 更新後のプロジェクト名。
		description: 更新後の説明。指定しない場合はNone。
		start_at: 更新後の開始日時。指定しない場合はNone。
		end_at: 更新後の終了日時。指定しない場合はNone。

	Returns:
		None。

	Raises:
		sqlalchemy.exc.DBAPIError: `end_at`が`start_at`より前の場合(SQLSTATE `P0009`)、
			元の例外を再送出する(通常はAPIスキーマの`ProjectUpdateRequest`側で事前に
			検証されるため、本関数まで到達するのはSP側の不変条件チェックとして働く)。
	"""
	await db.execute(
		text("CALL sp_update_project(:project_id, :name, :description, :start_at, :end_at)"),
		{
			"project_id": project_id,
			"name": name,
			"description": description,
			"start_at": start_at,
			"end_at": end_at,
		},
	)


async def set_active(db: AsyncSession, project_id: uuid.UUID, is_active: bool) -> None:
	"""プロジェクトの有効/無効状態を切り替える。

	ストアドプロシージャ `sp_deactivate_project` を呼び出し、projects テーブルの
	`is_active` を更新する副作用を持つ。本関数自体はcommitを行わず、呼び出し元の
	service層が同一セッションでcommitする。

	Args:
		db: 更新に使用する非同期DBセッション。
		project_id: 更新対象のプロジェクトID。
		is_active: 更新後の有効状態。

	Returns:
		None。
	"""
	await db.execute(
		text("CALL sp_deactivate_project(:project_id, :is_active)"),
		{"project_id": project_id, "is_active": is_active},
	)
