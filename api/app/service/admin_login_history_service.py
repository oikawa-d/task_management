"""管理者による全ユーザーのログイン履歴検索の業務ロジック。"""

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import raise_database_error
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
	"""ユーザーの表示名を組み立てる。

	姓名が設定されていれば「姓 名」を、いずれも未設定であればログインIDである
	`username`を表示名として用いる。

	Args:
		user: 表示名を求める対象のユーザー。

	Returns:
		str: 表示に用いるユーザー名。
	"""
	return " ".join(part for part in (user.last_name, user.first_name) if part) or user.username


def _to_item(history: LoginHistory, user: User | None) -> AdminLoginHistoryItem:
	"""ログイン履歴レコードをAPIレスポンス用の要素へ変換する。

	紐づくユーザーが取得できない場合（退会・削除等）は`user`を`None`として返す。

	Args:
		history: 変換対象のログイン履歴レコード。
		user: 履歴に紐づくユーザー。存在しない場合は`None`。

	Returns:
		AdminLoginHistoryItem: レスポンス表示用のログイン履歴要素。
	"""
	return AdminLoginHistoryItem(
		id=history.id,
		user=AdminLoginHistoryUser(id=user.id, username=user.username, display_name=_display_name(user))
		if user is not None
		else None,
		login_identifier=history.login_identifier,
		login_method=history.login_method,
		ip_address=str(history.ip_address) if history.ip_address is not None else None,
		user_agent=history.user_agent,
		success=history.success,
		failure_reason=history.failure_reason,
		created_at=history.created_at,
	)


async def search(query: AdminLoginHistoryQuery, db: AsyncSession) -> AdminLoginHistoryListResponse:
	"""条件に合致するログイン履歴を管理者向けに検索し、ページング結果を返す。

	`fn_admin_list_login_history`が返す`total_count`はウィンドウ関数によるものであり、
	該当ページの行が0件の場合は集計値も取得できないため、その場合に限り
	`fn_count_admin_login_history`へフォールバックして総件数を取得する（#347レビュー対応）。

	Args:
		query: ユーザーID・検索語・ログイン方式・成否・期間・ページ指定を含む検索条件。
		db: 検索に使用する非同期DBセッション。

	Returns:
		AdminLoginHistoryListResponse: 該当ページの履歴一覧とページングメタ情報。

	Raises:
		app.core.exceptions.AppError: DB問い合わせでSQLSTATEエラーが発生した場合、
			`raise_database_error`によりSQLSTATEに対応する業務例外へ変換されて送出される。
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
		raise_database_error(exc)

	items = [_to_item(row.history, row.user) for row in rows]
	total_pages = (total + query.per_page - 1) // query.per_page if total else 0
	return AdminLoginHistoryListResponse(
		items=items,
		meta=AdminUserListMeta(page=query.page, per_page=query.per_page, total=total, total_pages=total_pages),
	)
