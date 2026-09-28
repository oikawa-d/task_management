"""プロジェクト・タスク関連のDB関数（`fn_is_project_member`・`fn_next_task_position`）と、
タスク作成・更新プロシージャ（`sp_create_task`・`sp_update_task`）による
期限当日通知の作成・重複排除・アクセス制御を検証する実DB結合テスト。
"""

from datetime import UTC, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.core.config import get_backend_settings
from app.repository import project_repository, task_repository, user_repository
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _due_at_in_app_date(day_offset: int = 0) -> datetime:
	"""アプリのタイムゾーン基準で「今日からday_offset日後」0:30となるUTC日時を生成するヘルパー関数。

	Args:
		day_offset: アプリタイムゾーンの今日からのオフセット日数（0なら当日）。

	Returns:
		datetime: 該当ローカル日の0:30を表すUTCの`datetime`。
	"""
	settings = get_backend_settings()
	app_timezone = ZoneInfo(settings.app_timezone)
	local_date = datetime.now(UTC).astimezone(app_timezone).date() + timedelta(days=day_offset)
	return datetime.combine(local_date, time(0, 30), tzinfo=app_timezone).astimezone(timezone.utc)


async def test_fn_is_project_member_member_returns_true(db_session: AsyncSession) -> None:
	"""プロジェクト作成者（`project_repository.create`のowner）に対し、
	`fn_is_project_member`がTrueを返すことを検証する。
	"""
	owner_id = await user_repository.create(db_session, "alice", "alice@example.com", "hash")
	project_id = await project_repository.create(db_session, owner_id, "P", None, None, None)

	result = (
		await db_session.execute(text("SELECT fn_is_project_member(:pid, :uid)"), {"pid": project_id, "uid": owner_id})
	).scalar_one()
	assert result is True


async def test_fn_is_project_member_non_member_returns_false(db_session: AsyncSession) -> None:
	"""プロジェクトに所属せず`admin`でもない一般ユーザーに対し、
	`fn_is_project_member`がFalseを返すことを検証する。
	"""
	owner_id = await user_repository.create(db_session, "bob", "bob@example.com", "hash")
	stranger_id = await user_repository.create(db_session, "stranger", "stranger@example.com", "hash")
	project_id = await project_repository.create(db_session, owner_id, "P", None, None, None)

	result = (
		await db_session.execute(
			text("SELECT fn_is_project_member(:pid, :uid)"), {"pid": project_id, "uid": stranger_id}
		)
	).scalar_one()
	assert result is False


async def test_fn_is_project_member_admin_bypasses_membership(db_session: AsyncSession) -> None:
	"""`role='admin'`のユーザーは`project_members`に所属レコードが無くても、
	`fn_is_project_member`がTrueを返すことを検証する。
	"""
	owner_id = await user_repository.create(db_session, "carol", "carol@example.com", "hash")
	admin_id = await user_repository.create(db_session, "admin1", "admin1@example.com", "hash")
	await db_session.execute(text("UPDATE users SET role = 'admin' WHERE id = :id"), {"id": admin_id})
	project_id = await project_repository.create(db_session, owner_id, "P", None, None, None)

	result = (
		await db_session.execute(text("SELECT fn_is_project_member(:pid, :uid)"), {"pid": project_id, "uid": admin_id})
	).scalar_one()
	assert result is True


async def test_fn_is_project_member_inactive_user_returns_false(db_session: AsyncSession) -> None:
	"""`is_active=false`に更新されたプロジェクト作成者に対し、
	`fn_is_project_member`がFalse（無効化ユーザーは非該当）を返すことを検証する。
	"""
	owner_id = await user_repository.create(db_session, "dave", "dave@example.com", "hash")
	project_id = await project_repository.create(db_session, owner_id, "P", None, None, None)
	await db_session.execute(text("UPDATE users SET is_active = false WHERE id = :id"), {"id": owner_id})

	result = (
		await db_session.execute(text("SELECT fn_is_project_member(:pid, :uid)"), {"pid": project_id, "uid": owner_id})
	).scalar_one()
	assert result is False


async def test_fn_next_task_position_empty_column_returns_zero(db_session: AsyncSession) -> None:
	"""指定プロジェクト・ステータス（'todo'）にタスクが1件も無い場合、
	`fn_next_task_position`が採番の初期値0を返すことを検証する。
	"""
	owner_id = await user_repository.create(db_session, "erin", "erin@example.com", "hash")
	project_id = await project_repository.create(db_session, owner_id, "P", None, None, None)

	result = (
		await db_session.execute(text("SELECT fn_next_task_position(:pid, 'todo')"), {"pid": project_id})
	).scalar_one()
	assert result == 0


async def test_fn_list_tasks_unassigned_visible_only_to_creator(db_session: AsyncSession) -> None:
	"""プロジェクト未所属（`project_id=None`）のタスクが、作成者向けの`list_for_user`結果には含まれ、
	作成者以外のユーザー向けの結果には含まれないことを検証する。
	"""
	creator_id = await user_repository.create(db_session, "frank", "frank@example.com", "hash")
	other_id = await user_repository.create(db_session, "grace", "grace@example.com", "hash")
	task_id = await task_repository.create(db_session, None, creator_id, None, "unassigned", None, "todo", None, None)

	own = await task_repository.list_for_user(db_session, creator_id, None, None, False, 50, 0)
	other = await task_repository.list_for_user(db_session, other_id, None, None, False, 50, 0)

	assert task_id in {r.task.id for r in own}
	assert task_id not in {r.task.id for r in other}


async def test_fn_list_tasks_admin_sees_all_unassigned_tasks(db_session: AsyncSession) -> None:
	"""`role='admin'`のユーザーが、自分が作成していないプロジェクト未所属タスクも含め、
	`list_for_user`の結果に両方のタスクが含まれることを検証する。
	"""
	creator_id = await user_repository.create(db_session, "frank-admin-owner", "frank-admin-owner@example.com", "hash")
	admin_id = await user_repository.create(db_session, "grace-admin", "grace-admin@example.com", "hash")
	await db_session.execute(text("UPDATE users SET role = 'admin' WHERE id = :id"), {"id": admin_id})
	first_task_id = await task_repository.create(db_session, None, creator_id, None, "first", None, "todo", None, None)
	second_task_id = await task_repository.create(db_session, None, admin_id, None, "second", None, "todo", None, None)

	results = await task_repository.list_for_user(db_session, admin_id, None, None, False, 50, 0)

	assert {result.task.id for result in results} >= {first_task_id, second_task_id}


async def test_fn_list_tasks_non_member_cannot_see_project_scoped_tasks(db_session: AsyncSession) -> None:
	"""プロジェクトに所属しない一般ユーザーが、そのプロジェクトIDを指定して
	`list_for_user`を呼び出しても空リストが返り、タスクが閲覧できないことを検証する。
	"""
	owner_id = await user_repository.create(db_session, "heidi", "heidi@example.com", "hash")
	stranger_id = await user_repository.create(db_session, "ivan", "ivan@example.com", "hash")
	project_id = await project_repository.create(db_session, owner_id, "P", None, None, None)
	await task_repository.create(db_session, project_id, owner_id, None, "t", None, "todo", None, None)

	result = await task_repository.list_for_user(db_session, stranger_id, project_id, None, False, 50, 0)

	assert result == []


async def test_sp_create_task_inserts_due_today_notification_for_assignee(db_session: AsyncSession) -> None:
	"""担当者ありでアプリ日付基準の当日が期限のタスクを作成すると、`sp_create_task`が
	担当者宛に`type='due_today_created'`・`dedupe_key='created:<task_id>'`の通知を
	1件作成することを検証する。
	"""
	owner_id = await user_repository.create(db_session, "task-notify-create", "task-notify-create@example.com", "hash")
	project_id = await project_repository.create(db_session, owner_id, "P", None, None, None)
	due_at = _due_at_in_app_date()

	task_id = await task_repository.create(
		db_session, project_id, owner_id, owner_id, "today", "body", "todo", due_at, None
	)
	notification = (
		(
			await db_session.execute(
				text(
					"SELECT task_id, user_id, type, title, body, due_at, dedupe_key "
					"FROM notifications WHERE task_id = :task_id"
				),
				{"task_id": task_id},
			)
		)
		.mappings()
		.one()
	)

	assert notification["task_id"] == task_id
	assert notification["user_id"] == owner_id
	assert notification["type"] == "due_today_created"
	assert notification["title"] == "today"
	assert notification["body"] == "body"
	assert notification["due_at"] == due_at
	assert notification["dedupe_key"] == f"created:{task_id}"


async def test_sp_create_task_skips_notification_without_assignee_or_for_future(
	db_session: AsyncSession,
) -> None:
	"""担当者未設定のタスク、および期限が翌日以降のタスクを作成した場合、
	`sp_create_task`がいずれについても通知を作成しないことを検証する。
	"""
	owner_id = await user_repository.create(db_session, "task-notify-skip", "task-notify-skip@example.com", "hash")
	project_id = await project_repository.create(db_session, owner_id, "P", None, None, None)

	await task_repository.create(
		db_session, project_id, owner_id, None, "unassigned", None, "todo", _due_at_in_app_date(), None
	)
	await task_repository.create(
		db_session, project_id, owner_id, owner_id, "future", None, "todo", _due_at_in_app_date(1), None
	)

	count = (
		await db_session.execute(
			text("SELECT count(*) FROM notifications WHERE user_id = :user_id"), {"user_id": owner_id}
		)
	).scalar_one()
	assert count == 0


async def test_sp_update_task_notifies_only_when_due_at_changes_to_today_and_deduplicates(
	db_session: AsyncSession,
) -> None:
	"""期限を「変更無し→当日→翌日→再び当日（同一日時）」の順に更新した場合、
	`sp_update_task`が期限を当日へ変更した1回目のみ`type='due_today_updated'`の通知を作成し、
	同一`due_at`への再更新は`dedupe_key`の一意制約により重複作成されないことを検証する。
	"""
	owner_id = await user_repository.create(db_session, "task-notify-update", "task-notify-update@example.com", "hash")
	project_id = await project_repository.create(db_session, owner_id, "P", None, None, None)
	yesterday_due_at = _due_at_in_app_date(-1)
	today_due_at = _due_at_in_app_date()
	tomorrow_due_at = _due_at_in_app_date(1)
	task_id = await task_repository.create(
		db_session, project_id, owner_id, owner_id, "before", None, "todo", yesterday_due_at, None
	)

	await task_repository.update(
		db_session, task_id, owner_id, 1, "no due change", None, "todo", owner_id, yesterday_due_at, None
	)
	await task_repository.update(db_session, task_id, owner_id, 2, "today", None, "todo", owner_id, today_due_at, None)
	await task_repository.update(
		db_session, task_id, owner_id, 3, "tomorrow", None, "todo", owner_id, tomorrow_due_at, None
	)
	await task_repository.update(
		db_session, task_id, owner_id, 4, "today again", None, "todo", owner_id, today_due_at, None
	)

	notifications = (
		(
			await db_session.execute(
				text("SELECT type, title, due_at, dedupe_key FROM notifications WHERE task_id = :task_id"),
				{"task_id": task_id},
			)
		)
		.mappings()
		.all()
	)

	assert notifications == [
		{
			"type": "due_today_updated",
			"title": "today",
			"due_at": today_due_at,
			"dedupe_key": f"updated:{task_id}:{today_due_at.strftime('%Y-%m-%dT%H:%M:%S.%fZ')}",
		}
	]
