"""batch常駐スケジューラの起動エントリポイント。

`main()`がプロセスの起点で、ログ設定・設定読み込みののち`asyncio.run`で
`async_main`を実行する。`async_main`はDBエンジン・Redisクライアントを初期化し、
`--run-once`が指定されない限り`build_scheduler`で構築したAPSchedulerの
`AsyncIOScheduler`を起動してSIGTERM/SIGINTを待ち受ける。

登録されるジョブは現時点で期限通知ジョブ（`run_due_notification_job`）のみで、
`BatchSettings.notify_due_run_hours`（例: "10,17"）に列挙された各時刻に対して
`BatchSettings.notify_due_cron_minute`分に実行するcronトリガーを1つずつ
`due_notification_{hour}`というジョブIDで登録する（`build_scheduler`参照）。
`BatchSettings.batch_enabled`が`False`の場合はジョブを登録しないスケジューラを返す。
"""

import argparse
import asyncio
import logging
import signal
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from importlib import import_module
from types import FrameType
from typing import Any, cast
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]
from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]

from app.core.config import BatchSettings, get_batch_settings
from app.core.logger import configure_logging
from app.db import dispose_db_engine, get_db_engine
from app.redis_client import close_redis_client, get_redis_client

logger = logging.getLogger("app.main")
JobRunner = Callable[..., Awaitable[Any]]


def _parse_hour(value: str) -> int:
	"""コマンドライン引数`--slot`の時刻文字列を0-23の整数に変換する。

	Args:
		value: `argparse`から渡される時刻文字列。

	Returns:
		変換後の時刻（0以上23以下の整数）。

	Raises:
		argparse.ArgumentTypeError: 整数変換に失敗した場合、または0-23の範囲外の場合。
	"""
	try:
		hour = int(value)
	except ValueError as exc:
		raise argparse.ArgumentTypeError("時刻は整数で指定してください") from exc
	if not 0 <= hour <= 23:
		raise argparse.ArgumentTypeError("時刻は0から23の範囲で指定してください")
	return hour


def _parse_run_hours(value: str) -> list[int]:
	"""`NOTIFY_DUE_RUN_HOURS`（カンマ区切りの時刻文字列）を時刻のリストへ変換する。

	Args:
		value: カンマ区切りの時刻文字列（例: "10,17"）。

	Returns:
		指定順を保った時刻（0以上23以下の整数）のリスト。

	Raises:
		ValueError: 空要素・範囲外の値・重複した時刻が含まれる場合。
	"""
	hours: list[int] = []
	for raw_hour in value.split(","):
		if not raw_hour.strip():
			raise ValueError("NOTIFY_DUE_RUN_HOURSに空の時刻は指定できません")
		hour = int(raw_hour.strip())
		if not 0 <= hour <= 23:
			raise ValueError("NOTIFY_DUE_RUN_HOURSは0から23の範囲で指定してください")
		if hour in hours:
			raise ValueError("NOTIFY_DUE_RUN_HOURSに同じ時刻を重複指定できません")
		hours.append(hour)
	return hours


async def run_due_notification_job(*, slot: int, settings: BatchSettings | None = None) -> Any:
	"""期限通知ジョブを遅延importして実行するスケジューラ境界。

	`app.jobs.due_notification_job`をモジュールロード時ではなく呼び出し時に
	importすることで、スケジューラ構築時点ではジョブ本体への依存を持たせない。

	Args:
		slot: 実行対象の時刻スロット（0-23時）。通知の重複排除キーにも使われる。
		settings: 使用するbatch設定。省略時は`get_batch_settings()`で取得する。

	Returns:
		`app.jobs.due_notification_job.run_due_notification_job`の戻り値。

	Raises:
		ModuleNotFoundError: `app.jobs.due_notification_job`が存在しない場合。
	"""
	settings = settings or get_batch_settings()
	module = import_module("app.jobs.due_notification_job")
	job = cast(JobRunner, getattr(module, "run_due_notification_job"))
	now = datetime.now(ZoneInfo(settings.app_timezone))
	return await job(now=now, settings=settings, notification_slot=str(slot))


def build_scheduler(settings: BatchSettings) -> AsyncIOScheduler:
	"""期限通知ジョブを登録したAPSchedulerのスケジューラを構築する。

	`settings.app_timezone`のタイムゾーンでスケジューラを生成し、
	`settings.batch_enabled`が`False`の場合はジョブを登録せずに返す
	（呼び出し元でスケジューラをstartしない運用と組み合わせて全ジョブを無効化する）。
	有効な場合は`settings.notify_due_run_hours`（カンマ区切りの時刻）をパースし、
	各時刻ごとに`settings.notify_due_cron_minute`分に発火するcronトリガーで
	`run_due_notification_job`を`due_notification_{hour}`というジョブIDで登録する。
	`coalesce=True`・`max_instances=1`により、遅延時の多重発火や同時多重実行を防ぐ。

	Args:
		settings: ジョブ登録・タイムゾーン決定に使うbatch設定。

	Returns:
		ジョブ登録済み（または`batch_enabled=False`時は未登録）の`AsyncIOScheduler`。

	Raises:
		ValueError: `notify_due_run_hours`の形式が不正な場合。
	"""
	timezone = ZoneInfo(settings.app_timezone)
	scheduler = AsyncIOScheduler(timezone=timezone)
	if not settings.batch_enabled:
		return scheduler

	for hour in _parse_run_hours(settings.notify_due_run_hours):
		scheduler.add_job(
			run_due_notification_job,
			trigger=CronTrigger(
				hour=hour,
				minute=settings.notify_due_cron_minute,
				timezone=timezone,
			),
			id=f"due_notification_{hour}",
			kwargs={"slot": hour},
			coalesce=True,
			max_instances=1,
		)
	return scheduler


def handle_sigterm(_scheduler: AsyncIOScheduler, shutdown_event: asyncio.Event) -> None:
	"""SIGTERM/SIGINT受信時に、待機中のシャットダウンイベントへ通知する。

	スケジューラ自体の停止処理は`async_main`の`finally`節で行うため、
	ここではイベントをセットして`async_main`側の待機を解除するのみ。

	Args:
		_scheduler: 現在未使用（将来のシグナルハンドリング拡張のため引数として保持）。
		shutdown_event: セットすることでプロセスの終了処理を開始させるイベント。
	"""
	shutdown_event.set()


async def async_main(args: argparse.Namespace, settings: BatchSettings | None = None) -> None:
	"""batchプロセス本体の非同期処理。リソース初期化からシャットダウンまでを行う。

	`--run-once`指定時またはスケジュール実行が有効な場合にDBエンジン・Redis
	クライアントを初期化し、SIGTERM/SIGINTハンドラを登録する。`--run-once`が
	指定されていれば期限通知ジョブを1回だけ実行して終了し、そうでなければ
	`build_scheduler`で構築したスケジューラを起動してシャットダウンイベントを待つ。
	`finally`節でスケジューラ停止・Redis切断・DBエンジン破棄を行い、
	初期化した分だけ確実に後始末する。

	Args:
		args: `_parse_args`で解析済みのコマンドライン引数（`run_once`・`slot`を含む）。
		settings: 使用するbatch設定。省略時は`get_batch_settings()`で取得する。

	Raises:
		ValueError: `--run-once`指定時に`--slot`が指定されていない場合。
	"""
	settings = settings or get_batch_settings()
	needs_resources = bool(args.run_once or settings.batch_enabled)
	db_initialized = False
	redis_initialized = False
	scheduler: AsyncIOScheduler | None = None
	try:
		if needs_resources:
			get_db_engine()
			db_initialized = True
			get_redis_client(settings)
			redis_initialized = True

		shutdown_event = asyncio.Event()
		scheduler = build_scheduler(settings) if not args.run_once else None

		def on_signal(signum: int, frame: FrameType | None) -> None:
			if scheduler is not None:
				handle_sigterm(scheduler, shutdown_event)

		signal.signal(signal.SIGTERM, on_signal)
		signal.signal(signal.SIGINT, on_signal)
		if args.run_once:
			if args.slot is None:
				raise ValueError("--run-onceには--slotが必要です")
			await run_due_notification_job(slot=args.slot, settings=settings)
			return
		if settings.batch_enabled and scheduler is not None:
			scheduler.start()
			logger.info("batch scheduler started")
		else:
			logger.info("BATCH_ENABLED=false; scheduled jobs are disabled")
		await shutdown_event.wait()
	finally:
		if scheduler is not None and scheduler.running:
			scheduler.shutdown(wait=True)
		if redis_initialized:
			await close_redis_client()
		if db_initialized:
			await dispose_db_engine()


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
	"""batchプロセスのコマンドライン引数を解析する。

	`--run-once`と`--slot`は同時指定が必須の組であり、片方のみの指定はエラーとする。

	Args:
		argv: 解析対象の引数列。省略時は`sys.argv`から取得される。

	Returns:
		解析済みの`argparse.Namespace`（`run_once`・`slot`属性を持つ）。

	Raises:
		SystemExit: 引数解析エラー、または`--run-once`と`--slot`の組み合わせが不正な場合
			（`argparse.ArgumentParser.error`によりexit code 2で終了する）。
	"""
	parser = argparse.ArgumentParser(description="常駐batchスケジューラ")
	parser.add_argument("--run-once", choices=("due_notification",))
	parser.add_argument("--slot", type=_parse_hour)
	args = parser.parse_args(argv)
	if args.run_once and args.slot is None:
		parser.error("--run-onceには--slotが必要です")
	if args.slot is not None and not args.run_once:
		parser.error("--slotは--run-onceと同時に指定してください")
	return args


def main(argv: Sequence[str] | None = None) -> None:
	"""batch常駐スケジューラのエントリポイント。

	コマンドライン引数を解析し、ログ設定を適用したうえで`async_main`を
	`asyncio.run`で実行する。プロセスの起動から終了までをこの関数が担う。

	Args:
		argv: `_parse_args`へ渡す引数列。省略時は`sys.argv`が使われる。
	"""
	args = _parse_args(argv)
	settings = get_batch_settings()
	configure_logging(settings.log_level)
	logger.info("batch process starting")
	asyncio.run(async_main(args, settings))


if __name__ == "__main__":
	main()
