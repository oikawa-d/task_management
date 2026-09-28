"""タスク詳細モーダルの詳細設計書`docs/detailed_design/screen/08_task_detail_modal.md`が、
状態管理方式の決定事項と画面間の責務分離方針を記載し続けていることを検証するテスト。
"""

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TASK_DETAIL_DOCUMENT = REPOSITORY_ROOT / "docs/detailed_design/screen/08_task_detail_modal.md"


def test_task_detail_design_records_singleton_state_decision() -> None:
	"""設計書が、状態管理にTanStack Queryではなくsingletonの`taskDetailStore`を正とする決定と、
	`boardRefreshToken`・`useSyncExternalStore`によるボード再取得連携の記載を保持していることを検証する。
	"""
	text = TASK_DETAIL_DOCUMENT.read_text(encoding="utf-8")

	assert "TanStack Queryではなく`taskDetailStore`（singleton）を正とする" in text
	assert "boardRefreshToken" in text
	assert "useSyncExternalStore" in text


def test_task_detail_design_separates_board_and_detail_responsibilities() -> None:
	"""設計書が、`features/board`と`features/task-detail`へ同一責務のファイルを重複作成しない方針と、
	`BoardPage.tsx`・`useTaskDetail.ts`の具体パス、および詳細表示時に自動navigateしない仕様の
	記載を保持していることを検証する。
	"""
	text = TASK_DETAIL_DOCUMENT.read_text(encoding="utf-8")

	assert "同じ責務のファイルを`features/board`と`features/task-detail`の双方に作成しない" in text
	assert "frontend/src/features/board/BoardPage.tsx" in text
	assert "frontend/src/features/task-detail/hooks/useTaskDetail.ts" in text
	assert "自動navigateはせず" in text
