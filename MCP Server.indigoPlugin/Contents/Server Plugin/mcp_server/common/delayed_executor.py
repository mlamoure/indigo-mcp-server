"""
Plugin-side delayed execution for the MCP execute commands.

Indigo's IOM has no delayed variant of trigger/schedule/actionGroup.execute()
— only device commands and enable/disable accept delay/duration — so the MCP
Server emulates the `delay` / `delay_seconds` tool parameters here with
threading.Timer. These timers live in the plugin process only: a pending run
never appears in Indigo's UI or event log, cannot be cancelled with
remove_delayed_actions, and is lost if the plugin restarts.
"""

import logging
import threading
import uuid
from typing import Callable, Dict, Optional

from . import log_style


class DelayedExecutor:
    """Run callables after a delay on daemon timers; cancellable by job id."""

    def __init__(self, logger: Optional[logging.Logger] = None):
        self._logger = logger or logging.getLogger("Plugin")
        self._timers: Dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def schedule(self, seconds: float, fn: Callable[[], None], label: str) -> str:
        """
        Run `fn` after `seconds`. Returns a job id usable with cancel().

        `label` names the work in the log lines, e.g. "Action group 123".
        """
        job_id = uuid.uuid4().hex

        def _fire():
            with self._lock:
                self._timers.pop(job_id, None)
            try:
                fn()
                log_style.activity(
                    self._logger, f"{label} executed (scheduled {seconds}s ago)"
                )
            except Exception as exc:
                log_style.fail(self._logger, f"{label} (delayed {seconds}s)", exc)

        timer = threading.Timer(seconds, _fire)
        timer.daemon = True
        with self._lock:
            self._timers[job_id] = timer
            timer.start()
        self._logger.debug(f"Scheduled {label} in {seconds}s (job {job_id})")
        return job_id

    def cancel(self, job_id: str) -> bool:
        """Cancel a pending job. Returns False if it already fired or is unknown."""
        with self._lock:
            timer = self._timers.pop(job_id, None)
        if timer is None:
            return False
        timer.cancel()
        self._logger.debug(f"Cancelled delayed job {job_id}")
        return True

    def cancel_all(self) -> int:
        """Cancel every pending job (plugin shutdown). Returns how many were pending."""
        with self._lock:
            timers = list(self._timers.values())
            self._timers.clear()
        for timer in timers:
            timer.cancel()
        if timers:
            self._logger.debug(f"Cancelled {len(timers)} pending delayed job(s)")
        return len(timers)

    def pending_count(self) -> int:
        """Number of jobs still waiting to fire."""
        with self._lock:
            return len(self._timers)
