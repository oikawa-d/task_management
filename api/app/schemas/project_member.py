"""プロジェクトメンバー管理エンドポイント（`projects_router`のメンバー関連操作）の入出力DTOを定義するモジュール。"""

from datetime import datetime
from typing import Literal

from pydantic import UUID4, BaseModel, ConfigDict, Field

MemberRole = Literal["member", "admin"]


class MemberListQueryParams(BaseModel):
	"""`GET /projects/{project_id}/members` のパスパラメータDTO。"""

	project_id: UUID4


class MemberDeletePathParams(MemberListQueryParams):
	"""`DELETE /projects/{project_id}/members/{user_id}` のパスパラメータDTO。削除対象ユーザーIDを追加で保持する。"""

	user_id: UUID4


class AddMemberRequest(BaseModel):
	"""`POST /projects/{project_id}/members` のリクエストDTO。招待対象ユーザーIDを指定する。"""

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
	"""メンバー追加・単体取得エンドポイントのレスポンスDTO。`MemberSummary`と同一構造。"""


class MemberListMeta(BaseModel):
	"""メンバー一覧のメタ情報DTO。総件数を保持する。"""

	total: int = Field(ge=0)


class MemberListResponse(BaseModel):
	"""`GET /projects/{project_id}/members` のレスポンスDTO。"""

	items: list[MemberSummary]
	meta: MemberListMeta


class CandidateSearchQuery(BaseModel):
	"""メンバー招待候補検索エンドポイントのクエリパラメータDTO。検索文字列の長さを1〜50文字に制限する。"""

	model_config = ConfigDict(extra="forbid")

	q: str = Field(min_length=1, max_length=50)


class CandidateSummary(BaseModel):
	"""招待候補ユーザー1名分の表示用情報を表すDTO。"""

	user_id: UUID4
	username: str
	display_name: str | None


class CandidateListResponse(BaseModel):
	"""招待候補検索エンドポイントのレスポンスDTO。"""

	items: list[CandidateSummary]
