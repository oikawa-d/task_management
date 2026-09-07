import json
import logging

from app.core.logger import JsonFormatter, configure_logging


def test_json_formatter_produces_structured_log() -> None:
	formatter = JsonFormatter()
	record = logging.LogRecord(
		name="app.test",
		level=logging.INFO,
		pathname=__file__,
		lineno=1,
		msg="hello %s",
		args=("world",),
		exc_info=None,
	)

	output = json.loads(formatter.format(record))

	assert output["level"] == "INFO"
	assert output["logger"] == "app.test"
	assert output["message"] == "hello world"
	assert "timestamp" in output


def test_json_formatter_includes_request_id_when_present() -> None:
	formatter = JsonFormatter()
	record = logging.LogRecord(
		name="app.test",
		level=logging.WARNING,
		pathname=__file__,
		lineno=1,
		msg="degraded",
		args=(),
		exc_info=None,
	)
	record.request_id = "req-123"

	output = json.loads(formatter.format(record))

	assert output["request_id"] == "req-123"


def test_configure_logging_sets_level_and_json_handler() -> None:
	configure_logging("WARNING")

	root_logger = logging.getLogger()

	assert root_logger.level == logging.WARNING
	assert len(root_logger.handlers) == 1
	assert isinstance(root_logger.handlers[0].formatter, JsonFormatter)
