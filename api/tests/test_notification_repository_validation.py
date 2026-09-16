import pytest
from app.repository.notification_repository import validate_page_window


@pytest.mark.parametrize("limit", [0, -1])
def test_validate_page_window_rejects_non_positive_limit(limit: int) -> None:
	with pytest.raises(ValueError, match="limit"):
		validate_page_window(limit, 0)


def test_validate_page_window_rejects_negative_offset() -> None:
	with pytest.raises(ValueError, match="offset"):
		validate_page_window(20, -1)


def test_validate_page_window_accepts_first_and_later_pages() -> None:
	validate_page_window(20, 0)
	validate_page_window(20, 40)
