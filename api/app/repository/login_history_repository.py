"""ログイン履歴(login_history テーブル)へのデータアクセス層。

各関数はトランザクションのcommit/rollbackを行わない。呼び出し元のservice層が
同一セッションのcommitを担う。DB接続系の`OperationalError`は`raise_database_error`で
変換し、接続障害であれば`ServiceUnavailableError`として、それ以外は元の例外として送出する。
"""

import uuid

from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import raise_database_error
from app.models.login_history import LoginHistory


async def create(
	db: AsyncSession,
	user_id: uuid.UUID | None,
	login_identifier: str,
	login_method: str,
	ip_address: str | None,
	user_agent: str | None,
	success: bool,
	failure_reason: str | None,
) -> None:
	"""ログイン試行結果を1件記録する。

	ストアドプロシージャ `sp_record_login_history` を呼び出し、login_history テーブルに
	1行挿入する副作用を持つ。本関数自体はcommitを行わず、呼び出し元のservice層が
	同一セッションでcommitする。

	Args:
		db: 更新に使用する非同期DBセッション。
		user_id: ログイン試行を行ったユーザーID。ユーザーが特定できない場合はNone。
		login_identifier: ログイン試行に使われた識別子(メールアドレス等)。
		login_method: ログイン方式(パスワード/OAuth等)。
		ip_address: 接続元IPアドレス。取得できない場合はNone。
		user_agent: 接続元User-Agent。取得できない場合はNone。
		success: ログイン試行が成功したかどうか。
		failure_reason: 失敗理由。成功時または理由不明の場合はNone。

	Returns:
		None。

	Raises:
		ServiceUnavailableError: DB接続障害が発生した場合。
		OperationalError: 接続障害以外のDB操作エラーが発生した場合、元の例外を再送出する。
	"""
	try:
		await db.execute(
			text(
				"CALL sp_record_login_history("
				":user_id, :login_identifier, :login_method, :ip_address, :user_agent, :success, :failure_reason)"
			),
			{
				"user_id": user_id,
				"login_identifier": login_identifier,
				"login_method": login_method,
				"ip_address": ip_address,
				"user_agent": user_agent,
				"success": success,
				"failure_reason": failure_reason,
			},
		)
	except OperationalError as exc:
		raise_database_error(exc)


async def list_by_user_id(db: AsyncSession, user_id: uuid.UUID, limit: int = 50, offset: int = 0) -> list[LoginHistory]:
	"""指定ユーザーのログイン履歴を新しい順に取得する。

	DB関数 `fn_list_user_login_history` を呼び出し、login_history テーブルを検索する。

	Args:
		db: 検索に使用する非同期DBセッション。
		user_id: 検索対象のユーザーID。
		limit: 取得件数の上限。
		offset: 取得開始位置(ページング用)。

	Returns:
		該当するLoginHistoryのリスト。該当行が無い場合は空リスト。

	Raises:
		ServiceUnavailableError: DB接続障害が発生した場合。
		OperationalError: 接続障害以外のDB操作エラーが発生した場合、元の例外を再送出する。
	"""
	try:
		result = await db.execute(
			select(LoginHistory)
			.from_statement(text("SELECT * FROM fn_list_user_login_history(:user_id, :limit, :offset)"))
			.params(user_id=user_id, limit=limit, offset=offset)
		)
		return list(result.scalars().all())
	except OperationalError as exc:
		raise_database_error(exc)


async def purge_expired(db: AsyncSession, retention_days: int) -> None:
	"""保持期間を過ぎた古いログイン履歴を削除する。

	ストアドプロシージャ `sp_purge_login_history` を呼び出し、login_history テーブルから
	`retention_days` を超えて経過した行を削除する副作用を持つ。本関数自体はcommitを
	行わず、呼び出し元のservice層が同一セッションでcommitする。

	Args:
		db: 更新に使用する非同期DBセッション。
		retention_days: この日数より古い履歴を削除対象とする保持日数。

	Returns:
		None。

	Raises:
		ServiceUnavailableError: DB接続障害が発生した場合。
		OperationalError: 接続障害以外のDB操作エラーが発生した場合、元の例外を再送出する。
	"""
	try:
		await db.execute(text("CALL sp_purge_login_history(:retention_days)"), {"retention_days": retention_days})
	except OperationalError as exc:
		raise_database_error(exc)
