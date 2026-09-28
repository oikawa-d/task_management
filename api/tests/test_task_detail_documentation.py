"""タスク詳細モーダルの詳細設計書のリンク切れ有無、記載必須事項の網羅、
および廃止済み機能の記述が残っていないことを検証するテスト。
"""

import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TASK_DETAIL_DOCUMENT = REPOSITORY_ROOT / "docs/detailed_design/screen/08_task_detail_modal.md"
MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)#]+)(?:#[^)]+)?\)")


def _read_document() -> str:
	"""タスク詳細モーダル設計書の全文をUTF-8で読み込むヘルパー関数。

	Returns:
		str: 設計書の全文。
	"""
	return TASK_DETAIL_DOCUMENT.read_text(encoding="utf-8")


def test_task_detail_document_local_links_resolve() -> None:
	"""設計書中のMarkdownリンク（外部URL・mailto:を除く）が指すローカルファイルが、
	すべて実際に存在することを検証する。
	"""
	text = _read_document()
	missing_links: list[str] = []

	for target in MARKDOWN_LINK_PATTERN.findall(text):
		if target.startswith(("http://", "https://", "mailto:")):
			continue
		if not (TASK_DETAIL_DOCUMENT.parent / target).resolve().is_file():
			missing_links.append(target)

	assert missing_links == []


def test_task_detail_document_declares_singleton_state_contract() -> None:
	"""設計書に、singleton状態管理（`taskDetailStore`）に関する決定事項・関連ファイルパス・
	404時の挙動・テスト設計節など、必須項目が漏れなく記載されていることを検証する。
	"""
	text = _read_document()
	required_items = (
		"状態管理方針（Issue #246）",
		"TanStack Queryではなく`taskDetailStore`（singleton）を正とする",
		"`subscribe`/`getSnapshot`",
		"`boardRefreshToken`",
		"`frontend/src/features/board/components/TaskDetailModal.tsx`",
		"`frontend/src/features/task-detail/components/TaskEditForm.tsx`",
		"`frontend/src/features/task-detail/hooks/useTaskDetail.ts`",
		"`frontend/src/stores/taskDetailStore.ts`",
		"`frontend/src/lib/api/taskDetail.ts`",
		"task 404とcomments 404はどちらも`notFound=true`、`closeRequested=false`",
		"## 14. テスト設計",
	)

	missing_items = [item for item in required_items if item not in text]
	assert missing_items == []


def test_task_detail_document_has_no_obsolete_feature_ownership() -> None:
	"""設計書に、board側へ移設済みの旧コメントコンポーネントパスやTanStack Query由来の
	`queryKey`・`mutationKey`、廃止済みフックの記述が残っていないことを検証する。
	"""
	text = _read_document()

	assert "frontend/src/features/board/components/CommentList.tsx" not in text
	assert "frontend/src/features/board/components/CommentForm.tsx" not in text
	assert "queryKey" not in text
	assert "mutationKey" not in text
	assert "useUpdateTaskField" not in text
	assert "useComments" not in text
