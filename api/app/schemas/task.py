"""タスク管理エンドポイント（`tasks_router`、カンバンボード・カレンダー含む）の入出力DTOを定義するモジュール。"""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import UUID4, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.config import get_backend_settings
from app.core.constants import DESCRIPTION_MAX_LENGTH

TaskStatus = Literal["todo", "in_progress", "done"]
TaskSort = Literal["created_at", "due_at"]
TaskOrder = Literal["asc", "desc"]
CalendarScope = Literal["me", "project"]


def _default_per_page() -> int:
	"""タスク一覧のデフォルトページサイズを設定値から取得する。"""
	return get_backend_settings().pagination_default_per_page


class TaskAssignee(BaseModel):
	"""タスク担当者の表示用情報を表すDTO。ORMの`User`から`from_attributes`で変換する。"""

	model_config = ConfigDict(from_attributes=True)

	id: UUID4
	username: str
	display_name: str


class TaskCreator(BaseModel):
	"""タスク作成者の表示用情報を表すDTO。ORMの`User`から`from_attributes`で変換する。"""

	model_config = ConfigDict(from_attributes=True)

	id: UUID4
	username: str
	display_name: str | None = None


class TaskCreateRequest(BaseModel):
	"""`POST /api/projects/{project_id}/tasks` のリクエストDTO。"""

	model_config = ConfigDict(extra="forbid")

	title: str = Field(min_length=1, max_length=150)
	description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
	status: TaskStatus = "todo"
	assignee_id: UUID4 | None = None
	due_at: datetime | None = None


class TaskCreateFlatRequest(TaskCreateRequest):
	"""`POST /api/tasks`（プロジェクト非依存の作成）のリクエストDTO。プロジェクト未指定時は担当者割当を禁止する。"""

	project_id: UUID4 | None = None

	@model_validator(mode="after")
	def reject_assignee_without_project(self) -> "TaskCreateFlatRequest":
		"""プロジェクト未所属のタスクに担当者が指定されていないことを検証する。

		Returns:
			検証を通過した自インスタンス。

		Raises:
			ValueError: `project_id`が未指定にもかかわらず`assignee_id`が指定されている場合。
		"""
		if self.project_id is None and self.assignee_id is not None:
			raise ValueError("assignee_id cannot be set for an unassigned task")
		return self


class TaskUpdateRequest(BaseModel):
	"""`PATCH /api/tasks/{task_id}` のリクエストDTO。`version`による楽観ロックと部分更新を行う。"""

	model_config = ConfigDict(extra="forbid")

	version: int
	title: str | None = Field(default=None, min_length=1, max_length=150)
	description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
	status: TaskStatus | None = None
	assignee_id: UUID4 | None = None
	position: int | None = Field(default=None, ge=0)
	due_at: datetime | None = None
	is_active: bool | None = None

	@model_validator(mode="after")
	def reject_null_for_non_nullable_fields(self) -> "TaskUpdateRequest":
		"""非NULL項目（`title`・`status`・`position`・`is_active`）に`null`が明示指定された場合を拒否する。

		Returns:
			検証を通過した自インスタンス。

		Raises:
			ValueError: 対象フィールドが指定されており、かつ値が`None`の場合。
		"""
		for field_name in ("title", "status", "position", "is_active"):
			if field_name in self.model_fields_set and getattr(self, field_name) is None:
				raise ValueError(f"{field_name} cannot be null")
		return self


class TaskSummary(BaseModel):
	"""カンバンボード表示用のタスク要約DTO。ORMの`Task`から`from_attributes`で変換する。"""

	model_config = ConfigDict(from_attributes=True)

	id: UUID4
	title: str
	description: str | None
	assignee: TaskAssignee | None
	due_at: datetime | None
	position: int
	version: int
	is_active: bool
	comment_count: int
	created_at: datetime
	updated_at: datetime


class TaskResponse(BaseModel):
	"""タスク1件の基本情報を表すレスポンスDTO。ORMの`Task`から`from_attributes`で変換する。"""

	model_config = ConfigDict(from_attributes=True)

	id: UUID4
	project_id: UUID4 | None
	project_is_active: bool | None
	title: str
	description: str | None
	status: TaskStatus
	assignee: TaskAssignee | None
	created_by: TaskCreator
	position: int
	version: int
	is_active: bool
	due_at: datetime | None
	created_at: datetime
	updated_at: datetime


class TaskDetailResponse(TaskResponse):
	"""タスク詳細取得エンドポイントのレスポンスDTO。コメント件数を追加で保持する。"""

	comment_count: int


class TaskListItem(TaskDetailResponse):
	"""`GET /api/tasks` 一覧の1件分のレスポンスDTO。`TaskDetailResponse`と同一構造。"""


class CalendarTaskItem(TaskListItem):
	"""カレンダー表示用エンドポイントのレスポンスDTO。表示対象日（`due_date`）を追加で保持する。"""

	due_date: date


class BoardColumns(BaseModel):
	"""カンバンボードのステータス別タスク列を表すDTO。"""

	todo: list[TaskSummary] = Field(default_factory=list)
	in_progress: list[TaskSummary] = Field(default_factory=list)
	done: list[TaskSummary] = Field(default_factory=list)


class BoardResponse(BaseModel):
	"""`GET /api/projects/{project_id}/tasks` のレスポンスDTO。プロジェクトのカンバンボード表示用データを返す。"""

	model_config = ConfigDict(from_attributes=True)

	project_id: UUID4
	project_is_active: bool
	columns: BoardColumns


class TaskListQuery(BaseModel):
	"""`GET /api/tasks` のクエリパラメータDTO。ページネーション・絞り込み・並び替えを指定する。"""

	page: int = Field(default=1, ge=1)
	per_page: int = Field(default_factory=_default_per_page, ge=1)
	# FastAPIはDepends()でクエリパラメータモデルを解決する際、この型注釈だけから
	# 生成した別フィールドで先に素の値を検証してから本体のバリデータへ渡すため、
	# UUID4 | Literal["unassigned"] | Noneのままだと"null"がその時点で拒否され
	# normalize_unassigned_filterに届かない。strを経由させて素通しし、本バリデータで
	# "null"→"unassigned"への正規化とUUID変換を行う（router側で正しい型へcastする）。
	project_id: UUID4 | str | None = None
	status: TaskStatus | None = None
	include_inactive: bool = False
	sort: TaskSort = "created_at"
	order: TaskOrder = "desc"

	@field_validator("project_id", mode="before")
	@classmethod
	def normalize_unassigned_filter(cls, value: object) -> object:
		"""`project_id`フィルタの`"null"`（未所属指定）を正規化し、それ以外の文字列をUUIDへ変換する。

		Args:
			value: パース前の入力値。

		Returns:
			`"null"`は`"unassigned"`へ正規化した値、UUID文字列は`UUID`へ変換した値、
			それ以外はそのままの値。

		Raises:
			ValueError: `"unassigned"`が直接指定された場合、またはUUIDとして解釈できない文字列の場合。
		"""
		if value == "null":
			return "unassigned"
		if isinstance(value, str) and value == "unassigned":
			raise ValueError('project_id must be a UUID or "null"')
		if isinstance(value, str):
			try:
				return UUID(value)
			except ValueError as exc:
				raise ValueError('project_id must be a UUID or "null"') from exc
		return value

	@field_validator("per_page")
	@classmethod
	def validate_per_page_limit(cls, value: int) -> int:
		"""`per_page`が設定上限（`pagination_max_per_page`）を超えていないかを検証する。

		Args:
			value: 検証対象のページサイズ。

		Returns:
			検証を通過した値。

		Raises:
			ValueError: 設定上限を超えている場合。
		"""
		if value > get_backend_settings().pagination_max_per_page:
			raise ValueError("per_page exceeds the configured maximum")
		return value


class TaskListMeta(BaseModel):
	"""タスク一覧のページネーション情報を表すDTO。"""

	page: int = Field(ge=1)
	per_page: int = Field(ge=1)
	total: int = Field(ge=0)
	total_pages: int = Field(ge=0)


class TaskListResponse(BaseModel):
	"""`GET /api/tasks` のレスポンスDTO。"""

	items: list[TaskListItem]
	meta: TaskListMeta


class CalendarTaskQuery(BaseModel):
	"""`GET /api/tasks/calendar` のクエリパラメータの検証仕様を表すDTO。

	表示期間とスコープ（自分/プロジェクト）を指定する。ルーター側では個々のクエリパラメータを
	`Query(...)`で受け取ってから本クラスを構築するため、FastAPIのクエリ解決に直接バインドされる型ではない。
	"""

	from_date: date = Field(alias="from")
	to_date: date = Field(alias="to")
	scope: CalendarScope
	project_id: UUID4 | None = None

	@model_validator(mode="after")
	def validate_range_and_scope(self) -> "CalendarTaskQuery":
		"""表示期間が62日以内であること、および`scope`と`project_id`の組み合わせが整合していることを検証する。

		Returns:
			検証を通過した自インスタンス。

		Raises:
			ValueError: 期間が62日を超える場合、`scope="project"`で`project_id`が未指定の場合、
				または`scope="me"`で`project_id`が指定されている場合。
		"""
		if self.to_date < self.from_date or (self.to_date - self.from_date).days > 62:
			raise ValueError("calendar range must be within 62 days")
		if self.scope == "project" and self.project_id is None:
			raise ValueError("project_id is required for project scope")
		if self.scope == "me" and self.project_id is not None:
			raise ValueError("project_id is not allowed for me scope")
		return self
