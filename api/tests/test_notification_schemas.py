from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.schemas.notification import (
	NotificationItem,
	NotificationListQuery,
	NotificationListResponse,
	NotificationMeta,
	NotificationReadAllResponse,
	NotificationReadResponse,
	NotificationTask,
	UnreadCountResponse,
)
from pydantic import BaseModel, ValidationError


def test_notification_list_query_uses_documented_defaults() -> None:
	query = NotificationListQuery()

	assert query.page == 1
	assert query.per_page == 20
	assert query.unread_only is False


@pytest.mark.parametrize(
	"field, value",
	[
		("page", 0),
		("per_page", 0),
		("per_page", 101),
	],
)
def test_notification_list_query_rejects_out_of_range_values(field: str, value: int) -> None:
	with pytest.raises(ValidationError):
		NotificationListQuery(**{field: value})


def test_notification_list_query_accepts_boundary_values_and_boolean_conversion() -> None:
	query = NotificationListQuery(page=2, per_page=100, unread_only="true")

	assert query.page == 2
	assert query.per_page == 100
	assert query.unread_only is True


def test_notification_item_accepts_nested_task_and_nullable_fields() -> None:
	notification_id = uuid4()
	task_id = uuid4()
	project_id = uuid4()
	created_at = datetime(2026, 9, 4, 1, tzinfo=timezone.utc)
	read_at = datetime(2026, 9, 4, 2, tzinfo=timezone.utc)

	notification = NotificationItem(
		id=notification_id,
		type="due_soon_batch",
		title="設計書をレビューする",
		body="期限が近いタスクです",
		task=NotificationTask(id=task_id, project_id=project_id, title="設計書をレビューする"),
		due_at=created_at,
		read_at=read_at,
		created_at=created_at,
	)

	assert notification.id == notification_id
	assert notification.task is not None
	assert notification.task.project_id == project_id

	deleted_task_notification = notification.model_copy(
		update={"body": None, "task": None, "due_at": None, "read_at": None}
	)

	assert deleted_task_notification.task is None
	assert deleted_task_notification.read_at is None


def test_notification_item_rejects_unknown_notification_type() -> None:
	with pytest.raises(ValidationError):
		NotificationItem(
			id=uuid4(),
			type="unknown",
			title="通知",
			created_at=datetime.now(timezone.utc),
		)


def test_notification_list_response_contains_meta_and_unread_count() -> None:
	response = NotificationListResponse(
		items=[],
		meta=NotificationMeta(page=1, per_page=20, total=0, total_pages=0),
		unread_count=0,
	)

	assert response.items == []
	assert response.meta.total_pages == 0
	assert response.unread_count == 0


@pytest.mark.parametrize(
	"schema, field",
	[
		(UnreadCountResponse, "unread_count"),
		(NotificationReadResponse, "unread_count"),
		(NotificationReadAllResponse, "updated_count"),
		(NotificationReadAllResponse, "unread_count"),
	],
)
def test_notification_count_fields_reject_negative_values(schema: type[BaseModel], field: str) -> None:
	kwargs = {field: -1}
	if schema is NotificationReadResponse:
		kwargs["id"] = uuid4()
		kwargs["read_at"] = datetime.now(timezone.utc)

	with pytest.raises(ValidationError):
		schema(**kwargs)


def test_notification_read_responses_match_documented_fields() -> None:
	read_at = datetime(2026, 9, 4, 2, tzinfo=timezone.utc)

	read_response = NotificationReadResponse(id=uuid4(), read_at=read_at, unread_count=2)
	read_all_response = NotificationReadAllResponse(updated_count=3, unread_count=0)

	assert read_response.read_at == read_at
	assert read_response.unread_count == 2
	assert read_all_response.updated_count == 3
	assert read_all_response.unread_count == 0
