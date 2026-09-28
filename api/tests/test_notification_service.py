"""`app.service.notification_service`（通知一覧取得・既読化・全既読化）のテスト。

リポジトリ呼び出しをモック化した単体テストと、`db_session`を使った実DB結合テストの
両方で、ページング・タスク情報の欠落処理・タイムゾーン変換・DBエラー時のロールバック/
`ServiceUnavailableError`変換・並行更新時の整合性を検証する。
"""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from app.core.config import get_backend_settings
from app.core.exceptions import NotFoundError, ServiceUnavailableError
from app.models.notification import Notification
from app.repository import notification_repository, user_repository
from app.repository.notification_repository import NotificationListItem
from app.schemas.auth import CurrentUser
from app.schemas.notification import NotificationReadAllResponse, NotificationReadResponse
from app.service import notification_service
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def _user() -> CurrentUser:
	"""テスト用の`member`ロールユーザー（`CurrentUser`）を生成するヘルパー関数。

	Returns:
		CurrentUser: ランダムなidを持つ有効ユーザー。
	"""
	return CurrentUser(id=uuid4(), username="taro", role="member", is_active=True, email_verified_at=None)


def _list_item(
	*,
	task_id=None,
	task_title: str | None = None,
	task_project_id=None,
	total_count: int = 1,
) -> NotificationListItem:
	"""`notification_repository.list_by_user`が返す行を模した`NotificationListItem`を
	生成するヘルパー関数。

	Args:
		task_id: 紐づくタスクID（Noneならタスク未紐付け）。
		task_title: タスクタイトル（LEFT JOIN不一致時はNone）。
		task_project_id: タスクの所属プロジェクトID。
		total_count: ウィンドウ関数由来の全体件数。

	Returns:
		NotificationListItem: 通知本体とタスク付随情報・全体件数を持つ疑似リポジトリ行。
	"""
	now = datetime(2026, 9, 4, 1, tzinfo=timezone.utc)
	notification = Notification(
		id=uuid4(),
		user_id=uuid4(),
		task_id=task_id,
		type="due_today_created",
		title="期限です",
		body="確認してください",
		due_at=now,
		dedupe_key="k",
		read_at=None,
		created_at=now,
	)
	return NotificationListItem(
		notification=notification,
		task_title=task_title,
		task_project_id=task_project_id,
		total_count=total_count,
	)


def _patch_repository(
	monkeypatch: pytest.MonkeyPatch,
	*,
	list_by_user_return=None,
	count_notifications_return: int = 0,
	count_unread_return: int = 0,
) -> tuple[AsyncMock, AsyncMock, AsyncMock]:
	"""`notification_service`が参照する`notification_repository`の
	`list_by_user`・`count_notifications`・`count_unread`を`AsyncMock`に差し替えるヘルパー関数。

	Args:
		monkeypatch: モック差し替えに使う`pytest.MonkeyPatch`。
		list_by_user_return: `list_by_user`の戻り値（Noneなら空リスト）。
		count_notifications_return: `count_notifications`の戻り値。
		count_unread_return: `count_unread`の戻り値。

	Returns:
		tuple[AsyncMock, AsyncMock, AsyncMock]: 差し替えた
		`(list_by_user, count_notifications, count_unread)`の各モック。
	"""
	list_by_user = AsyncMock(return_value=list_by_user_return or [])
	count_notifications = AsyncMock(return_value=count_notifications_return)
	count_unread = AsyncMock(return_value=count_unread_return)
	monkeypatch.setattr(notification_service.notification_repository, "list_by_user", list_by_user)
	monkeypatch.setattr(notification_service.notification_repository, "count_notifications", count_notifications)
	monkeypatch.setattr(notification_service.notification_repository, "count_unread", count_unread)
	return list_by_user, count_notifications, count_unread


async def _insert_notification(
	db: AsyncSession,
	user_id,
	dedupe_key: str,
	created_at: datetime,
	read_at: datetime | None = None,
	due_at: datetime | None = None,
):
	"""検証用の通知レコードを`notifications`テーブルへ直接1件INSERTするヘルパー関数。

	Args:
		db: INSERTに使う`AsyncSession`。
		user_id: 通知の宛先ユーザーID。
		dedupe_key: 重複排除キー。
		created_at: 作成日時。
		read_at: 既読日時（Noneなら未読）。
		due_at: タスク期限日時（Noneなら期限無し）。

	Returns:
		作成された通知レコードのid。
	"""
	result = await db.execute(
		text(
			"INSERT INTO notifications "
			"(user_id, type, title, body, due_at, dedupe_key, read_at, created_at) "
			"VALUES (:user_id, 'due_today_created', :title, :body, :due_at, :dedupe_key, :read_at, :created_at) "
			"RETURNING id"
		),
		{
			"user_id": user_id,
			"title": dedupe_key,
			"body": "確認してください",
			"due_at": due_at,
			"dedupe_key": dedupe_key,
			"read_at": read_at,
			"created_at": created_at,
		},
	)
	return result.scalar_one()


@pytest.mark.asyncio
async def test_list_notifications_scopes_repository_to_current_user(monkeypatch: pytest.MonkeyPatch) -> None:
	"""`list_notifications`が`page=2, per_page=20`から`limit=20, offset=20`を算出して
	`list_by_user`を現在のユーザーIDで呼び出し、レスポンスへリポジトリ行の内容を反映することを検証する。
	"""
	user = _user()
	list_by_user, _, _ = _patch_repository(monkeypatch, list_by_user_return=[_list_item()], count_unread_return=1)
	db = object()

	response = await notification_service.list_notifications(db, user, 2, 20, False)  # type: ignore[arg-type]

	list_by_user.assert_awaited_once_with(db, user.id, False, limit=20, offset=20)
	assert response.items[0].title == "期限です"
	assert response.unread_count == 1


@pytest.mark.asyncio
async def test_list_notifications_includes_task_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
	"""紐づくタスク情報（id・project_id・title）がリポジトリ行にある場合、
	レスポンスの`items[].task`へそのまま反映されることを検証する。
	"""
	user = _user()
	task_id = uuid4()
	project_id = uuid4()
	item = _list_item(task_id=task_id, task_title="設計書をレビューする", task_project_id=project_id)
	_patch_repository(monkeypatch, list_by_user_return=[item])
	db = object()

	response = await notification_service.list_notifications(db, user, 1, 20, False)  # type: ignore[arg-type]

	assert response.items[0].task is not None
	assert response.items[0].task.id == task_id
	assert response.items[0].task.project_id == project_id
	assert response.items[0].task.title == "設計書をレビューする"


@pytest.mark.asyncio
async def test_list_notifications_task_deleted_returns_null(monkeypatch: pytest.MonkeyPatch) -> None:
	"""`task_id`がNone（タスクが削除・未紐付け）の場合、レスポンスの`items[].task`が
	Noneになることを検証する。
	"""
	user = _user()
	item = _list_item(task_id=None)
	_patch_repository(monkeypatch, list_by_user_return=[item])
	db = object()

	response = await notification_service.list_notifications(db, user, 1, 20, False)  # type: ignore[arg-type]

	assert response.items[0].task is None


@pytest.mark.asyncio
async def test_list_notifications_task_title_none_returns_null_task(monkeypatch: pytest.MonkeyPatch) -> None:
	"""task_idが非NULLでもtask_titleがNULL（LEFT JOIN不一致）ならtask=nullとする。"""
	user = _user()
	item = _list_item(task_id=uuid4(), task_title=None, task_project_id=uuid4())
	_patch_repository(monkeypatch, list_by_user_return=[item])
	db = object()

	response = await notification_service.list_notifications(db, user, 1, 20, False)  # type: ignore[arg-type]

	assert response.items[0].task is None


@pytest.mark.asyncio
async def test_list_notifications_meta_total_reflects_overall_count_not_page_size(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""リポジトリ行の`total_count`（ウィンドウ関数由来の全体件数、この例では25）が、
	取得した行数（5）ではなく`meta.total`にそのまま反映され、`meta.total_pages`が
	`per_page=20`から`ceil(25/20)=2`となることを検証する。
	"""
	user = _user()
	items = [_list_item(total_count=25) for _ in range(5)]
	_patch_repository(monkeypatch, list_by_user_return=items)
	db = object()

	response = await notification_service.list_notifications(db, user, 2, 20, False)  # type: ignore[arg-type]

	assert len(response.items) == 5
	assert response.meta.total == 25
	assert response.meta.total_pages == 2


@pytest.mark.asyncio
async def test_list_notifications_meta_total_uses_fallback_when_no_rows(monkeypatch: pytest.MonkeyPatch) -> None:
	"""pageが総ページ数を超えitemsが空でも、meta.totalは0ではなく実際の全体件数を返す。"""
	user = _user()
	_, count_notifications, _ = _patch_repository(monkeypatch, list_by_user_return=[], count_notifications_return=7)
	db = object()

	response = await notification_service.list_notifications(db, user, 99, 20, False)  # type: ignore[arg-type]

	count_notifications.assert_awaited_once_with(db, user.id, False)
	assert response.items == []
	assert response.meta.total == 7
	assert response.meta.total_pages == 1


@pytest.mark.asyncio
async def test_list_notifications_calls_count_unread_only_when_not_unread_only(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""`unread_only=False`の場合、未読件数取得に`count_unread`のみが呼ばれ
	（`count_notifications`は呼ばれず）、その戻り値がレスポンスの`unread_count`になることを検証する。
	"""
	user = _user()
	_, count_notifications, count_unread = _patch_repository(
		monkeypatch, list_by_user_return=[_list_item(total_count=3)], count_unread_return=2
	)
	db = object()

	response = await notification_service.list_notifications(db, user, 1, 20, False)  # type: ignore[arg-type]

	count_unread.assert_awaited_once_with(db, user.id)
	count_notifications.assert_not_awaited()
	assert response.unread_count == 2


@pytest.mark.asyncio
async def test_list_notifications_skips_count_unread_when_unread_only(monkeypatch: pytest.MonkeyPatch) -> None:
	"""`unread_only=True`の場合、`count_unread`・`count_notifications`のどちらも呼ばれず、
	リポジトリ行の`total_count`がそのまま`unread_count`・`meta.total`になることを検証する。
	"""
	user = _user()
	_, count_notifications, count_unread = _patch_repository(
		monkeypatch, list_by_user_return=[_list_item(total_count=4)]
	)
	db = object()

	response = await notification_service.list_notifications(db, user, 1, 20, True)  # type: ignore[arg-type]

	count_unread.assert_not_awaited()
	count_notifications.assert_not_awaited()
	assert response.unread_count == 4
	assert response.meta.total == 4


@pytest.mark.asyncio
async def test_mark_all_notifications_returns_changed_count(monkeypatch: pytest.MonkeyPatch) -> None:
	"""`mark_all_notifications_read`が`mark_all_read`の戻り値を`updated_count`、
	更新後の`count_unread`結果を`unread_count`としてレスポンスに反映し、
	`db.commit`を1回呼ぶことを検証する。
	"""
	user = _user()
	mark_all_read = AsyncMock(return_value=3)
	monkeypatch.setattr(notification_service.notification_repository, "count_unread", AsyncMock(return_value=0))
	monkeypatch.setattr(notification_service.notification_repository, "mark_all_read", mark_all_read)
	db = AsyncMock()

	response = await notification_service.mark_all_notifications_read(db, user)  # type: ignore[arg-type]

	mark_all_read.assert_awaited_once_with(db, user.id)
	db.commit.assert_awaited_once()
	assert response.updated_count == 3
	assert response.unread_count == 0


@pytest.mark.asyncio
async def test_mark_notification_read_returns_app_timezone(monkeypatch: pytest.MonkeyPatch) -> None:
	"""`mark_notification_read`が、リポジトリから返されたUTCの`read_at`を
	アプリタイムゾーン（Asia/Tokyo）へ変換してレスポンスに含め、`db.commit`を1回呼ぶことを検証する。
	"""
	user = _user()
	persisted_read_at = datetime(2026, 9, 4, 17, 0, tzinfo=timezone.utc)
	mark_read = AsyncMock(return_value=persisted_read_at)
	monkeypatch.setattr(notification_service.notification_repository, "mark_read", mark_read)
	monkeypatch.setattr(notification_service.notification_repository, "count_unread", AsyncMock(return_value=0))
	notification_id = uuid4()
	db = AsyncMock()

	response = await notification_service.mark_notification_read(db, notification_id, user)  # type: ignore[arg-type]

	mark_read.assert_awaited_once_with(db, notification_id, user.id)
	assert response.id == notification_id
	assert response.read_at == persisted_read_at.astimezone(ZoneInfo("Asia/Tokyo"))
	db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_notification_read_returns_404_when_repository_returns_none(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""`mark_read`が`None`（対象通知が存在しない、または他ユーザー所有）を返した場合、
	`NotFoundError`が送出され、`count_unread`は呼ばれず`db.rollback`も呼ばれないことを検証する。
	"""
	user = _user()
	mark_read = AsyncMock(return_value=None)
	count_unread = AsyncMock(return_value=0)
	monkeypatch.setattr(notification_service.notification_repository, "mark_read", mark_read)
	monkeypatch.setattr(notification_service.notification_repository, "count_unread", count_unread)
	db = AsyncMock()

	with pytest.raises(NotFoundError):
		await notification_service.mark_notification_read(db, uuid4(), user)  # type: ignore[arg-type]

	count_unread.assert_not_awaited()
	db.rollback.assert_not_awaited()


@pytest.mark.parametrize("operation", ["mark_read", "mark_all_read"])
async def test_notification_mutation_rolls_back_on_database_error(
	monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
	"""`mark_read`・`mark_all_read`のいずれかが一般的な`DBAPIError`を送出した場合、
	`mark_notification_read`/`mark_all_notifications_read`が`db.rollback`を呼び、
	`db.commit`は呼ばずに例外をそのまま伝播させることを検証する。
	"""
	user = _user()
	db = AsyncMock()
	db_error = DBAPIError("notification update", {}, Exception("database error"))
	if operation == "mark_read":
		monkeypatch.setattr(notification_service.notification_repository, "mark_read", AsyncMock(side_effect=db_error))
		call = notification_service.mark_notification_read(db, uuid4(), user)
	else:
		monkeypatch.setattr(
			notification_service.notification_repository, "mark_all_read", AsyncMock(side_effect=db_error)
		)
		call = notification_service.mark_all_notifications_read(db, user)

	with pytest.raises(DBAPIError):
		await call  # type: ignore[arg-type]

	db.rollback.assert_awaited_once()
	db.commit.assert_not_awaited()


@pytest.mark.parametrize("operation", ["mark_read", "mark_all_read"])
async def test_notification_mutation_converts_connection_failure_via_raise_database_error(
	monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
	"""project_service.pyと同じ`raise_database_error`経由の変換を検証する。

	接続系のOperationalError（SQLSTATE 08xxx）は`ServiceUnavailableError`へ変換される。
	素の`except DBAPIError: raise`（旧実装）ではOperationalErrorがそのまま伝播し、
	このテストは失敗する。
	"""
	user = _user()
	db = AsyncMock()
	connection_error = OperationalError("notification update", {}, SimpleNamespace(sqlstate="08006"))
	if operation == "mark_read":
		monkeypatch.setattr(
			notification_service.notification_repository, "mark_read", AsyncMock(side_effect=connection_error)
		)
		call = notification_service.mark_notification_read(db, uuid4(), user)
	else:
		monkeypatch.setattr(
			notification_service.notification_repository, "mark_all_read", AsyncMock(side_effect=connection_error)
		)
		call = notification_service.mark_all_notifications_read(db, user)

	with pytest.raises(ServiceUnavailableError):
		await call  # type: ignore[arg-type]

	db.rollback.assert_awaited_once()
	db.commit.assert_not_awaited()


async def test_notification_lifecycle_uses_database_contract(db_session: AsyncSession) -> None:
	"""実DBを用いて、他ユーザーの通知が混ざらないこと・`due_at`がJST（UTC+9）に変換されること・
	個別既読化と全既読化の件数集計・二重既読化時のべき等性（同じ`read_at`・`unread_count`が
	返る）を、通知一覧取得から既読化までの一連の流れで検証する。
	"""
	user_id = await user_repository.create(db_session, "notification-lifecycle", "notification@example.com", "hash")
	other_user_id = await user_repository.create(
		db_session, "notification-other", "notification-other@example.com", "hash"
	)
	now = datetime(2026, 9, 4, 1, tzinfo=timezone.utc)
	first_id = await _insert_notification(db_session, user_id, "first", now, due_at=now)
	await _insert_notification(db_session, user_id, "second", now - timedelta(hours=1))
	await _insert_notification(
		db_session, user_id, "already-read", now - timedelta(hours=2), read_at=now - timedelta(days=1)
	)
	other_id = await _insert_notification(db_session, other_user_id, "other", now)
	current_user = CurrentUser(
		id=user_id, username="notification-lifecycle", role="member", is_active=True, email_verified_at=None
	)

	page = await notification_service.list_notifications(db_session, current_user, 1, 2, False)
	assert len(page.items) == 2
	assert page.meta.total == 3
	assert page.unread_count == 2
	assert all(item.id != other_id for item in page.items)
	first_item = next(item for item in page.items if item.id == first_id)
	# aware datetime同士の`==`は瞬間比較のためUTC/JST表現の差異を検出できない(常にTrueになる)。
	# オフセットと壁時計時刻を直接検証し、変換が行われなかった場合(UTCのまま返る場合)に
	# 確実に失敗するようにする。
	assert first_item.due_at.utcoffset() == timedelta(hours=9)
	assert (
		first_item.due_at.year,
		first_item.due_at.month,
		first_item.due_at.day,
		first_item.due_at.hour,
		first_item.due_at.minute,
	) == (2026, 9, 4, 10, 0)

	read_response = await notification_service.mark_notification_read(db_session, first_id, current_user)
	assert read_response.id == first_id
	assert read_response.unread_count == 1
	read_again_response = await notification_service.mark_notification_read(db_session, first_id, current_user)
	assert read_again_response.read_at == read_response.read_at
	assert read_again_response.unread_count == read_response.unread_count

	read_all_response = await notification_service.mark_all_notifications_read(db_session, current_user)
	assert read_all_response.updated_count == 1
	assert read_all_response.unread_count == 0
	assert await notification_repository.count_unread(db_session, other_user_id) == 1
	empty_read_all_response = await notification_service.mark_all_notifications_read(db_session, current_user)
	assert empty_read_all_response.updated_count == 0
	assert empty_read_all_response.unread_count == 0


async def test_notification_due_at_rolls_over_to_next_day_in_app_timezone(db_session: AsyncSession) -> None:
	"""UTCの`due_at`（2026-09-04 15:30）をアプリタイムゾーン（JST）へ変換すると
	日付が繰り上がる（2026-09-05 00:30）境界値について、`list_notifications`が
	正しくJST表現の日時を返すことを実DBで検証する。
	"""
	user_id = await user_repository.create(
		db_session, "notification-date-boundary", "notification-date-boundary@example.com", "hash"
	)
	# UTC 2026-09-04 15:30 はJST(UTC+9)では日付が繰り上がり 2026-09-05 00:30 になる境界値。
	due_at = datetime(2026, 9, 4, 15, 30, tzinfo=timezone.utc)
	notification_id = await _insert_notification(db_session, user_id, "date-boundary", due_at, due_at=due_at)
	current_user = CurrentUser(
		id=user_id, username="notification-date-boundary", role="member", is_active=True, email_verified_at=None
	)

	page = await notification_service.list_notifications(db_session, current_user, 1, 10, False)

	item = next(item for item in page.items if item.id == notification_id)
	assert item.due_at.utcoffset() == timedelta(hours=9)
	assert (item.due_at.year, item.due_at.month, item.due_at.day, item.due_at.hour, item.due_at.minute) == (
		2026,
		9,
		5,
		0,
		30,
	)


async def test_read_all_is_consistent_with_concurrent_individual_read(db_session: AsyncSession) -> None:
	"""同一通知に対して個別既読化（`mark_notification_read`）と全既読化
	（`mark_all_notifications_read`）を別セッションから並行実行しても、
	最終的な未読件数が0件に収束し、各レスポンスの件数が矛盾しない範囲に収まることを検証する。
	"""
	username = f"notification-concurrent-{uuid4().hex[:8]}"
	user_id = await user_repository.create(db_session, username, f"{username}@example.com", "hash")
	notification_id = await _insert_notification(
		db_session, user_id, f"concurrent-{uuid4().hex}", datetime.now(timezone.utc)
	)
	await db_session.commit()
	current_user = CurrentUser(id=user_id, username=username, role="member", is_active=True, email_verified_at=None)

	engine = create_async_engine(get_backend_settings().database_url)
	session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

	async def _mark_individual() -> NotificationReadResponse:
		async with session_factory() as session:
			response = await notification_service.mark_notification_read(session, notification_id, current_user)
			await session.commit()
			return response

	async def _mark_all() -> NotificationReadAllResponse:
		async with session_factory() as session:
			response = await notification_service.mark_all_notifications_read(session, current_user)
			await session.commit()
			return response

	try:
		individual_response, read_all_response = await asyncio.wait_for(
			asyncio.gather(_mark_individual(), _mark_all()), timeout=5
		)
	finally:
		await engine.dispose()

	assert individual_response.unread_count >= 0
	assert read_all_response.updated_count in (0, 1)
	assert read_all_response.unread_count >= 0
	assert await notification_repository.count_unread(db_session, user_id) == 0
