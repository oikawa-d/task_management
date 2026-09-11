"""管理者による全ユーザーのログイン履歴検索の業務ロジック。

参照設計書:
- docs/detailed_design/api/admin/07_get_admin_login_history.md

`fn_admin_list_login_history`はuser_idの表示情報をJOINしないため、当該ページの
user_idを重複排除したうえで`user_repository.get_by_id`をユーザーIDごとに呼び出す。
repositoryにIN句によるバッチ取得FNが存在しないため、設計書§11「N+1対策」が想定する
単一バッチクエリではなく、重複排除済みユーザー数に比例したクエリになる
（要検討: バッチ取得用FNの追加はDB層の変更を伴うため本issueの範囲外とした）。
"""

from uuid import UUID

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_backend_settings
from app.core.exceptions import ServiceUnavailableError
from app.models.login_history import LoginHistory
from app.models.user import User
from app.repository import admin_repository, user_repository
from app.schemas.admin import (
	AdminLoginHistoryItem,
	AdminLoginHistoryListResponse,
	AdminLoginHistoryQuery,
	AdminLoginHistoryUser,
	AdminUserListMeta,
)


def _display_name(user: User) -> str:
	return " ".join(part for part in (user.last_name, user.first_name) if part) or user.username


def _to_item(history: LoginHistory, users_by_id: dict[UUID, User]) -> AdminLoginHistoryItem:
	user = users_by_id.get(history.user_id) if history.user_id is not None else None
	return AdminLoginHistoryItem(
		id=history.id,
		user=AdminLoginHistoryUser(id=user.id, username=user.username, display_name=_display_name(user))
		if user is not None
		else None,
		login_identifier=history.login_identifier,
		login_method=history.login_method,
		ip_address=history.ip_address,
		user_agent=history.user_agent,
		success=history.success,
		failure_reason=history.failure_reason,
		created_at=history.created_at,
	)


async def search(query: AdminLoginHistoryQuery, db: AsyncSession) -> AdminLoginHistoryListResponse:
	settings = get_backend_settings()
	offset = (query.page - 1) * query.per_page
	try:
		matched = await admin_repository.list_login_history(
			db,
			query.user_id,
			query.q,
			query.login_method,
			query.success,
			query.created_from,
			query.created_to,
			settings.admin_list_count_query_limit,
			0,
		)
	except DBAPIError as exc:
		raise ServiceUnavailableError() from exc
	total = len(matched)
	page_rows = matched[offset : offset + query.per_page]

	user_ids = sorted({row.user_id for row in page_rows if row.user_id is not None}, key=str)
	users_by_id: dict[UUID, User] = {}
	try:
		for user_id in user_ids:
			user = await user_repository.get_by_id(db, user_id)
			if user is not None:
				users_by_id[user_id] = user
	except DBAPIError as exc:
		raise ServiceUnavailableError() from exc

	items = [_to_item(row, users_by_id) for row in page_rows]
	total_pages = (total + query.per_page - 1) // query.per_page if total else 0
	return AdminLoginHistoryListResponse(
		items=items,
		meta=AdminUserListMeta(page=query.page, per_page=query.per_page, total=total, total_pages=total_pages),
	)
