"""構造化（JSON）ログのフォーマッタとロギング初期化処理を提供するモジュール。"""

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
	"identifier",
	"login_method",
	"auth_mode",
	"success",
	"failure_reason",
	"deleted_session_count",
	"deleted_refresh_count",
	"actor_user_id",
	"target_user_id",
	"new_role",
	"old_role",
	"result",
	"old_is_active",
	"new_is_active",
	"session_revoked_count",
	"refresh_revoked_count",
	"project_id",
	"owner_id",
	"member_count",
	"task_count_todo",
	"task_count_in_progress",
	"task_count_done",
	"mode",
	"access_token_revocation_delay_seconds",
)

_JSON_HANDLER_MARKER = "_cerberus_json_handler"


class JsonFormatter(logging.Formatter):
	"""ログレコードを1行のJSON文字列へ整形する`logging.Formatter`実装。

	監査・可観測性のために許可された属性（`_SAFE_AUDIT_FIELDS`）のみを出力し、
	想定外の値の混入を防ぐ。
	"""

	def format(self, record: logging.LogRecord) -> str:
		"""ログレコードをJSON文字列へ変換する。

		タイムスタンプ・レベル・ロガー名・メッセージに加え、例外情報（あれば）と
		`_SAFE_AUDIT_FIELDS`に含まれる属性のうち文字列・真偽値・整数のものだけを含める。

		Args:
			record: 整形対象のログレコード。

		Returns:
			1行のJSON文字列。
		"""
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
			if isinstance(value, (str, bool)) or (isinstance(value, int) and not isinstance(value, bool)):
				payload[field] = value
		return json.dumps(payload, ensure_ascii=False)


def configure_logging(log_level: str) -> None:
	"""ルートロガーにJSON整形のストリームハンドラを設定する。

	アプリ起動時に一度だけ呼ばれる想定だが、再呼び出し時は前回このモジュールが
	追加したハンドラ（`_JSON_HANDLER_MARKER`の目印を持つもの）だけを取り除いてから
	付け直すことで、ハンドラの重複登録を防ぐ。

	Args:
		log_level: 設定するログレベル文字列（例: "INFO"）。大文字小文字は問わない。
	"""
	root_logger = logging.getLogger()
	root_logger.setLevel(log_level.upper())
	for handler in root_logger.handlers[:]:
		if getattr(handler, _JSON_HANDLER_MARKER, False):
			root_logger.removeHandler(handler)

	handler = logging.StreamHandler(sys.stdout)
	handler.setFormatter(JsonFormatter())
	setattr(handler, _JSON_HANDLER_MARKER, True)
	root_logger.addHandler(handler)
