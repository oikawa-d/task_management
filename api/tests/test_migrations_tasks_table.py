import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
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


async def test_direct_physical_project_delete_cascades_as_defensive_constraint(db_session: AsyncSession) -> None:
	owner_id = await _create_user(db_session, "owner6")
	project_id = await _create_project(db_session, owner_id, "p6")
	await db_session.execute(
		text("INSERT INTO project_members (project_id, user_id) VALUES (:pid, :uid)"),
		{"pid": project_id, "uid": owner_id},
	)
	task_id = (
		await db_session.execute(
			text("INSERT INTO tasks (project_id, created_by, title) VALUES (:pid, :uid, 't') RETURNING id"),
			{"pid": project_id, "uid": owner_id},
		)
	).scalar_one()
	await db_session.execute(
		text("INSERT INTO task_comments (task_id, user_id, body) VALUES (:tid, :uid, 'c')"),
		{"tid": task_id, "uid": owner_id},
	)

	await db_session.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project_id})

	members = (
		await db_session.execute(
			text("SELECT count(*) FROM project_members WHERE project_id = :pid"), {"pid": project_id}
		)
	).scalar_one()
	assert members == 0
	remaining_project_id = (
		await db_session.execute(text("SELECT project_id FROM tasks WHERE id = :tid"), {"tid": task_id})
	).scalar_one()
	assert remaining_project_id is None
	comment_count = (
		await db_session.execute(text("SELECT count(*) FROM task_comments WHERE task_id = :tid"), {"tid": task_id})
	).scalar_one()
	assert comment_count == 1


async def test_direct_physical_task_delete_cascades_comments(db_session: AsyncSession) -> None:
	owner_id = await _create_user(db_session, "owner7")
	project_id = await _create_project(db_session, owner_id, "p7")
	task_id = (
		await db_session.execute(
			text("INSERT INTO tasks (project_id, created_by, title) VALUES (:pid, :uid, 't') RETURNING id"),
			{"pid": project_id, "uid": owner_id},
		)
	).scalar_one()
	await db_session.execute(
		text("INSERT INTO task_comments (task_id, user_id, body) VALUES (:tid, :uid, 'c')"),
		{"tid": task_id, "uid": owner_id},
	)

	await db_session.execute(text("DELETE FROM tasks WHERE id = :id"), {"id": task_id})

	comment_count = (
		await db_session.execute(text("SELECT count(*) FROM task_comments WHERE task_id = :tid"), {"tid": task_id})
	).scalar_one()
	assert comment_count == 0


async def test_tasks_check_constraints_reject_invalid_values(db_session: AsyncSession) -> None:
	owner_id = await _create_user(db_session, "owner8")
	project_id = await _create_project(db_session, owner_id, "p8")

	with pytest.raises(DBAPIError):
		await db_session.execute(
			text("INSERT INTO tasks (project_id, created_by, title, status) VALUES (:pid, :uid, 't', 'invalid')"),
			{"pid": project_id, "uid": owner_id},
		)


async def test_tasks_position_non_negative_check(db_session: AsyncSession) -> None:
	owner_id = await _create_user(db_session, "owner9")
	project_id = await _create_project(db_session, owner_id, "p9")

	with pytest.raises(DBAPIError):
		await db_session.execute(
			text("INSERT INTO tasks (project_id, created_by, title, position) VALUES (:pid, :uid, 't', -1)"),
			{"pid": project_id, "uid": owner_id},
		)


async def test_tasks_project_id_null_allowed(db_session: AsyncSession) -> None:
	owner_id = await _create_user(db_session, "owner10")

	row = (
		(
			await db_session.execute(
				text("INSERT INTO tasks (created_by, title) VALUES (:uid, 't') RETURNING project_id"),
				{"uid": owner_id},
			)
		)
		.mappings()
		.one()
	)

	assert row["project_id"] is None


async def test_uq_tasks_project_status_position_is_deferred_within_transaction(db_session: AsyncSession) -> None:
	owner_id = await _create_user(db_session, "owner11")
	project_id = await _create_project(db_session, owner_id, "p11")
	task1_id = (
		await db_session.execute(
			text(
				"INSERT INTO tasks (project_id, created_by, title, status, position) "
				"VALUES (:pid, :uid, 't1', 'todo', 0) RETURNING id"
			),
			{"pid": project_id, "uid": owner_id},
		)
	).scalar_one()
	task2_id = (
		await db_session.execute(
			text(
				"INSERT INTO tasks (project_id, created_by, title, status, position) "
				"VALUES (:pid, :uid, 't2', 'todo', 1) RETURNING id"
			),
			{"pid": project_id, "uid": owner_id},
		)
	).scalar_one()
	await db_session.commit()

	# 一時的な重複を経由して並べ替える（DEFERRABLE INITIALLY DEFERRED のため中間状態は許容される）
	await db_session.execute(text("UPDATE tasks SET position = 99 WHERE id = :id"), {"id": task1_id})
	await db_session.execute(text("UPDATE tasks SET position = 0 WHERE id = :id"), {"id": task2_id})
	await db_session.execute(text("UPDATE tasks SET position = 1 WHERE id = :id"), {"id": task1_id})
	await db_session.commit()


async def test_uq_tasks_project_status_position_rejects_unresolved_duplicate_on_commit(
	db_session: AsyncSession,
) -> None:
	owner_id = await _create_user(db_session, "owner12")
	project_id = await _create_project(db_session, owner_id, "p12")
	await db_session.execute(
		text(
			"INSERT INTO tasks (project_id, created_by, title, status, position) VALUES (:pid, :uid, 't1', 'todo', 0)"
		),
		{"pid": project_id, "uid": owner_id},
	)
	await db_session.execute(
		text(
			"INSERT INTO tasks (project_id, created_by, title, status, position) VALUES (:pid, :uid, 't2', 'todo', 0)"
		),
		{"pid": project_id, "uid": owner_id},
	)

	with pytest.raises(IntegrityError):
		await db_session.commit()


async def test_trg_tasks_set_updated_at(db_session: AsyncSession) -> None:
	owner_id = await _create_user(db_session, "owner14")
	project_id = await _create_project(db_session, owner_id, "p14")
	task_id = (
		await db_session.execute(
			text("INSERT INTO tasks (project_id, created_by, title) VALUES (:pid, :uid, 't') RETURNING id"),
			{"pid": project_id, "uid": owner_id},
		)
	).scalar_one()
	await db_session.commit()

	before = (
		await db_session.execute(text("SELECT updated_at FROM tasks WHERE id = :id"), {"id": task_id})
	).scalar_one()
	await db_session.execute(text("UPDATE tasks SET title = 'renamed' WHERE id = :id"), {"id": task_id})
	after = (
		await db_session.execute(text("SELECT updated_at FROM tasks WHERE id = :id"), {"id": task_id})
	).scalar_one()
	assert after > before


async def test_trg_task_comments_set_updated_at(db_session: AsyncSession) -> None:
	owner_id = await _create_user(db_session, "owner15")
	project_id = await _create_project(db_session, owner_id, "p15")
	task_id = (
		await db_session.execute(
			text("INSERT INTO tasks (project_id, created_by, title) VALUES (:pid, :uid, 't') RETURNING id"),
			{"pid": project_id, "uid": owner_id},
		)
	).scalar_one()
	comment_id = (
		await db_session.execute(
			text("INSERT INTO task_comments (task_id, user_id, body) VALUES (:tid, :uid, 'c') RETURNING id"),
			{"tid": task_id, "uid": owner_id},
		)
	).scalar_one()
	await db_session.commit()

	before = (
		await db_session.execute(text("SELECT updated_at FROM task_comments WHERE id = :id"), {"id": comment_id})
	).scalar_one()
	await db_session.execute(text("UPDATE task_comments SET body = 'edited' WHERE id = :id"), {"id": comment_id})
	after = (
		await db_session.execute(text("SELECT updated_at FROM task_comments WHERE id = :id"), {"id": comment_id})
	).scalar_one()
	assert after > before
