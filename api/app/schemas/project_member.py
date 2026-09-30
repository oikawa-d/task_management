"""プロジェクトメンバー管理エンドポイント（`projects_router`のメンバー関連操作）の入出力DTOを定義するモジュール。"""

from datetime import datetime
from typing import Literal

from pydantic import UUID4, BaseModel, ConfigDict, Field

MemberRole = Literal["member", "admin"]


class MemberListQueryParams(BaseModel):
	"""`GET /api/projects/{project_id}/members` が受け取る`project_id`の形状を検証するDTO。

	実際のルーティングではFastAPIのパス引数として`project_id: UUID`を直接受け取るため、
	このクラス自体はルーターに直接バインドされておらず、値のバリデーション仕様を表す。
	"""

	project_id: UUID4


class MemberDeletePathParams(MemberListQueryParams):
	"""`DELETE /api/projects/{project_id}/members/{user_id}` が受け取るパスパラメータの形状を検証するDTO。

	`MemberListQueryParams`と同様、ルーターへ直接バインドされる型ではなく、
	削除対象ユーザーIDを含めたバリデーション仕様を表す。
	"""

	user_id: UUID4


class AddMemberRequest(BaseModel):
	"""`POST /api/projects/{project_id}/members` のリクエストDTO。招待対象ユーザーIDを指定する。"""

	model_config = ConfigDict(extra="forbid")

	user_id: UUID4


class MemberSummary(BaseModel):
	"""プロジェクトメンバー1名分の表示用情報を表すDTO。"""

	user_id: UUID4
	username: str
	display_name: str | None
	role: MemberRole
	is_owner: bool
	is_active: bool
	joined_at: datetime


class MemberResponse(MemberSummary):
	"""`POST /api/projects/{project_id}/members` のレスポンスDTO。`MemberSummary`と同一構造。"""


class MemberListMeta(BaseModel):
	"""メンバー一覧のメタ情報DTO。総件数を保持する。"""

	total: int = Field(ge=0)


class MemberListResponse(BaseModel):
	"""`GET /api/projects/{project_id}/members` のレスポンスDTO。"""

	items: list[MemberSummary]
	meta: MemberListMeta


class CandidateSearchQuery(BaseModel):
	"""`GET /api/projects/{project_id}/member-candidates` のクエリパラメータDTO。

	検索文字列の長さを1〜50文字に制限する。
	"""

	model_config = ConfigDict(extra="forbid")

	q: str = Field(min_length=1, max_length=50)


class CandidateSummary(BaseModel):
	"""招待候補ユーザー1名分の表示用情報を表すDTO。"""

	user_id: UUID4
	username: str
	display_name: str | None


class CandidateListResponse(BaseModel):
	"""`GET /api/projects/{project_id}/member-candidates` のレスポンスDTO。"""

	items: list[CandidateSummary]
