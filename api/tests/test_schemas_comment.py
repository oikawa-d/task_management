"""
コメントスキーマのバリデーション・トリミング・フィールド制限を検証するテスト。
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.schemas.comment import CommentCreateRequest, CommentListResponse, CommentResponse
from pydantic import ValidationError


def test_comment_create_trims_body_and_rejects_unknown_fields() -> None:
	"""
	CommentCreateRequest が body を前後の空白でトリミングし、予期しないフィールドを拒否することを検証。

	条件：body が前後に空白を含む場合、トリミング後の値が保持されること。未定義フィールド unexpected を含む場合、ValidationError が送出されること。
	"""
	payload = CommentCreateRequest(body="  コメント  ")

	assert payload.body == "コメント"
	with pytest.raises(ValidationError):
		CommentCreateRequest(body="コメント", unexpected=True)


@pytest.mark.parametrize("body", ["", "   ", "a" * 2001])
def test_comment_create_rejects_blank_or_overlong_body(body: str) -> None:
	"""
	CommentCreateRequest が空またはスペースのみ、または2001文字超の body を拒否することを検証。

	条件：body が空、スペースのみ、または2001文字超のいずれかのとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		CommentCreateRequest(body=body)


def test_comment_response_contains_author_and_timestamps() -> None:
	"""
	CommentResponse が author（ユーザー情報）と created_at・updated_at タイムスタンプを含むことを検証。

	条件：author と timestamps を指定してCommentResponse を作成したとき、各フィールドが正しく保持されること。
	"""
	now = datetime.now(timezone.utc)
	response = CommentResponse(
		id=uuid4(),
		task_id=uuid4(),
		body="コメント",
		author={"id": uuid4(), "username": "taro", "display_name": "太郎"},
		created_at=now,
		updated_at=now,
	)

	assert response.author.username == "taro"
	assert response.updated_at == now


def test_comment_list_response_uses_count_alias() -> None:
	"""
	CommentListResponse の count フィールドがエイリアスをサポートし、model_dump(by_alias=True) で正しく出力されることを検証。

	条件：count フィールドを指定してCommentListResponse を作成し、model_dump(by_alias=True) を呼び出したとき、count キーが含まれること。
	"""
	response = CommentListResponse(task_id=uuid4(), items=[], count=0)

	assert response.count == 0
	assert response.model_dump(by_alias=True)["count"] == 0
