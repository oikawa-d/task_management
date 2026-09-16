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
		msg="job started",
		args=(),
		exc_info=None,
	)

	output = json.loads(formatter.format(record))

	assert output["level"] == "INFO"
	assert output["message"] == "job started"


def test_configure_logging_sets_level_and_json_handler() -> None:
	configure_logging("ERROR")

	root_logger = logging.getLogger()

	assert root_logger.level == logging.ERROR
	assert isinstance(root_logger.handlers[0].formatter, JsonFormatter)
