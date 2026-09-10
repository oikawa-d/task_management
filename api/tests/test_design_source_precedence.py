from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_repository_guidelines_prioritize_design_documents_over_issue_body() -> None:
	guidelines = (REPOSITORY_ROOT / "AGENTS.md").read_text(encoding="utf-8")

	assert "issue本文と設計書が食い違う場合は、設計書が正です。" in guidelines
	assert "実装ファイルの配置" in guidelines
	assert "詳細設計書の「実装ファイル」欄を唯一の正" in guidelines


def test_auth_design_documents_define_implementation_file_locations() -> None:
	auth_documents = sorted((REPOSITORY_ROOT / "docs/detailed_design/auth").glob("*.md"))

	assert auth_documents
	assert all("実装ファイル" in document.read_text(encoding="utf-8") for document in auth_documents)
	assert "api/app/auth/base.py" in (REPOSITORY_ROOT / "docs/detailed_design/auth/00_strategy_base.md").read_text(
		encoding="utf-8"
	)
