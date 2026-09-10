import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

_SAFE_AUDIT_FIELDS = (
	"operation",
	"event",
	"route",
	"scope",
	"limit",
	"window",
	"client_ip",
	"proxy_peer_ip",
	"ip_source",
	"request_id",
	"user_id",
	"login_method",
	"deleted_session_count",
	"deleted_refresh_count",
)


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
		for field in _SAFE_AUDIT_FIELDS:
			value = getattr(record, field, None)
			if isinstance(value, str) or (isinstance(value, int) and not isinstance(value, bool)):
				payload[field] = value
		return json.dumps(payload, ensure_ascii=False)


def configure_logging(log_level: str) -> None:
	root_logger = logging.getLogger()
	root_logger.setLevel(log_level.upper())
	root_logger.handlers.clear()

	handler = logging.StreamHandler(sys.stdout)
	handler.setFormatter(JsonFormatter())
	root_logger.addHandler(handler)
