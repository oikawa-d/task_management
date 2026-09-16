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
	result = await db.execute(select(ApiHistory).where(ApiHistory.request_id == request_id))
	return result.scalars().one_or_none()


async def purge_expired(db: AsyncSession, retention_days: int) -> None:
	await db.execute(text("CALL sp_purge_api_history(:retention_days)"), {"retention_days": retention_days})
