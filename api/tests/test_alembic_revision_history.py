import ast
import re
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

VERSIONS_DIR = Path(__file__).resolve().parents[1] / "alembic" / "versions"
MIGRATION_DOCUMENT = Path(__file__).resolve().parents[2] / "docs/detailed_design/database/09_migration.md"
REVISION_FILENAME_PATTERN = re.compile(r"^(?P<revision>\d{4})_[a-z0-9_]+\.py$")


def _revision_id(path: Path) -> str:
	tree = ast.parse(path.read_text(encoding="utf-8"))
	for node in ast.walk(tree):
		if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "revision":
			if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
				return node.value.value
		if isinstance(node, ast.Assign) and any(
			isinstance(target, ast.Name) and target.id == "revision" for target in node.targets
		):
			if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
				return node.value.value
	raise AssertionError(f"revision declaration is missing: {path.name}")


def _down_revision(path: Path) -> str | None:
	tree = ast.parse(path.read_text(encoding="utf-8"))
	for node in ast.walk(tree):
		targets = []
		if isinstance(node, ast.AnnAssign):
			targets = [node.target]
		elif isinstance(node, ast.Assign):
			targets = node.targets
		if not any(isinstance(target, ast.Name) and target.id == "down_revision" for target in targets):
			continue
		value = node.value
		if isinstance(value, ast.Constant) and (value.value is None or isinstance(value.value, str)):
			return value.value
		raise AssertionError(f"down_revision must be a string or None: {path.name}")
	raise AssertionError(f"down_revision declaration is missing: {path.name}")


def test_migration_filename_prefix_matches_revision_id() -> None:
	violations: list[str] = []
	seen_revisions: dict[str, Path] = {}

	for path in sorted(VERSIONS_DIR.glob("*.py")):
		match = REVISION_FILENAME_PATTERN.fullmatch(path.name)
		if match is None:
			violations.append(f"invalid migration filename: {path.name}")
			continue

		expected = match.group("revision")
		actual = _revision_id(path)
		if actual != expected:
			violations.append(f"{path.name}: filename={expected}, revision={actual}")
		if actual in seen_revisions:
			violations.append(f"duplicate revision={actual}: {seen_revisions[actual].name}, {path.name}")
		else:
			seen_revisions[actual] = path

	assert violations == [], "migration filename/revision violations: " + "; ".join(violations)


def test_migration_history_has_single_head() -> None:
	config = Config()
	config.set_main_option("script_location", str(VERSIONS_DIR.parent))

	assert len(ScriptDirectory.from_config(config).get_heads()) == 1


def test_migration_history_is_a_contiguous_single_chain() -> None:
	records = []
	for path in sorted(VERSIONS_DIR.glob("*.py")):
		match = REVISION_FILENAME_PATTERN.fullmatch(path.name)
		if match is not None:
			records.append((int(match.group("revision")), _revision_id(path), _down_revision(path), path.name))

	records.sort()
	violations: list[str] = []
	for index, (prefix, revision, down_revision, filename) in enumerate(records, start=1):
		expected_revision = f"{index:04d}"
		expected_down_revision = None if index == 1 else f"{index - 1:04d}"
		if prefix != index or revision != expected_revision or down_revision != expected_down_revision:
			violations.append(
				f"{filename}: expected revision={expected_revision}, down_revision={expected_down_revision}; "
				f"actual revision={revision}, down_revision={down_revision}"
			)

	assert violations == [], "migration chain violations: " + "; ".join(violations)


def test_migration_filename_naming_convention_is_documented() -> None:
	document = MIGRATION_DOCUMENT.read_text(encoding="utf-8")

	assert "ファイル名の4桁接頭辞は `revision` ID と一致させる" in document
