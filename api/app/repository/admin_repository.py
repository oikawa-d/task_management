"""管理者(admin)機能向けのデータアクセス層。

ユーザー・プロジェクト・ログイン履歴の一覧/件数取得、およびユーザーの権限・状態変更、
プロジェクトの有効/無効化を扱う。各関数はトランザクションのcommit/rollbackを行わない。
呼び出し元のservice層が同一セッションのcommitを担う。
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.login_history import LoginHistory
from app.models.project import Project
from app.models.user import User


@dataclass(frozen=True)
class AdminUserListItem:
	"""fn_admin_list_users の1行分（ユーザー本体＋ページング前の全体件数）。"""

	user: User
	total_count: int


@dataclass(frozen=True)
class AdminProjectListItem:
	"""fn_admin_list_projects の1行分（プロジェクト本体＋集計値＋全体件数）。"""

	project: Project
	total_count: int
	member_count: int = 0
	task_count_todo: int = 0
	task_count_in_progress: int = 0
	task_count_done: int = 0


@dataclass(frozen=True)
class AdminLoginHistoryListItem:
	"""fn_admin_list_login_history の1行分（履歴本体＋ユーザー＋全体件数）。"""

	history: LoginHistory
	total_count: int
	user: User | None = None


def _build_user(row: RowMapping) -> User:
	"""クエリ結果の1行からUserモデルを組み立てる。

	Args:
		row: `("user").*`形式で選択されたユーザー列を含む1行。

	Returns:
		組み立てたUserインスタンス。
	"""
	return User(
		id=row["id"],
		username=row["username"],
		email=row["email"],
		password_hash=row["password_hash"],
		last_name=row["last_name"],
		first_name=row["first_name"],
		last_name_kana=row["last_name_kana"],
		first_name_kana=row["first_name_kana"],
		birth_date=row["birth_date"],
		role=row["role"],
		is_active=row["is_active"],
		email_verified_at=row["email_verified_at"],
		created_at=row["created_at"],
		updated_at=row["updated_at"],
	)


def _build_project(row: RowMapping) -> Project:
	"""クエリ結果の1行からProjectモデル(オーナー情報を除く)を組み立てる。

	Args:
		row: `(project).*`形式で選択されたプロジェクト列を含む1行。

	Returns:
		組み立てたProjectインスタンス(`owner`は未設定)。
	"""
	return Project(
		id=row["id"],
		name=row["name"],
		description=row["description"],
		owner_id=row["owner_id"],
		is_active=row["is_active"],
		start_at=row["start_at"],
		end_at=row["end_at"],
		created_at=row["created_at"],
		updated_at=row["updated_at"],
	)


def _build_project_owner(row: RowMapping) -> User:
	"""クエリ結果の1行から、プロジェクトオーナーのUserモデルを組み立てる。

	Args:
		row: `owner_`プレフィックス付きのオーナー列を含む1行。

	Returns:
		組み立てたUserインスタンス(オーナー情報)。
	"""
	return User(
		id=row["owner_user_id"],
		username=row["owner_username"],
		email=row["owner_email"],
		password_hash=row["owner_password_hash"],
		last_name=row["owner_last_name"],
		first_name=row["owner_first_name"],
		last_name_kana=row["owner_last_name_kana"],
		first_name_kana=row["owner_first_name_kana"],
		birth_date=row["owner_birth_date"],
		role=row["owner_role"],
		is_active=row["owner_is_active"],
		email_verified_at=row["owner_email_verified_at"],
		created_at=row["owner_created_at"],
		updated_at=row["owner_updated_at"],
	)


def _build_admin_project(row: RowMapping) -> Project:
	"""クエリ結果の1行から、オーナー情報付きのProjectモデルを組み立てる。

	Args:
		row: プロジェクト列とオーナー列(`owner_`プレフィックス)を含む1行。

	Returns:
		`owner`を設定済みのProjectインスタンス。
	"""
	project = _build_project(row)
	project.owner = _build_project_owner(row)
	return project


def _build_login_history(row: RowMapping) -> LoginHistory:
	"""クエリ結果の1行からLoginHistoryモデルを組み立てる。

	Args:
		row: `(history).*`形式で選択されたログイン履歴列を含む1行。

	Returns:
		組み立てたLoginHistoryインスタンス。
	"""
	return LoginHistory(
		id=row["id"],
		user_id=row["user_id"],
		login_identifier=row["login_identifier"],
		login_method=row["login_method"],
		ip_address=row["ip_address"],
		user_agent=row["user_agent"],
		success=row["success"],
		failure_reason=row["failure_reason"],
		created_at=row["created_at"],
	)


async def list_users(
	db: AsyncSession,
	query: str | None,
	role: str | None,
	is_active: bool | None,
	limit: int,
	offset: int,
) -> list[AdminUserListItem]:
	"""管理画面向けにユーザー一覧を検索条件・ページング付きで取得する。

	DB関数 `fn_admin_list_users` を呼び出し、users テーブルを検索する。

	Args:
		db: 検索に使用する非同期DBセッション。
		query: ユーザー名・メール等の絞り込みキーワード。指定しない場合はNone。
		role: ロールでの絞り込み。指定しない場合はNone。
		is_active: 有効/無効での絞り込み。指定しない場合はNone。
		limit: 取得件数の上限。
		offset: 取得開始位置(ページング用)。

	Returns:
		ユーザーと全体件数を含むAdminUserListItemのリスト。該当行が無い場合は空リスト。
	"""
	result = await db.execute(
		text('SELECT ("user").*, total_count FROM fn_admin_list_users(:query, :role, :is_active, :limit, :offset)'),
		{"query": query, "role": role, "is_active": is_active, "limit": limit, "offset": offset},
	)
	return [AdminUserListItem(user=_build_user(row), total_count=row["total_count"]) for row in result.mappings()]


async def count_users(db: AsyncSession, query: str | None, role: str | None, is_active: bool | None) -> int:
	"""管理画面向けの検索条件に合致するユーザー件数を取得する。

	`fn_admin_list_users`の`total_count`が取得できない場合(該当0件)のフォールバック
	用件数取得として使用する。DB関数 `fn_count_admin_users` を呼び出す。

	Args:
		db: 検索に使用する非同期DBセッション。
		query: ユーザー名・メール等の絞り込みキーワード。指定しない場合はNone。
		role: ロールでの絞り込み。指定しない場合はNone。
		is_active: 有効/無効での絞り込み。指定しない場合はNone。

	Returns:
		該当するユーザーの件数(0件の場合は0)。
	"""
	result = await db.execute(
		text("SELECT fn_count_admin_users(:query, :role, :is_active) AS count"),
		{"query": query, "role": role, "is_active": is_active},
	)
	return int(result.scalar_one())


async def list_projects(
	db: AsyncSession, query: str | None, is_active: bool | None, limit: int, offset: int
) -> list[AdminProjectListItem]:
	"""管理画面向けにプロジェクト一覧を、オーナー・集計値付きで取得する。

	DB関数 `fn_admin_list_projects` を呼び出し、projects テーブルをオーナー情報・
	メンバー数・タスク集計とともに検索する。

	Args:
		db: 検索に使用する非同期DBセッション。
		query: プロジェクト名等の絞り込みキーワード。指定しない場合はNone。
		is_active: 有効/無効での絞り込み。指定しない場合はNone。
		limit: 取得件数の上限。
		offset: 取得開始位置(ページング用)。

	Returns:
		プロジェクト・集計値・全体件数を含むAdminProjectListItemのリスト。
		該当行が無い場合は空リスト。
	"""
	result = await db.execute(
		text(
			"SELECT (project).*, (owner).id AS owner_user_id, (owner).username AS owner_username, "
			"(owner).email AS owner_email, (owner).password_hash AS owner_password_hash, "
			"(owner).last_name AS owner_last_name, (owner).first_name AS owner_first_name, "
			"(owner).last_name_kana AS owner_last_name_kana, (owner).first_name_kana AS owner_first_name_kana, "
			"(owner).birth_date AS owner_birth_date, (owner).role AS owner_role, "
			"(owner).is_active AS owner_is_active, (owner).email_verified_at AS owner_email_verified_at, "
			"(owner).created_at AS owner_created_at, (owner).updated_at AS owner_updated_at, "
			"member_count, task_count_todo, task_count_in_progress, "
			"task_count_done, total_count "
			"FROM fn_admin_list_projects(:query, :is_active, :limit, :offset)"
		),
		{"query": query, "is_active": is_active, "limit": limit, "offset": offset},
	)
	return [
		AdminProjectListItem(
			project=_build_admin_project(row),
			total_count=row["total_count"],
			member_count=row["member_count"],
			task_count_todo=row["task_count_todo"],
			task_count_in_progress=row["task_count_in_progress"],
			task_count_done=row["task_count_done"],
		)
		for row in result.mappings()
	]


async def count_projects(db: AsyncSession, query: str | None, is_active: bool | None) -> int:
	"""管理画面向けの検索条件に合致するプロジェクト件数を取得する。

	`fn_admin_list_projects`の`total_count`が取得できない場合(該当0件)のフォールバック
	用件数取得として使用する。DB関数 `fn_count_admin_projects` を呼び出す。

	Args:
		db: 検索に使用する非同期DBセッション。
		query: プロジェクト名等の絞り込みキーワード。指定しない場合はNone。
		is_active: 有効/無効での絞り込み。指定しない場合はNone。

	Returns:
		該当するプロジェクトの件数(0件の場合は0)。
	"""
	result = await db.execute(
		text("SELECT fn_count_admin_projects(:query, :is_active) AS count"),
		{"query": query, "is_active": is_active},
	)
	return int(result.scalar_one())


async def list_login_history(
	db: AsyncSession,
	user_id: uuid.UUID | None,
	query: str | None,
	login_method: str | None,
	success: bool | None,
	created_from: datetime | None,
	created_to: datetime | None,
	limit: int,
	offset: int,
) -> list[AdminLoginHistoryListItem]:
	"""管理画面向けにログイン履歴一覧を検索条件・ページング付きで取得する。

	DB関数 `fn_admin_list_login_history` を呼び出し、login_history テーブルを紐づく
	ユーザー情報とともに検索する。

	Args:
		db: 検索に使用する非同期DBセッション。
		user_id: ユーザーIDでの絞り込み。指定しない場合はNone。
		query: ログイン識別子等の絞り込みキーワード。指定しない場合はNone。
		login_method: ログイン方式での絞り込み。指定しない場合はNone。
		success: 成功/失敗での絞り込み。指定しない場合はNone。
		created_from: 記録日時の下限。指定しない場合はNone。
		created_to: 記録日時の上限。指定しない場合はNone。
		limit: 取得件数の上限。
		offset: 取得開始位置(ページング用)。

	Returns:
		履歴・全体件数・紐づくユーザー(退会等で存在しない場合はNone)を含む
		AdminLoginHistoryListItemのリスト。該当行が無い場合は空リスト。
	"""
	result = await db.execute(
		text(
			'SELECT (history).*, ("user").id AS user_info_id, ("user").username AS user_info_username, '
			'("user").last_name AS user_info_last_name, ("user").first_name AS user_info_first_name, '
			"total_count FROM fn_admin_list_login_history("
			":user_id, :query, :login_method, :success, :created_from, :created_to, :limit, :offset)"
		),
		{
			"user_id": user_id,
			"query": query,
			"login_method": login_method,
			"success": success,
			"created_from": created_from,
			"created_to": created_to,
			"limit": limit,
			"offset": offset,
		},
	)
	return [
		AdminLoginHistoryListItem(
			history=_build_login_history(row),
			total_count=row["total_count"],
			user=(
				User(
					id=row["user_info_id"],
					username=row["user_info_username"],
					last_name=row["user_info_last_name"],
					first_name=row["user_info_first_name"],
				)
				if row["user_info_id"] is not None
				else None
			),
		)
		for row in result.mappings()
	]


async def count_login_history(
	db: AsyncSession,
	user_id: uuid.UUID | None,
	query: str | None,
	login_method: str | None,
	success: bool | None,
	created_from: datetime | None,
	created_to: datetime | None,
) -> int:
	"""管理画面向けの検索条件に合致するログイン履歴件数を取得する。

	`fn_admin_list_login_history`の`total_count`が取得できない場合(該当0件)の
	フォールバック用件数取得として使用する。DB関数 `fn_count_admin_login_history` を
	呼び出す。

	Args:
		db: 検索に使用する非同期DBセッション。
		user_id: ユーザーIDでの絞り込み。指定しない場合はNone。
		query: ログイン識別子等の絞り込みキーワード。指定しない場合はNone。
		login_method: ログイン方式での絞り込み。指定しない場合はNone。
		success: 成功/失敗での絞り込み。指定しない場合はNone。
		created_from: 記録日時の下限。指定しない場合はNone。
		created_to: 記録日時の上限。指定しない場合はNone。

	Returns:
		該当するログイン履歴の件数(0件の場合は0)。
	"""
	result = await db.execute(
		text(
			"SELECT fn_count_admin_login_history("
			":user_id, :query, :login_method, :success, :created_from, :created_to) AS count"
		),
		{
			"user_id": user_id,
			"query": query,
			"login_method": login_method,
			"success": success,
			"created_from": created_from,
			"created_to": created_to,
		},
	)
	return int(result.scalar_one())


async def update_user_role(db: AsyncSession, actor_id: uuid.UUID, target_id: uuid.UUID, new_role: str) -> str:
	"""ユーザーのロールを変更する。

	ストアドプロシージャ `sp_admin_update_user_role` を1回呼び出し、users テーブルの
	該当行の`role`を更新する副作用を持つ。対象不存在チェック(SQLSTATE `P0010`)・
	自己変更禁止(`P0007`)・最後のadmin保護(`P0008`)はSP内部で一体実行される。
	本関数自体はcommitを行わず、呼び出し元のservice層が同一セッションでcommitする。

	Args:
		db: 更新に使用する非同期DBセッション。
		actor_id: 変更操作を行う管理者のユーザーID。
		target_id: ロール変更対象のユーザーID。
		new_role: 変更後のロール。

	Returns:
		監査ログ用に、変更前のroleの値。

	Raises:
		sqlalchemy.exc.DBAPIError: `target_id`が存在しない場合(`P0010`)、
			`actor_id`と`target_id`が同一の場合(`P0007`)、または最後の有効な
			admin(唯一の有効admin)を降格しようとした場合(`P0008`)、元の例外を
			再送出する(業務エラーへの変換は呼び出し元のservice層が行う)。
	"""
	result = await db.execute(
		text("CALL sp_admin_update_user_role(:actor_id, :target_id, :new_role, NULL)"),
		{"actor_id": actor_id, "target_id": target_id, "new_role": new_role},
	)
	return str(result.mappings().one()["p_old_role"])


async def update_user_status(db: AsyncSession, actor_id: uuid.UUID, target_id: uuid.UUID, is_active: bool) -> bool:
	"""ユーザーの有効/無効状態を変更する。

	ストアドプロシージャ `sp_admin_update_user_status` を1回呼び出し、users テーブルの
	該当行の`is_active`を更新する副作用を持つ。本関数自体はcommitを行わず、呼び出し元の
	service層が同一セッションでcommitする。

	Args:
		db: 更新に使用する非同期DBセッション。
		actor_id: 変更操作を行う管理者のユーザーID。
		target_id: 状態変更対象のユーザーID。
		is_active: 変更後の有効状態。

	Returns:
		監査ログ用に、変更前のis_activeの値。

	Raises:
		sqlalchemy.exc.DBAPIError: 対象不存在・自己変更禁止・最後のadmin保護など
			SP内部の業務チェックに違反した場合、元の例外を再送出する(業務エラーへの
			変換は呼び出し元のservice層が行う)。
	"""
	result = await db.execute(
		text("CALL sp_admin_update_user_status(:actor_id, :target_id, :is_active, NULL)"),
		{"actor_id": actor_id, "target_id": target_id, "is_active": is_active},
	)
	return bool(result.mappings().one()["p_old_is_active"])


async def deactivate_project(db: AsyncSession, project_id: uuid.UUID, is_active: bool) -> None:
	"""管理者権限でプロジェクトの有効/無効状態を変更する。

	ストアドプロシージャ `sp_admin_deactivate_project` を呼び出し、projects テーブルの
	`is_active` を更新する副作用を持つ。本関数自体はcommitを行わず、呼び出し元の
	service層が同一セッションでcommitする。

	Args:
		db: 更新に使用する非同期DBセッション。
		project_id: 対象のプロジェクトID。
		is_active: 変更後の有効状態。

	Returns:
		None。
	"""
	await db.execute(
		text("CALL sp_admin_deactivate_project(:project_id, :is_active)"),
		{"project_id": project_id, "is_active": is_active},
	)
