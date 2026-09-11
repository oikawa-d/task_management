"""Alembic revisionの重複・分岐・孤立をDBなしで検証する。"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

VERSIONS_DIR = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _revision_values(path: Path) -> tuple[str, str | None]:
	tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
	values: dict[str, str | None] = {}
	for node in tree.body:
		if not isinstance(node, (ast.Assign, ast.AnnAssign)):
			continue
		targets = node.targets if isinstance(node, ast.Assign) else [node.target]
		for target in targets:
			if not isinstance(target, ast.Name) or target.id not in {"revision", "down_revision"}:
				continue
			value = node.value
			if isinstance(value, ast.Constant) and (isinstance(value.value, str) or value.value is None):
				values[target.id] = value.value
			else:
				raise AssertionError(f"{path} の {target.id} は文字列またはNoneで定義してください")
	if "revision" not in values or "down_revision" not in values:
		raise AssertionError(f"{path} にrevision/down_revision定義がありません")
	return values["revision"], values["down_revision"]


def _revision_graph() -> dict[str, tuple[str, str | None]]:
	entries = {path.name: _revision_values(path) for path in VERSIONS_DIR.glob("*.py") if path.name != "__init__.py"}
	by_revision: dict[str, tuple[str, str | None]] = {}
	duplicates: dict[str, list[str]] = {}
	for filename, entry in entries.items():
		revision = entry[0]
		if revision in by_revision:
			duplicates.setdefault(revision, [by_revision[revision][0]]).append(filename)
		else:
			by_revision[revision] = (filename, entry[1])
	if duplicates:
		raise AssertionError(f"revision IDが重複しています: {duplicates}")
	return by_revision


def test_alembic_revisions_are_unique_continuous_and_connected() -> None:
	graph = _revision_graph()
	assert graph, "Alembic revisionがありません"

	ids = sorted(graph, key=int)
	assert ids == [f"{index:04d}" for index in range(1, len(ids) + 1)]

	parents = {parent for _, parent in graph.values() if parent is not None}
	missing = parents - graph.keys()
	assert not missing, f"down_revisionが存在しません: {sorted(missing)}"

	heads = set(graph) - parents
	assert heads == {ids[-1]}, f"headが単一ではありません: {sorted(heads)}"

	visited: set[str] = set()
	current: str | None = ids[-1]
	while current is not None:
		assert current not in visited, f"revision履歴が循環しています: {current}"
		visited.add(current)
		current = graph[current][1]
	assert visited == set(graph), f"孤立したrevisionがあります: {sorted(set(graph) - visited)}"


def test_revision_filename_prefix_matches_revision_id() -> None:
	for path in VERSIONS_DIR.glob("*.py"):
		if path.name == "__init__.py":
			continue
		revision, _ = _revision_values(path)
		assert path.name[:4] == revision, f"ファイル名接頭辞とrevision IDが不一致です: {path.name} -> {revision}"


@pytest.mark.parametrize("revision", ["0021", "0022", "0023", "0024"])
def test_recent_revision_has_expected_parent(revision: str) -> None:
	graph = _revision_graph()
	index = int(revision)
	assert graph[revision][1] == f"{index - 1:04d}"


def test_migration_0023_downgrade_assets_exist() -> None:
	legacy_dir = VERSIONS_DIR.parents[2] / "db" / "procedures" / "legacy"
	for filename in (
		"0022_sp_mark_notification_read.sql",
		"0022_sp_mark_all_notifications_read.sql",
	):
		asset = legacy_dir / filename
		assert asset.is_file(), f"downgrade用SQL資材がありません: {asset}"


def test_recent_migration_source_assets_exist() -> None:
	repository_root = VERSIONS_DIR.parents[2]
	for relative_path in (
		"db/procedures/sp_mark_notification_read.sql",
		"db/procedures/sp_mark_all_notifications_read.sql",
		"db/functions/fn_list_calendar_tasks.sql",
	):
		asset = repository_root / relative_path
		assert asset.is_file(), f"migrationが参照するSQL資材がありません: {asset}"
