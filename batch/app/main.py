import logging
import signal
import time
from types import FrameType

from app.core.config import get_batch_settings
from app.core.logger import configure_logging

logger = logging.getLogger("app.main")


def _handle_shutdown(signum: int, frame: FrameType | None) -> None:
	raise SystemExit(0)


def main() -> None:
	settings = get_batch_settings()
	configure_logging(settings.log_level)
	logger.info("batch process starting")

	signal.signal(signal.SIGTERM, _handle_shutdown)
	signal.signal(signal.SIGINT, _handle_shutdown)
	while True:
		time.sleep(3600)


if __name__ == "__main__":
	main()
