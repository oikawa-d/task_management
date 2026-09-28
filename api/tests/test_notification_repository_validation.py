"""通知一覧取得のページ範囲検証`validate_page_window`のテスト。"""

import pytest
from app.repository.notification_repository import validate_page_window


@pytest.mark.parametrize("limit", [0, -1])
def test_validate_page_window_rejects_non_positive_limit(limit: int) -> None:
	"""limitが0または負の場合に、"limit"を含むメッセージのValueErrorが送出されることを検証する。"""
	with pytest.raises(ValueError, match="limit"):
		validate_page_window(limit, 0)


def test_validate_page_window_rejects_negative_offset() -> None:
	"""offsetが負の場合に、"offset"を含むメッセージのValueErrorが送出されることを検証する。"""
	with pytest.raises(ValueError, match="offset"):
		validate_page_window(20, -1)


def test_validate_page_window_accepts_first_and_later_pages() -> None:
	"""limitが正でoffsetが0または正のとき、1ページ目・後続ページのいずれも例外を送出せず通過することを検証する。"""
	validate_page_window(20, 0)
	validate_page_window(20, 40)
