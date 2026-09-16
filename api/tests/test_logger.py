import ast
import json
import logging
from pathlib import Path

import pytest
from app.core.logger import _SAFE_AUDIT_FIELDS, JsonFormatter, configure_logging


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


def test_json_formatter_includes_force_logout_fields() -> None:
	formatter = JsonFormatter()
	record = logging.LogRecord(
		name="app.audit",
		level=logging.INFO,
		pathname=__file__,
		lineno=1,
		msg="admin forced logout",
		args=(),
		exc_info=None,
	)
	record.actor_user_id = "actor-123"
	record.target_user_id = "target-123"
	record.mode = "jwt"
	record.access_token_revocation_delay_seconds = 900
	record.code = "secret-code"
	record.email = "alice@example.com"

	output = json.loads(formatter.format(record))

	assert output["actor_user_id"] == "actor-123"
	assert output["target_user_id"] == "target-123"
	assert output["mode"] == "jwt"
	assert output["access_token_revocation_delay_seconds"] == 900
	assert "code" not in output
	assert "email" not in output


def _find_unknown_extra_keys(source: str, filename: str, allowed: set[str]) -> list[str]:
	tree = ast.parse(source, filename=filename)
	log_methods = {"debug", "info", "warning", "error", "exception", "critical", "log"}
	unknown: list[str] = []

	for node in ast.walk(tree):
		if not isinstance(node, ast.Call):
			continue
		for keyword in node.keywords:
			if keyword.arg != "extra" or not isinstance(node.func, ast.Attribute) or node.func.attr not in log_methods:
				continue
			if not isinstance(keyword.value, ast.Dict):
				unknown.append(f"{filename}:{keyword.value.lineno}:dynamic extra mapping")
				continue
			for key in keyword.value.keys:
				if key is None:
					unknown.append(f"{filename}:{keyword.value.lineno}:dynamic extra mapping")
				elif not isinstance(key, ast.Constant) or not isinstance(key.value, str) or key.value not in allowed:
					key_name = "dynamic extra key" if not isinstance(key, ast.Constant) else repr(key.value)
					unknown.append(f"{filename}:{key.lineno}:{key_name}")
	return unknown


def test_all_structured_log_extra_keys_are_allowlisted() -> None:
	app_root = Path(__file__).resolve().parent.parent / "app"
	allowed = set(_SAFE_AUDIT_FIELDS)
	unknown: list[str] = []

	for path in app_root.rglob("*.py"):
		unknown.extend(_find_unknown_extra_keys(path.read_text(), str(path), allowed))

	assert unknown == []


@pytest.mark.parametrize(
	("extra", "expected_fragment"),
	[
		("{dynamic_key: value}", "dynamic extra key"),
		("{1: value}", ":1"),
		("{**mapping}", "dynamic extra mapping"),
	],
)
def test_extra_key_scanner_rejects_non_allowlisted_keys(extra: str, expected_fragment: str) -> None:
	unknown = _find_unknown_extra_keys(
		f'logger.info("message", extra={extra})',
		"<test>",
		{"operation"},
	)

	assert len(unknown) == 1
	assert expected_fragment in unknown[0]


def test_configure_logging_sets_level_and_json_handler() -> None:
	configure_logging("WARNING")

	root_logger = logging.getLogger()

	assert root_logger.level == logging.WARNING
	json_handlers = [handler for handler in root_logger.handlers if isinstance(handler.formatter, JsonFormatter)]
	assert len(json_handlers) == 1


def test_configure_logging_preserves_existing_handlers() -> None:
	root_logger = logging.getLogger()
	existing_handler = logging.NullHandler()
	root_logger.addHandler(existing_handler)

	try:
		configure_logging("INFO")

		assert existing_handler in root_logger.handlers
	finally:
		root_logger.removeHandler(existing_handler)


def test_json_formatter_emits_failure_reason_and_drops_unlisted_keys() -> None:
	formatter = JsonFormatter()
	record = logging.LogRecord(
		name="app.oauth",
		level=logging.WARNING,
		pathname=__file__,
		lineno=1,
		msg="OAuth callback failed",
		args=(),
		exc_info=None,
	)
	record.operation = "oauth_callback"
	record.event = "oauth_callback_failed"
	record.failure_reason = "InvalidStateError"
	# _SAFE_AUDIT_FIELDSに無いキーはフォーマッタ通過時に落ちる。
	record.error = "InvalidStateError"

	output = json.loads(formatter.format(record))

	assert output["failure_reason"] == "InvalidStateError"
	assert "error" not in output
