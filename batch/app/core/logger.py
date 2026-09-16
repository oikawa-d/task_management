import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any


class JsonFormatter(logging.Formatter):
	def format(self, record: logging.LogRecord) -> str:
		payload: dict[str, Any] = {
			"timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
			"level": record.levelname,
			"logger": record.name,
			"message": record.getMessage(),
		}
		if record.exc_info:
			payload["exc_info"] = self.formatException(record.exc_info)
		return json.dumps(payload, ensure_ascii=False)


def configure_logging(log_level: str) -> None:
	root_logger = logging.getLogger()
	root_logger.setLevel(log_level.upper())
	root_logger.handlers.clear()

	handler = logging.StreamHandler(sys.stdout)
	handler.setFormatter(JsonFormatter())
	root_logger.addHandler(handler)
