import re
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TASK_DETAIL_DOCUMENT = REPOSITORY_ROOT / "docs/detailed_design/screen/08_task_detail_modal.md"
MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)#]+)(?:#[^)]+)?\)")


def _read_document() -> str:
	return TASK_DETAIL_DOCUMENT.read_text(encoding="utf-8")


def test_task_detail_document_local_links_resolve() -> None:
	text = _read_document()
	missing_links: list[str] = []

	for target in MARKDOWN_LINK_PATTERN.findall(text):
		if target.startswith(("http://", "https://", "mailto:")):
			continue
		if not (TASK_DETAIL_DOCUMENT.parent / target).resolve().is_file():
			missing_links.append(target)

	assert missing_links == []


def test_task_detail_document_declares_singleton_state_contract() -> None:
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
	text = _read_document()

	assert "frontend/src/features/board/components/CommentList.tsx" not in text
	assert "frontend/src/features/board/components/CommentForm.tsx" not in text
	assert "queryKey" not in text
	assert "mutationKey" not in text
	assert "useUpdateTaskField" not in text
	assert "useComments" not in text
