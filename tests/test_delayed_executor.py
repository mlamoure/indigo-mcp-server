"""
DelayedExecutor: plugin-side timers behind the MCP execute delay parameters.
"""

import sys
import threading
import time
from pathlib import Path
from unittest.mock import Mock

plugin_path = Path(__file__).parent.parent / "MCP Server.indigoPlugin/Contents/Server Plugin"
sys.path.insert(0, str(plugin_path))

from mcp_server.common.delayed_executor import DelayedExecutor  # noqa: E402


def wait_for(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_fires_after_delay_and_logs_activity():
    logger = Mock()
    fired = threading.Event()
    executor = DelayedExecutor(logger=logger)

    job_id = executor.schedule(0.05, fired.set, "Action group 1")

    assert isinstance(job_id, str) and job_id
    assert executor.pending_count() == 1
    assert fired.wait(2.0)
    assert wait_for(lambda: logger.info.called)
    assert "Action group 1 executed (scheduled 0.05s ago)" in logger.info.call_args[0][0]
    assert executor.pending_count() == 0


def test_cancel_prevents_firing():
    fired = threading.Event()
    executor = DelayedExecutor(logger=Mock())

    job_id = executor.schedule(0.2, fired.set, "schedule 2")

    assert executor.cancel(job_id) is True
    assert executor.pending_count() == 0
    assert not fired.wait(0.4)
    assert executor.cancel(job_id) is False  # already gone


def test_cancel_all_clears_pending():
    executor = DelayedExecutor(logger=Mock())
    executor.schedule(5, lambda: None, "a")
    executor.schedule(5, lambda: None, "b")

    assert executor.cancel_all() == 2
    assert executor.pending_count() == 0
    assert executor.cancel_all() == 0


def test_exception_in_callable_is_logged_not_raised():
    logger = Mock()
    ran = threading.Event()
    executor = DelayedExecutor(logger=logger)

    def boom():
        ran.set()
        raise RuntimeError("boom")

    executor.schedule(0.05, boom, "schedule 3")

    assert ran.wait(2.0)
    assert wait_for(lambda: logger.error.called)
    line = logger.error.call_args[0][0]
    assert "schedule 3" in line and "boom" in line
    logger.info.assert_not_called()
