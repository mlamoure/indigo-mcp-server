"""
Lightweight timer queue for duration-based (dwell-time) subscription conditions.

When a subscription has duration_seconds set, the condition must remain matched
for that duration before the webhook fires. If the condition reverts before the
timer expires, the pending webhook is cancelled.

Uses threading.Timer (stdlib). Timers are lost on plugin restart (acceptable).
"""

import logging
import threading
from typing import Any, Callable, Dict, Optional


class DwellTimerQueue:
    """
    Manages pending dwell timers for subscriptions with duration_seconds.

    Each pending dwell is keyed by "{subscription_id}:{entity_id}" to allow
    per-entity timers within a single subscription.
    """

    def __init__(
        self,
        callback: Callable[[Any, Any], None],
        logger: Optional[logging.Logger] = None,
    ):
        """
        Args:
            callback: Called when timer fires — callback(subscription, event).
            logger: Optional logger instance.
        """
        self._callback = callback
        self._logger = logger or logging.getLogger(__name__)
        self._timers: Dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def _make_key(self, subscription_id: str, entity_id: Any) -> str:
        """Build a unique key for a pending dwell timer."""
        return f"{subscription_id}:{entity_id}"

    def start_dwell(
        self,
        subscription: Any,
        event: Any,
        duration_seconds: int,
        entity_id: Any,
    ) -> None:
        """
        Start a dwell timer. When it fires, dispatch the webhook.

        If a timer already exists for this subscription+entity, it is NOT
        restarted (the condition was already matching). A new timer is only
        started on the transition into the matching state.

        Args:
            subscription: The Subscription object.
            event: The Event to dispatch when the timer fires.
            duration_seconds: How long the condition must hold.
            entity_id: The entity ID (for per-entity timer tracking).
        """
        key = self._make_key(subscription.subscription_id, entity_id)

        with self._lock:
            # If timer already pending for this key, don't restart — condition
            # was already matching, let the existing timer continue.
            if key in self._timers:
                return

            def _on_expire():
                with self._lock:
                    self._timers.pop(key, None)
                self._logger.debug(
                    f"Dwell timer expired for {key}, dispatching webhook"
                )
                try:
                    self._callback(subscription, event)
                except Exception:
                    self._logger.exception(
                        f"Dwell timer callback failed for {key}"
                    )

            timer = threading.Timer(duration_seconds, _on_expire)
            timer.daemon = True
            self._timers[key] = timer
            timer.start()

            self._logger.debug(
                f"Dwell timer started: {key} ({duration_seconds}s)"
            )

    def cancel_dwell(self, subscription_id: str, entity_id: Any) -> None:
        """
        Cancel a pending dwell timer (condition reverted before expiry).

        Args:
            subscription_id: The subscription ID.
            entity_id: The entity ID.
        """
        key = self._make_key(subscription_id, entity_id)

        with self._lock:
            timer = self._timers.pop(key, None)

        if timer is not None:
            timer.cancel()
            self._logger.debug(f"Dwell timer cancelled: {key}")

    def cancel_all(self) -> None:
        """Cancel all pending timers. Called on shutdown."""
        with self._lock:
            timers = list(self._timers.values())
            self._timers.clear()

        for timer in timers:
            timer.cancel()

        if timers:
            self._logger.debug(f"Cancelled {len(timers)} pending dwell timers")

    def get_pending_count(self) -> int:
        """Return the number of pending dwell timers."""
        with self._lock:
            return len(self._timers)
