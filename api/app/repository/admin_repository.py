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
	"""fn_admin_list_projects の1行分（プロジェクト本体＋ページング前の全体件数）。"""

	project: Project
	total_count: int


@dataclass(frozen=True)
class AdminLoginHistoryListItem:
	"""fn_admin_list_login_history の1行分（ログイン履歴本体＋ページング前の全体件数）。"""

	history: LoginHistory
	total_count: int


def _build_user(row: RowMapping) -> User:
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


def _build_login_history(row: RowMapping) -> LoginHistory:
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
	result = await db.execute(
		text('SELECT ("user").*, total_count FROM fn_admin_list_users(:query, :role, :is_active, :limit, :offset)'),
		{"query": query, "role": role, "is_active": is_active, "limit": limit, "offset": offset},
	)
	return [AdminUserListItem(user=_build_user(row), total_count=row["total_count"]) for row in result.mappings()]


async def count_users(db: AsyncSession, query: str | None, role: str | None, is_active: bool | None) -> int:
	"""fn_admin_list_usersの`total_count`が取得できない場合（該当0件）のフォールバック用件数取得。"""
	result = await db.execute(
		text("SELECT fn_count_admin_users(:query, :role, :is_active) AS count"),
		{"query": query, "role": role, "is_active": is_active},
	)
	return int(result.scalar_one())


async def list_projects(
	db: AsyncSession, query: str | None, is_active: bool | None, limit: int, offset: int
) -> list[AdminProjectListItem]:
	result = await db.execute(
		text("SELECT (project).*, total_count FROM fn_admin_list_projects(:query, :is_active, :limit, :offset)"),
		{"query": query, "is_active": is_active, "limit": limit, "offset": offset},
	)
	return [
		AdminProjectListItem(project=_build_project(row), total_count=row["total_count"]) for row in result.mappings()
	]


async def count_projects(db: AsyncSession, query: str | None, is_active: bool | None) -> int:
	"""fn_admin_list_projectsの`total_count`が取得できない場合（該当0件）のフォールバック用件数取得。"""
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
	result = await db.execute(
		text(
			"SELECT (history).*, total_count FROM fn_admin_list_login_history("
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
		AdminLoginHistoryListItem(history=_build_login_history(row), total_count=row["total_count"])
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
	"""fn_admin_list_login_historyの`total_count`が取得できない場合（該当0件）のフォールバック用件数取得。"""
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
	"""sp_admin_update_user_roleを1回呼ぶ。対象不存在（P0010）・自己変更禁止（P0007）・

	最後のadmin保護（P0008）はSP内部で一体実行される。戻り値は更新前のroleで、
	監査ログ用にservice層が別途取得することを避けるためOUTパラメータで受け取る。
	"""
	result = await db.execute(
		text("CALL sp_admin_update_user_role(:actor_id, :target_id, :new_role, NULL)"),
		{"actor_id": actor_id, "target_id": target_id, "new_role": new_role},
	)
	return str(result.mappings().one()["p_old_role"])


async def update_user_status(db: AsyncSession, actor_id: uuid.UUID, target_id: uuid.UUID, is_active: bool) -> bool:
	"""sp_admin_update_user_statusを1回呼ぶ。戻り値は更新前のis_active（監査ログ用）。"""
	result = await db.execute(
		text("CALL sp_admin_update_user_status(:actor_id, :target_id, :is_active, NULL)"),
		{"actor_id": actor_id, "target_id": target_id, "is_active": is_active},
	)
	return bool(result.mappings().one()["p_old_is_active"])


async def deactivate_project(db: AsyncSession, project_id: uuid.UUID, is_active: bool) -> None:
	await db.execute(
		text("CALL sp_admin_deactivate_project(:project_id, :is_active)"),
		{"project_id": project_id, "is_active": is_active},
	)
