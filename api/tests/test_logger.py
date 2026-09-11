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


def test_json_formatter_includes_safe_oauth_fields_only() -> None:
	formatter = JsonFormatter()
	record = logging.LogRecord(
		name="app.oauth",
		level=logging.WARNING,
		pathname=__file__,
		lineno=1,
		msg="OAuth operation failed",
		args=(),
		exc_info=None,
	)
	record.operation = "token_exchange"
	record.event = "oauth_failure"
	record.route = "/api/auth/oauth/google/callback"
	record.scope = "oauth_callback"
	record.limit = 10
	record.window = 900
	record.client_ip = "198.51.100.4"
	record.proxy_peer_ip = "10.0.0.1"
	record.ip_source = "trusted_xff"
	record.request_id = "request-123"
	record.user_id = "user-123"
	record.identifier = "alice@example.com"
	record.login_method = "oauth_google"
	record.auth_mode = "jwt"
	record.success = True
	record.failure_reason = None
	record.deleted_session_count = 1
	record.deleted_refresh_count = 0
	record.code = "secret-code"
	record.email = "alice@example.com"

	output = json.loads(formatter.format(record))

	assert output["operation"] == "token_exchange"
	assert output["event"] == "oauth_failure"
	assert output["route"] == "/api/auth/oauth/google/callback"
	assert output["client_ip"] == "198.51.100.4"
	assert output["deleted_session_count"] == 1
	assert output["identifier"] == "alice@example.com"
	assert output["auth_mode"] == "jwt"
	assert output["success"] is True
	assert "failure_reason" not in output
	assert "code" not in output
	assert "email" not in output


def test_configure_logging_sets_level_and_json_handler() -> None:
	configure_logging("WARNING")

	root_logger = logging.getLogger()

	assert root_logger.level == logging.WARNING
	assert len(root_logger.handlers) == 1
	assert isinstance(root_logger.handlers[0].formatter, JsonFormatter)
