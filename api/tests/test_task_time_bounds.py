from datetime import UTC, datetime

from app.repository.task_repository import _app_day_bounds_utc


def test_app_day_bounds_are_utc_for_tokyo_date() -> None:
	start, end = _app_day_bounds_utc(datetime(2026, 9, 8, 15, 30, tzinfo=UTC), "Asia/Tokyo")

	assert start == datetime(2026, 9, 8, 15, tzinfo=UTC)
	assert end == datetime(2026, 9, 9, 15, tzinfo=UTC)


def test_app_day_bounds_handle_dst_timezone() -> None:
	start, end = _app_day_bounds_utc(datetime(2026, 7, 1, 16, tzinfo=UTC), "America/New_York")

	assert start == datetime(2026, 7, 1, 4, tzinfo=UTC)
	assert end == datetime(2026, 7, 2, 4, tzinfo=UTC)
