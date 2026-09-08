from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def _alembic_config() -> Config:
	return Config(str(ALEMBIC_INI))


@pytest.fixture(autouse=True)
def _reset_schema():
	command.downgrade(_alembic_config(), "base")
	yield
	command.downgrade(_alembic_config(), "base")


@pytest_asyncio.fixture
async def db():
	from app.core.config import get_backend_settings

	engine = create_async_engine(get_backend_settings().database_url)
	session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
	try:
		async with session_factory() as session:
			yield session
	finally:
		await engine.dispose()


async def _create_user_and_project(db: AsyncSession) -> tuple[str, str]:
	user_id = (
		await db.execute(
			text(
				"INSERT INTO users (username, email, password_hash) "
				"VALUES ('notif-owner', 'notif-owner@example.com', 'hash') RETURNING id"
			)
		)
	).scalar_one()
	project_id = (
		await db.execute(
			text("INSERT INTO projects (name, owner_id) VALUES ('P', :owner_id) RETURNING id"),
			{"owner_id": user_id},
		)
	).scalar_one()
	await db.commit()
	return str(user_id), str(project_id)


async def _create_task_via_sp(db: AsyncSession, project_id: str, owner_id: str, due_at: datetime) -> str:
	await db.execute(text("SELECT set_config('TimeZone', 'UTC', true)"))
	result = await db.execute(
		text(
			"CALL sp_create_task(:project_id, :created_by, :assignee_id, 'today', 'body', 'todo', :due_at, NULL, NULL)"
		),
		{"project_id": project_id, "created_by": owner_id, "assignee_id": owner_id, "due_at": due_at},
	)
	task_id = result.mappings().one()["p_task_id"]
	await db.commit()
	return str(task_id)


async def test_migration_0016_upgrade_adds_notification_insert_for_due_today_task(db: AsyncSession) -> None:
	command.upgrade(_alembic_config(), "head")
	owner_id, project_id = await _create_user_and_project(db)
	task_id = await _create_task_via_sp(db, project_id, owner_id, datetime.now(timezone.utc))

	count = (
		await db.execute(text("SELECT count(*) FROM notifications WHERE task_id = :tid"), {"tid": task_id})
	).scalar_one()
	assert count == 1


async def test_migration_0016_downgrade_restores_procedure_without_notification_insert(db: AsyncSession) -> None:
	cfg = _alembic_config()
	command.upgrade(cfg, "head")
	command.downgrade(cfg, "-1")
	owner_id, project_id = await _create_user_and_project(db)
	task_id = await _create_task_via_sp(db, project_id, owner_id, datetime.now(timezone.utc))

	count = (
		await db.execute(text("SELECT count(*) FROM notifications WHERE task_id = :tid"), {"tid": task_id})
	).scalar_one()
	assert count == 0


async def test_migration_0010_alone_creates_task_without_referencing_notifications_table(db: AsyncSession) -> None:
	# 0016が0010と同一のdb/procedures/sp_create_task.sqlを読み込む実装だと、
	# 空DBから0010まで適用しただけで通知INSERT入りの新定義が適用されてしまう
	# （notificationsテーブルは0011で初めて作成されるため、参照するとUndefinedTableで失敗する）。
	# この再現性が保たれていることを確認する回帰テスト。
	command.upgrade(_alembic_config(), "0010")
	owner_id, project_id = await _create_user_and_project(db)
	task_id = await _create_task_via_sp(db, project_id, owner_id, datetime.now(timezone.utc))

	title = (await db.execute(text("SELECT title FROM tasks WHERE id = :tid"), {"tid": task_id})).scalar_one()
	assert title == "today"


async def test_migration_0016_upgrade_downgrade_upgrade_roundtrip_reinstates_notification_insert(
	db: AsyncSession,
) -> None:
	cfg = _alembic_config()
	command.upgrade(cfg, "head")
	command.downgrade(cfg, "-1")
	command.upgrade(cfg, "head")
	owner_id, project_id = await _create_user_and_project(db)
	task_id = await _create_task_via_sp(db, project_id, owner_id, datetime.now(timezone.utc))

	count = (
		await db.execute(text("SELECT count(*) FROM notifications WHERE task_id = :tid"), {"tid": task_id})
	).scalar_one()
	assert count == 1
