"""APIアクセス履歴(api_history テーブル)へのデータアクセス層。

各関数はトランザクションのcommit/rollbackを行わない。呼び出し元のservice層(または
ミドルウェア)が同一セッションのcommitを担う。
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import bindparam, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_history import ApiHistory

# 11_table_api_history.md §4により、単純な追記専用の履歴INSERT・request_id検索は
# 業務ロジックを伴わないため直接SQLでよい（00_policy.md §2.1の例外ではなく、
# 各テーブル詳細設計書自身が明記する個別の設計判断）。保持期間パージのみSP経由とする。


@dataclass(frozen=True)
class ApiHistoryCreateInput:
	"""`create`関数へ渡すAPI履歴1件分の入力値をまとめるデータクラス。"""

	request_id: uuid.UUID
	method: str
	path: str
	status: str
	status_code: int
	error_code: str | None
	error_detail: str | None
	body: dict[str, object] | None
	user_id: uuid.UUID | None
	ip_address: str | None
	user_agent: str | None
	duration_ms: int
	created_at: datetime | None = None


async def create(db: AsyncSession, data: ApiHistoryCreateInput) -> uuid.UUID:
	"""APIアクセス履歴を1件追加する。

	api_history テーブルへ直接INSERTする副作用を持つ(業務ロジックを伴わない追記専用の
	ため生SQLを使用する設計判断による)。本関数自体はcommitを行わず、呼び出し元が
	同一セッションでcommitする。

	Args:
		db: 更新に使用する非同期DBセッション。
		data: 挿入する履歴1件分の値。`created_at`がNoneの場合はDBのデフォルト値が使われる。

	Returns:
		挿入された行のid(UUID)。

	Raises:
		sqlalchemy.exc.DBAPIError: INSERTに失敗した場合(一意制約違反等)、そのまま送出する。
	"""
	params: dict[str, object] = {
		"request_id": data.request_id,
		"method": data.method,
		"path": data.path,
		"status": data.status,
		"status_code": data.status_code,
		"error_code": data.error_code,
		"error_detail": data.error_detail,
		"body": data.body,
		"user_id": data.user_id,
		"ip_address": data.ip_address,
		"user_agent": data.user_agent,
		"duration_ms": data.duration_ms,
	}
	columns = list(params.keys())
	if data.created_at is not None:
		params["created_at"] = data.created_at
		columns.append("created_at")
	column_list = ", ".join(columns)
	value_list = ", ".join(f":{c}" for c in columns)
	# 生SQLのtext()はデフォルトでは列型を推論しないため、bodyはJSONB型を明示してbindしないと
	# asyncpgドライバがPython dictをそのままエンコードできずエラーになる。
	statement = text(f"INSERT INTO api_history ({column_list}) VALUES ({value_list}) RETURNING id").bindparams(
		bindparam("body", type_=JSONB)
	)
	result = await db.execute(statement, params)
	history_id: uuid.UUID = result.scalar_one()
	return history_id


async def list_by_request_id(db: AsyncSession, request_id: uuid.UUID) -> ApiHistory | None:
	"""リクエストIDに紐づくAPI履歴を1件取得する。

	api_history テーブルを `request_id` で検索する。

	Args:
		db: 検索に使用する非同期DBセッション。
		request_id: 検索対象のリクエストID。

	Returns:
		該当するApiHistory。該当行が存在しない場合はNone。
	"""
	result = await db.execute(select(ApiHistory).where(ApiHistory.request_id == request_id))
	return result.scalars().one_or_none()


async def purge_expired(db: AsyncSession, retention_days: int) -> None:
	"""保持期間を過ぎた古いAPI履歴を削除する。

	ストアドプロシージャ `sp_purge_api_history` を呼び出し、api_history テーブルから
	`retention_days` を超えて経過した行を削除する副作用を持つ。本関数自体はcommitを
	行わず、呼び出し元のservice層が同一セッションでcommitする。

	Args:
		db: 更新に使用する非同期DBセッション。
		retention_days: この日数より古い履歴を削除対象とする保持日数。

	Returns:
		None。

	Raises:
		sqlalchemy.exc.DBAPIError: `retention_days`が0以下の場合、SP内部の
			`RAISE EXCEPTION 'p_retention_days must be positive'`が発生し、
			元の例外を再送出する。
	"""
	await db.execute(text("CALL sp_purge_api_history(:retention_days)"), {"retention_days": retention_days})
