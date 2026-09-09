from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.schemas.comment import CommentCreateRequest, CommentListResponse, CommentResponse
from pydantic import ValidationError


def test_comment_create_trims_body_and_rejects_unknown_fields() -> None:
	payload = CommentCreateRequest(body="  コメント  ")

	assert payload.body == "コメント"
	with pytest.raises(ValidationError):
		CommentCreateRequest(body="コメント", unexpected=True)


@pytest.mark.parametrize("body", ["", "   ", "a" * 2001])
def test_comment_create_rejects_blank_or_overlong_body(body: str) -> None:
	with pytest.raises(ValidationError):
		CommentCreateRequest(body=body)


def test_comment_response_contains_author_and_timestamps() -> None:
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
	response = CommentListResponse(task_id=uuid4(), items=[], count=0)

	assert response.count == 0
	assert response.model_dump(by_alias=True)["count"] == 0
