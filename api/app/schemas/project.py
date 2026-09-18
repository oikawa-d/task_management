"""プロジェクト管理エンドポイント（`projects_router`）の入出力DTOを定義するモジュール。"""

from datetime import datetime
from typing import Self, cast
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.core.config import BackendSettings
from app.core.constants import DESCRIPTION_MAX_LENGTH

_PAGINATION_DEFAULT_PER_PAGE = cast(int, BackendSettings.model_fields["pagination_default_per_page"].default)
_PAGINATION_MAX_PER_PAGE = cast(int, BackendSettings.model_fields["pagination_max_per_page"].default)


class ProjectListQuery(BaseModel):
	"""`GET /projects` のクエリパラメータDTO。ページネーションと非活性プロジェクトの表示可否を指定する。"""

	page: int = Field(default=1, ge=1)
	per_page: int = Field(default=_PAGINATION_DEFAULT_PER_PAGE, ge=1, le=_PAGINATION_MAX_PER_PAGE)
	include_inactive: bool = False


class ProjectCreateRequest(BaseModel):
	"""`POST /projects` のリクエストDTO。"""

	name: str = Field(min_length=1, max_length=100)
	description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
	start_at: datetime | None = None
	end_at: datetime | None = None

	@model_validator(mode="after")
	def validate_period(self) -> Self:
		"""`end_at` が指定されている場合、`start_at` 以降であることを検証する。

		Returns:
			検証を通過した自インスタンス。

		Raises:
			ValueError: `end_at` が `start_at` より前の日時の場合。
		"""
		if self.start_at is not None and self.end_at is not None and self.end_at < self.start_at:
			raise ValueError("end_at must be greater than or equal to start_at")
		return self


class ProjectUpdateRequest(BaseModel):
	"""`PATCH /projects/{project_id}` のリクエストDTO。指定されたフィールドのみ部分更新する。"""

	name: str | None = Field(default=None, min_length=1, max_length=100)
	description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
	start_at: datetime | None = None
	end_at: datetime | None = None
	is_active: bool | None = None

	@model_validator(mode="before")
	@classmethod
	def validate_non_nullable_fields(cls, value: object) -> object:
		"""非NULL項目（`name`・`is_active`）に `null` が明示的に指定された場合を拒否する。

		Args:
			value: パース前の入力データ。

		Returns:
			検証を通過した入力データ（値は変更しない）。

		Raises:
			ValueError: `name`または`is_active`に`null`が指定された場合。
		"""
		if isinstance(value, dict):
			for field_name in ("name", "is_active"):
				if field_name in value and value[field_name] is None:
					raise ValueError(f"{field_name} must not be null")
		return value

	@model_validator(mode="after")
	def validate_at_least_one_field(self) -> Self:
		"""部分更新リクエストとして、最低1項目は指定されていることを検証する。

		Returns:
			検証を通過した自インスタンス。

		Raises:
			ValueError: どのフィールドも指定されていない場合。
		"""
		if not self.model_fields_set:
			raise ValueError("at least one field must be specified")
		return self


class ProjectPathParams(BaseModel):
	"""プロジェクトIDをパスパラメータに持つエンドポイント共通のパスパラメータDTO。"""

	project_id: UUID


class ProjectOwner(BaseModel):
	"""プロジェクトオーナーの表示用情報を表すDTO。"""

	id: UUID
	username: str
	display_name: str


class ProjectTaskCounts(BaseModel):
	"""プロジェクト配下タスクのステータス別件数を表すDTO。"""

	todo: int = Field(ge=0)
	in_progress: int = Field(ge=0)
	done: int = Field(ge=0)


class ProjectMember(BaseModel):
	"""プロジェクト詳細レスポンスに含めるメンバー1名分の表示用情報を表すDTO。"""

	user_id: UUID
	username: str
	display_name: str
	is_owner: bool
	joined_at: datetime


class ProjectSummary(BaseModel):
	"""プロジェクト一覧・詳細で共通する基本情報を表すDTO。"""

	id: UUID
	name: str
	description: str | None
	owner: ProjectOwner
	member_count: int = Field(ge=0)
	task_counts: ProjectTaskCounts
	is_owner: bool
	is_active: bool
	start_at: datetime | None
	end_at: datetime | None
	created_at: datetime


class ProjectSummaryResponse(ProjectSummary):
	"""`GET /projects` の一覧アイテムのレスポンスDTO。"""

	updated_at: datetime | None = None


class ProjectDetail(ProjectSummary):
	"""プロジェクト詳細の内部表現DTO。メンバー一覧を追加で保持する。"""

	updated_at: datetime
	members: list[ProjectMember]


class ProjectDetailResponse(ProjectDetail):
	"""`GET /projects/{project_id}` のレスポンスDTO。`ProjectDetail`と同一構造。"""


class ProjectListMeta(BaseModel):
	"""プロジェクト一覧のページネーション情報を表すDTO。"""

	page: int = Field(ge=1)
	per_page: int = Field(ge=1, le=_PAGINATION_MAX_PER_PAGE)
	total: int = Field(ge=0)
	total_pages: int = Field(ge=0)


class ProjectListResponse(BaseModel):
	"""`GET /projects` のレスポンスDTO。"""

	items: list[ProjectSummaryResponse]
	meta: ProjectListMeta
