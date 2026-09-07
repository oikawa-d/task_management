import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession


async def _create_user(db: AsyncSession, username: str) -> str:
	row = (
		await db.execute(
			text("INSERT INTO users (username, email, password_hash) VALUES (:username, :email, 'hash') RETURNING id"),
			{"username": username, "email": f"{username}@example.com"},
		)
	).scalar_one()
	return str(row)


async def _create_project(db: AsyncSession, owner_id: str, name: str = "proj") -> str:
	row = (
		await db.execute(
			text("INSERT INTO projects (name, owner_id) VALUES (:name, :owner_id) RETURNING id"),
			{"name": name, "owner_id": owner_id},
		)
	).scalar_one()
	return str(row)


async def test_projects_default_is_active_true(db_session: AsyncSession) -> None:
	owner_id = await _create_user(db_session, "owner1")

	row = (
		(
			await db_session.execute(
				text("INSERT INTO projects (name, owner_id) VALUES ('p1', :owner_id) RETURNING is_active"),
				{"owner_id": owner_id},
			)
		)
		.mappings()
		.one()
	)

	assert row["is_active"] is True


async def test_ck_projects_period_rejects_end_before_start(db_session: AsyncSession) -> None:
	owner_id = await _create_user(db_session, "owner2")

	with pytest.raises(DBAPIError):
		await db_session.execute(
			text(
				"INSERT INTO projects (name, owner_id, start_at, end_at) "
				"VALUES ('p2', :owner_id, '2026-02-01T00:00:00Z', '2026-01-01T00:00:00Z')"
			),
			{"owner_id": owner_id},
		)


async def test_ck_projects_period_allows_partial_or_null(db_session: AsyncSession) -> None:
	owner_id = await _create_user(db_session, "owner3")

	await db_session.execute(
		text("INSERT INTO projects (name, owner_id, start_at) VALUES ('p3a', :owner_id, '2026-01-01T00:00:00Z')"),
		{"owner_id": owner_id},
	)
	await db_session.execute(
		text("INSERT INTO projects (name, owner_id, end_at) VALUES ('p3b', :owner_id, '2026-01-01T00:00:00Z')"),
		{"owner_id": owner_id},
	)
	await db_session.execute(
		text("INSERT INTO projects (name, owner_id) VALUES ('p3c', :owner_id)"), {"owner_id": owner_id}
	)


async def test_projects_owner_restrict_prevents_user_delete(db_session: AsyncSession) -> None:
	owner_id = await _create_user(db_session, "owner4")
	await _create_project(db_session, owner_id, "p4")

	with pytest.raises(DBAPIError):
		await db_session.execute(text("DELETE FROM users WHERE id = :id"), {"id": owner_id})


async def test_project_deactivation_does_not_cascade(db_session: AsyncSession) -> None:
	owner_id = await _create_user(db_session, "owner5")
	project_id = await _create_project(db_session, owner_id, "p5")
	await db_session.execute(
		text("INSERT INTO project_members (project_id, user_id) VALUES (:pid, :uid)"),
		{"pid": project_id, "uid": owner_id},
	)
	task_id = (
		await db_session.execute(
			text("INSERT INTO tasks (project_id, created_by, title) VALUES (:pid, :uid, 'task1') RETURNING id"),
			{"pid": project_id, "uid": owner_id},
		)
	).scalar_one()
	await db_session.execute(
		text("INSERT INTO task_comments (task_id, user_id, body) VALUES (:tid, :uid, 'hello')"),
		{"tid": task_id, "uid": owner_id},
	)

	await db_session.execute(text("UPDATE projects SET is_active = false WHERE id = :id"), {"id": project_id})

	members = (
		await db_session.execute(
			text("SELECT count(*) FROM project_members WHERE project_id = :pid"), {"pid": project_id}
		)
	).scalar_one()
	tasks = (
		await db_session.execute(text("SELECT count(*) FROM tasks WHERE project_id = :pid"), {"pid": project_id})
	).scalar_one()
	comments = (
		await db_session.execute(text("SELECT count(*) FROM task_comments WHERE task_id = :tid"), {"tid": task_id})
	).scalar_one()
	assert members == 1
	assert tasks == 1
	assert comments == 1


async def test_trg_projects_set_updated_at(db_session: AsyncSession) -> None:
	owner_id = await _create_user(db_session, "owner13")
	project_id = await _create_project(db_session, owner_id, "p13")
	await db_session.commit()

	before = (
		await db_session.execute(text("SELECT updated_at FROM projects WHERE id = :id"), {"id": project_id})
	).scalar_one()
	await db_session.execute(text("UPDATE projects SET name = 'renamed' WHERE id = :id"), {"id": project_id})
	after = (
		await db_session.execute(text("SELECT updated_at FROM projects WHERE id = :id"), {"id": project_id})
	).scalar_one()
	assert after > before
