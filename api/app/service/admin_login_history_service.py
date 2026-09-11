"""管理者による全ユーザーのログイン履歴検索の業務ロジック。"""

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ServiceUnavailableError
from app.models.login_history import LoginHistory
from app.models.user import User
from app.repository import admin_repository
from app.schemas.admin import (
	AdminLoginHistoryItem,
	AdminLoginHistoryListResponse,
	AdminLoginHistoryQuery,
	AdminLoginHistoryUser,
	AdminUserListMeta,
)


def _display_name(user: User) -> str:
	return " ".join(part for part in (user.last_name, user.first_name) if part) or user.username


def _to_item(history: LoginHistory, user: User | None) -> AdminLoginHistoryItem:
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
	"""fn_admin_list_login_historyのtotal_countはウィンドウ関数のため該当ページが0件の

	場合のみfn_count_admin_login_historyへフォールバックする（#347レビュー対応）。
	"""
	offset = (query.page - 1) * query.per_page
	try:
		rows = await admin_repository.list_login_history(
			db,
			query.user_id,
			query.q,
			query.login_method,
			query.success,
			query.created_from,
			query.created_to,
			query.per_page,
			offset,
		)
		total = (
			rows[0].total_count
			if rows
			else await admin_repository.count_login_history(
				db, query.user_id, query.q, query.login_method, query.success, query.created_from, query.created_to
			)
		)
	except DBAPIError as exc:
		raise ServiceUnavailableError() from exc

	items = [_to_item(row.history, row.user) for row in rows]
	total_pages = (total + query.per_page - 1) // query.per_page if total else 0
	return AdminLoginHistoryListResponse(
		items=items,
		meta=AdminUserListMeta(page=query.page, per_page=query.per_page, total=total, total_pages=total_pages),
	)
