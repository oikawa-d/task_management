"""タスクコメント関連エンドポイント（`comment_router`）の入出力DTOを定義するモジュール。"""

from datetime import datetime
from uuid import UUID

from pydantic import UUID4, ConfigDict, Field, field_validator

from app.core.config import get_backend_settings
from app.schemas.base import StrictSchema


def _validate_body_length(value: str) -> str:
	"""コメント本文が設定上限文字数（`task_comment_body_max_length`）以内かを検証する。

	Args:
		value: 検証対象のコメント本文。

	Returns:
		検証を通過した本文（値は変更しない）。

	Raises:
		ValueError: 上限文字数を超えている場合。
	"""
	if len(value) > get_backend_settings().task_comment_body_max_length:
		raise ValueError("comment body exceeds the configured maximum length")
	return value


class CommentAuthor(StrictSchema):
	"""コメント投稿者の表示用情報を表すDTO。`CommentResponse.author` として埋め込まれる。"""

	id: UUID4
	username: str
	display_name: str


class CommentCreateRequest(StrictSchema):
	"""`POST /api/tasks/{task_id}/comments` のリクエストDTO。前後空白を除去したうえで本文長を検証する。"""

	model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

	body: str = Field(min_length=1)

	@field_validator("body")
	@classmethod
	def validate_body(cls, value: str) -> str:
		"""コメント本文の長さを検証するフィールドバリデータ。`_validate_body_length` に委譲する。"""
		return _validate_body_length(value)


class CommentUpdateRequest(CommentCreateRequest):
	"""`PATCH /api/comments/{comment_id}` のリクエストDTO。作成時と同じ制約を流用する。"""


class CommentResponse(StrictSchema):
	"""コメント1件のレスポンスDTO。作成・更新・詳細取得の各エンドポイントで共通利用する。"""

	id: UUID4
	task_id: UUID4
	body: str
	author: CommentAuthor
	created_at: datetime
	updated_at: datetime


class CommentListResponse(StrictSchema):
	"""`GET /api/tasks/{task_id}/comments` のレスポンスDTO。対象タスクのコメント一覧と件数を返す。"""

	task_id: UUID
	items: list[CommentResponse]
	count: int = Field(ge=0)
