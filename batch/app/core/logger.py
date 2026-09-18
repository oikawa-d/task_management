"""batchプロセスのログ出力設定を行うモジュール。

標準出力へJSON形式でログを出力するフォーマッタと、
ルートロガーへその設定を適用する初期化関数を提供する。
"""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any


class JsonFormatter(logging.Formatter):
	"""ログレコードをJSON文字列へ整形するフォーマッタ。

	コンテナ環境でのログ収集・解析を想定し、標準出力へ構造化ログを流すために使う。
	"""

	def format(self, record: logging.LogRecord) -> str:
		"""ログレコードをJSON文字列に変換する。

		Args:
			record: フォーマット対象のログレコード。

		Returns:
			timestamp・level・logger・messageを含むJSON文字列。
			例外情報がある場合は`exc_info`キーにトレースバック文字列を追加する。
		"""
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
	"""ルートロガーへJSON形式の標準出力ハンドラを設定する。

	既存のハンドラをすべて削除してから標準出力向けの`JsonFormatter`付き
	ハンドラを追加するため、複数回呼び出してもハンドラが重複しない。

	Args:
		log_level: 設定するログレベル文字列（例: "INFO"）。大文字小文字は問わない。

	Raises:
		ValueError: `log_level`が`logging`モジュールで解釈できない値の場合。
	"""
	root_logger = logging.getLogger()
	root_logger.setLevel(log_level.upper())
	root_logger.handlers.clear()

	handler = logging.StreamHandler(sys.stdout)
	handler.setFormatter(JsonFormatter())
	root_logger.addHandler(handler)
