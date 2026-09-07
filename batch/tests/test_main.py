import signal

import pytest
from app.main import _handle_shutdown


def test_handle_shutdown_raises_system_exit() -> None:
	with pytest.raises(SystemExit):
		_handle_shutdown(signal.SIGTERM, None)
