from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.core.config import get_backend_settings
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration_comments.conftest import ALLOWED_ORIGIN, CommentScenario, write_headers


def _error() -> Exception:
	from sqlalchemy.exc import OperationalError

	return OperationalError("comment transaction", {}, SimpleNamespace(sqlstate="08006"))


@pytest.mark.parametrize(
	("method", "path", "body"),
	[
		("get", "comments", None),
		("post", "comments", {"body": "unauthenticated"}),
		("patch", "comment", {"body": "unauthenticated"}),
		("delete", "comment", None),
	],
)
async def test_comment_endpoints_require_authentication(
	client: TestClient,
	scenario: CommentScenario,
	method: str,
	path: str,
	body: dict[str, str] | None,
) -> None:
	url = f"/api/tasks/{scenario.task_id}/comments" if path == "comments" else f"/api/comments/{scenario.comment_id}"
	response = client.request(
		method.upper(),
		url,
		json=body,
		headers={"Origin": ALLOWED_ORIGIN} if method != "get" else {},
	)
	assert response.status_code == 401, response.text
	assert response.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_comment_mutations_require_csrf_in_session_mode(
	client: TestClient, scenario: CommentScenario, authenticate
) -> None:
	if get_backend_settings().auth_mode != "session":
		pytest.skip("CSRFはsession方式のみで検証する")
	authenticate()
	for method, url, body in (
		("post", f"/api/tasks/{scenario.task_id}/comments", {"body": "missing csrf"}),
		("patch", f"/api/comments/{scenario.comment_id}", {"body": "missing csrf"}),
		("delete", f"/api/comments/{scenario.comment_id}", None),
	):
		response = client.request(method.upper(), url, json=body, headers={"Origin": ALLOWED_ORIGIN})
		assert response.status_code == 403, response.text
		assert response.json()["error"]["code"] == "CSRF_INVALID"


async def test_comment_crud_round_trip_at_api_boundary(
	client: TestClient, scenario: CommentScenario, authenticate
) -> None:
	auth_headers = authenticate()
	created = client.post(
		f"/api/tasks/{scenario.task_id}/comments",
		json={"body": "  posted comment  "},
		headers=write_headers(client, auth_headers),
	)
	assert created.status_code == 201, created.text
	assert created.json()["body"] == "posted comment"
	comment_id = created.json()["id"]

	listed = client.get(f"/api/tasks/{scenario.task_id}/comments", headers=auth_headers)
	assert listed.status_code == 200, listed.text
	assert listed.json()["items"][-1]["id"] == comment_id
	assert listed.json()["items"][-1]["author"]["username"] == scenario.author_username

	updated = client.patch(
		f"/api/comments/{comment_id}",
		json={"body": "  edited comment  "},
		headers=write_headers(client, auth_headers),
	)
	assert updated.status_code == 200, updated.text
	assert updated.json()["body"] == "edited comment"

	deleted = client.delete(f"/api/comments/{comment_id}", headers=write_headers(client, auth_headers))
	assert deleted.status_code == 204
	listed_after_delete = client.get(f"/api/tasks/{scenario.task_id}/comments", headers=auth_headers)
	assert listed_after_delete.status_code == 200
	assert all(item["id"] != comment_id for item in listed_after_delete.json()["items"])


async def test_comment_authorization_boundary_for_peer_outsider_and_admin(
	client: TestClient, scenario: CommentScenario, authenticate
) -> None:
	peer_headers = authenticate("peer")
	assert client.get(f"/api/tasks/{scenario.task_id}/comments", headers=peer_headers).status_code == 200
	for method in ("patch", "delete"):
		response = client.request(
			method.upper(),
			f"/api/comments/{scenario.comment_id}",
			json={"body": "must remain"} if method == "patch" else None,
			headers=write_headers(client, peer_headers),
		)
		assert response.status_code == 403, response.text

	outsider_headers = authenticate("outsider")
	assert client.get(f"/api/tasks/{scenario.task_id}/comments", headers=outsider_headers).status_code == 404
	outsider_post = client.post(
		f"/api/tasks/{scenario.task_id}/comments",
		json={"body": "not allowed"},
		headers=write_headers(client, outsider_headers),
	)
	assert outsider_post.status_code == 404
	outsider_update = client.patch(
		f"/api/comments/{scenario.comment_id}",
		json={"body": "not allowed"},
		headers=write_headers(client, outsider_headers),
	)
	assert outsider_update.status_code == 404
	outsider_delete = client.delete(
		f"/api/comments/{scenario.comment_id}", headers=write_headers(client, outsider_headers)
	)
	assert outsider_delete.status_code == 404

	admin_headers = authenticate("admin")
	admin_update = client.patch(
		f"/api/comments/{scenario.comment_id}",
		json={"body": "admin edited"},
		headers=write_headers(client, admin_headers),
	)
	assert admin_update.status_code == 200, admin_update.text
	admin_delete = client.delete(f"/api/comments/{scenario.comment_id}", headers=write_headers(client, admin_headers))
	assert admin_delete.status_code == 204


async def test_comment_task_scope_handles_inactive_unassigned_and_missing_resources(
	client: TestClient, scenario: CommentScenario, authenticate, db_session: AsyncSession
) -> None:
	auth_headers = authenticate()
	await db_session.execute(
		text("UPDATE tasks SET is_active = false WHERE id = :task_id"), {"task_id": scenario.inactive_task_id}
	)
	await db_session.commit()
	for method, path, body in (
		("get", f"/api/tasks/{scenario.inactive_task_id}/comments", None),
		("post", f"/api/tasks/{scenario.inactive_task_id}/comments", {"body": "inactive"}),
	):
		response = client.request(
			method.upper(), path, json=body, headers=write_headers(client, auth_headers) if body else auth_headers
		)
		assert response.status_code == 404, response.text
	for method, body in (("patch", {"body": "inactive"}), ("delete", None)):
		response = client.request(
			method.upper(),
			f"/api/comments/{scenario.inactive_comment_id}",
			json=body,
			headers=write_headers(client, auth_headers),
		)
		assert response.status_code == 404, response.text

	created = client.post(
		f"/api/tasks/{scenario.unassigned_task_id}/comments",
		json={"body": "unassigned works"},
		headers=write_headers(client, auth_headers),
	)
	assert created.status_code == 201, created.text
	peer_headers = authenticate("peer")
	assert client.get(f"/api/tasks/{scenario.unassigned_task_id}/comments", headers=peer_headers).status_code == 404
	peer_post = client.post(
		f"/api/tasks/{scenario.unassigned_task_id}/comments",
		json={"body": "not allowed"},
		headers=write_headers(client, peer_headers),
	)
	assert peer_post.status_code == 404

	missing_task = client.get("/api/tasks/00000000-0000-4000-8000-000000000000/comments", headers=auth_headers)
	assert missing_task.status_code == 404
	missing_comment = client.patch(
		"/api/comments/00000000-0000-4000-8000-000000000000",
		json={"body": "missing"},
		headers=write_headers(client, auth_headers),
	)
	assert missing_comment.status_code == 404
	missing_delete = client.delete(
		"/api/comments/00000000-0000-4000-8000-000000000000",
		headers=write_headers(client, auth_headers),
	)
	assert missing_delete.status_code == 404


async def test_comment_create_transaction_failure_leaves_no_partial_row(
	client: TestClient, scenario: CommentScenario, authenticate, monkeypatch: pytest.MonkeyPatch
) -> None:
	auth_headers = authenticate()
	from sqlalchemy.ext.asyncio import AsyncSession

	original_commit = AsyncSession.commit
	failed = False

	async def fail_once(session: AsyncSession) -> None:
		nonlocal failed
		if not failed:
			failed = True
			raise _error()
		await original_commit(session)

	monkeypatch.setattr(AsyncSession, "commit", fail_once)
	response = client.post(
		f"/api/tasks/{scenario.task_id}/comments",
		json={"body": "must rollback"},
		headers=write_headers(client, auth_headers),
	)
	assert response.status_code == 503, response.text
	monkeypatch.undo()

	listed = client.get(f"/api/tasks/{scenario.task_id}/comments", headers=auth_headers)
	assert listed.status_code == 200
	assert all(item["body"] != "must rollback" for item in listed.json()["items"])


async def test_comment_update_and_delete_transaction_failure_leave_original_state(
	client: TestClient, scenario: CommentScenario, authenticate, monkeypatch: pytest.MonkeyPatch
) -> None:
	auth_headers = authenticate()
	from sqlalchemy.ext.asyncio import AsyncSession

	original_commit = AsyncSession.commit
	failed = False

	async def fail_once(session: AsyncSession) -> None:
		nonlocal failed
		if not failed:
			failed = True
			raise _error()
		await original_commit(session)

	monkeypatch.setattr(AsyncSession, "commit", fail_once)
	updated = client.patch(
		f"/api/comments/{scenario.comment_id}",
		json={"body": "must rollback"},
		headers=write_headers(client, auth_headers),
	)
	assert updated.status_code == 503, updated.text
	monkeypatch.undo()

	current = client.get(f"/api/tasks/{scenario.task_id}/comments", headers=auth_headers)
	assert current.status_code == 200
	assert current.json()["items"][0]["body"] == "initial comment"

	failed = False
	monkeypatch.setattr(AsyncSession, "commit", fail_once)
	deleted = client.delete(f"/api/comments/{scenario.comment_id}", headers=write_headers(client, auth_headers))
	assert deleted.status_code == 503, deleted.text
	monkeypatch.undo()

	remaining = client.get(f"/api/tasks/{scenario.task_id}/comments", headers=auth_headers)
	assert remaining.status_code == 200
	assert any(item["id"] == str(scenario.comment_id) for item in remaining.json()["items"])
