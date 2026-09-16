from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TASK_DETAIL_DOCUMENT = REPOSITORY_ROOT / "docs/detailed_design/screen/08_task_detail_modal.md"


def test_task_detail_design_records_singleton_state_decision() -> None:
	text = TASK_DETAIL_DOCUMENT.read_text(encoding="utf-8")

	assert "TanStack Queryではなく`taskDetailStore`（singleton）を正とする" in text
	assert "boardRefreshToken" in text
	assert "useSyncExternalStore" in text


def test_task_detail_design_separates_board_and_detail_responsibilities() -> None:
	text = TASK_DETAIL_DOCUMENT.read_text(encoding="utf-8")

	assert "同じ責務のファイルを`features/board`と`features/task-detail`の双方に作成しない" in text
	assert "frontend/src/features/board/BoardPage.tsx" in text
	assert "frontend/src/features/task-detail/hooks/useTaskDetail.ts" in text
	assert "自動navigateはせず" in text
