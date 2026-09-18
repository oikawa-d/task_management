"""管理者向けエンドポイント（`admin_router`：ユーザー・プロジェクト・ログイン履歴の一覧管理）の入出力DTOを定義するモジュール。"""

from datetime import datetime
from typing import Literal, cast

from pydantic import UUID4, ConfigDict, Field, field_validator, model_validator

from app.core.config import BackendSettings, get_backend_settings
from app.schemas.base import StrictSchema
from app.schemas.user import LoginMethod

AdminRole = Literal["member", "admin"]
_DEFAULT_PER_PAGE = cast(int, BackendSettings.model_fields["pagination_default_per_page"].default)
_MAX_PER_PAGE = cast(int, BackendSettings.model_fields["pagination_max_per_page"].default)


def _validate_search_query(value: str | None) -> str | None:
	"""検索キーワードが設定上限文字数（`admin_search_query_max_length`）以内かを検証する。

	Args:
		value: 検証対象の検索キーワード。未指定（`None`）の場合は検証をスキップする。

	Returns:
		検証を通過した値。

	Raises:
		ValueError: 上限文字数を超えている場合。
	"""
	if value is not None and len(value) > get_backend_settings().admin_search_query_max_length:
		raise ValueError("search query exceeds the configured maximum length")
	return value


class AdminPaginationQuery(StrictSchema):
	"""管理者向け一覧系クエリで共通するページネーションパラメータの基底DTO。"""

	page: int = Field(default=1, ge=1)
	per_page: int = Field(default=_DEFAULT_PER_PAGE, ge=1, le=_MAX_PER_PAGE)


class AdminUserListQuery(AdminPaginationQuery):
	"""`GET /api/admin/users` のクエリパラメータDTO。検索・ロール・有効状態での絞り込みを行う。"""

	q: str | None = None
	role: AdminRole | None = None
	is_active: bool | None = None

	@field_validator("q")
	@classmethod
	def validate_query_length(cls, value: str | None) -> str | None:
		"""検索キーワードの長さを検証するフィールドバリデータ。`_validate_search_query`に委譲する。"""
		return _validate_search_query(value)


class AdminUserRoleUpdateRequest(StrictSchema):
	"""`PATCH /api/admin/users/{user_id}/role` のリクエストDTO。"""

	role: AdminRole


class AdminUserStatusUpdateRequest(StrictSchema):
	"""`PATCH /api/admin/users/{user_id}/status` のリクエストDTO。アカウントの有効/無効を切り替える。"""

	is_active: bool


class AdminUserItem(StrictSchema):
	"""管理者向けユーザー一覧の1件分を表すDTO。ORMの`User`から`from_attributes`で変換する。"""

	model_config = ConfigDict(from_attributes=True)

	id: UUID4
	username: str
	email: str
	display_name: str
	role: AdminRole
	is_active: bool
	email_verified_at: datetime | None
	created_at: datetime


class AdminUserListMeta(StrictSchema):
	"""管理者向けユーザー一覧のページネーション情報を表すDTO。"""

	page: int = Field(ge=1)
	per_page: int = Field(ge=1, le=_MAX_PER_PAGE)
	total: int = Field(ge=0)
	total_pages: int = Field(ge=0)


class AdminUserListResponse(StrictSchema):
	"""`GET /api/admin/users` のレスポンスDTO。"""

	items: list[AdminUserItem]
	meta: AdminUserListMeta


class AdminUserDetailResponse(AdminUserItem):
	"""`GET /api/admin/users/{user_id}` のレスポンスDTO。更新日時を追加で保持する。"""

	updated_at: datetime


class AdminProjectListQuery(AdminPaginationQuery):
	"""`GET /api/admin/projects` のクエリパラメータDTO。"""

	q: str | None = None

	@field_validator("q")
	@classmethod
	def validate_query_length(cls, value: str | None) -> str | None:
		"""検索キーワードの長さを検証するフィールドバリデータ。`_validate_search_query`に委譲する。"""
		return _validate_search_query(value)


class AdminProjectListMeta(AdminUserListMeta):
	"""管理者向けプロジェクト一覧のページネーション情報を表すDTO。`AdminUserListMeta`と同一構造。"""


class AdminProjectOwner(StrictSchema):
	"""管理者向けプロジェクト一覧に含めるオーナー情報を表すDTO。"""

	id: UUID4
	username: str
	display_name: str


class AdminProjectTaskCounts(StrictSchema):
	"""管理者向けプロジェクト一覧に含めるステータス別タスク件数を表すDTO。"""

	todo: int = Field(ge=0)
	in_progress: int = Field(ge=0)
	done: int = Field(ge=0)


class AdminProjectSummary(StrictSchema):
	"""管理者向けプロジェクト一覧の1件分を表すDTO。"""

	id: UUID4
	name: str
	description: str | None
	owner: AdminProjectOwner
	member_count: int = Field(ge=0)
	task_counts: AdminProjectTaskCounts
	is_active: bool
	start_at: datetime | None
	end_at: datetime | None
	created_at: datetime


class AdminProjectListResponse(StrictSchema):
	"""`GET /api/admin/projects` のレスポンスDTO。"""

	items: list[AdminProjectSummary]
	meta: AdminProjectListMeta


class AdminLoginHistoryQuery(AdminPaginationQuery):
	"""`GET /api/admin/login-history` のクエリパラメータDTO。対象ユーザー・方式・成否・期間での絞り込みを行う。"""

	model_config = ConfigDict(extra="forbid", populate_by_name=True)

	user_id: UUID4 | None = None
	q: str | None = None
	login_method: LoginMethod | None = None
	success: bool | None = None
	created_from: datetime | None = Field(default=None, alias="from")
	created_to: datetime | None = Field(default=None, alias="to")

	@field_validator("q")
	@classmethod
	def validate_query_length(cls, value: str | None) -> str | None:
		"""検索キーワードの長さを検証するフィールドバリデータ。`_validate_search_query`に委譲する。"""
		return _validate_search_query(value)

	@model_validator(mode="after")
	def validate_period(self) -> "AdminLoginHistoryQuery":
		"""絞り込み期間の開始（`from`）が終了（`to`）より前であることを検証する。

		Returns:
			検証を通過した自インスタンス。

		Raises:
			ValueError: `from`が`to`以降の日時の場合。
		"""
		if self.created_from is not None and self.created_to is not None and self.created_from >= self.created_to:
			raise ValueError("from must be earlier than to")
		return self


class AdminLoginHistoryUser(StrictSchema):
	"""管理者向けログイン履歴に含める対象ユーザー情報を表すDTO。"""

	id: UUID4
	username: str
	display_name: str


class AdminLoginHistoryItem(StrictSchema):
	"""管理者向けログイン履歴一覧の1件分を表すDTO。ORMの`LoginHistory`から`from_attributes`で変換する。"""

	model_config = ConfigDict(from_attributes=True)

	id: UUID4
	user: AdminLoginHistoryUser | None
	login_identifier: str
	login_method: LoginMethod
	ip_address: str | None
	user_agent: str | None
	success: bool
	failure_reason: str | None
	created_at: datetime


class AdminLoginHistoryListResponse(StrictSchema):
	"""`GET /api/admin/login-history` のレスポンスDTO。"""

	items: list[AdminLoginHistoryItem]
	meta: AdminUserListMeta
