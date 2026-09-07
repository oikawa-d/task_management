import signal
import time
from types import FrameType


def _handle_shutdown(signum: int, frame: FrameType | None) -> None:
	raise SystemExit(0)


def main() -> None:
	signal.signal(signal.SIGTERM, _handle_shutdown)
	signal.signal(signal.SIGINT, _handle_shutdown)
	while True:
		time.sleep(3600)


if __name__ == "__main__":
	main()
