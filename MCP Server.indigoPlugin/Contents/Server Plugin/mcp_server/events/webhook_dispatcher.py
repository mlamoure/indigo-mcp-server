"""
Webhook dispatcher — background HTTP POST delivery with retry.

Receives (subscription, event) pairs from the subscription manager,
queues them, and delivers via a background daemon thread with
exponential backoff retry.

Uses urllib.request (stdlib) — no external dependencies.
"""

import hashlib
import hmac
import json
import logging
import queue
import ssl
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

from .event_model import Event
from .subscription_model import Subscription


class WebhookDispatcher:
    """
    Asynchronous webhook delivery with retry and auth support.

    dispatch() is non-blocking — it enqueues the event and returns
    immediately so Indigo callbacks are never blocked.
    """

    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        timeout: int = 10,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
    ):
        """
        Args:
            logger: Optional logger instance.
            timeout: HTTP request timeout in seconds.
            max_retries: Max retry attempts on failure.
            retry_base_delay: Base delay for exponential backoff (seconds).
        """
        self._logger = logger or logging.getLogger(__name__)
        self._timeout = timeout
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay

        self._queue: queue.Queue[Optional[Tuple[Subscription, Event]]] = queue.Queue()
        self._worker: Optional[threading.Thread] = None
        self._running = False

        # Stats
        self._stats_lock = threading.Lock()
        self._events_sent = 0
        self._events_failed = 0

        # Track which subscription IDs have already had warnings logged, to avoid log spam on repeated deliveries
        self._warned_ssl: set = set()
        self._warned_http: set = set()

    def start(self) -> None:
        """Start the background delivery worker thread."""
        if self._running:
            return

        self._running = True
        self._worker = threading.Thread(
            target=self._delivery_loop, name="webhook-dispatcher", daemon=True
        )
        self._worker.start()
        self._logger.debug("Webhook dispatcher started")

    def stop(self) -> None:
        """Signal the worker to drain the queue and stop."""
        if not self._running:
            return

        self._running = False
        # Send sentinel to unblock the worker
        self._queue.put(None)

        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=10)

        self._logger.debug("Webhook dispatcher stopped")

    def dispatch(self, subscription: Subscription, event: Event) -> None:
        """
        Non-blocking enqueue of an event for delivery.

        Called from Indigo callback threads — must return immediately.
        """
        if not self._running:
            self._logger.debug("Dispatcher not running, dropping event")
            return

        self._queue.put((subscription, event))

    def get_stats(self) -> Dict[str, Any]:
        """Return dispatcher-level delivery stats."""
        with self._stats_lock:
            return {
                "events_sent": self._events_sent,
                "events_failed": self._events_failed,
                "queue_depth": self._queue.qsize(),
                "running": self._running,
            }

    # ------------------------------------------------------------------
    # Background delivery
    # ------------------------------------------------------------------

    def _delivery_loop(self) -> None:
        """Background worker: read from queue, deliver with retry."""
        while self._running:
            try:
                item = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue

            if item is None:
                # Sentinel — drain remaining items then exit
                self._drain_queue()
                break

            subscription, event = item
            self._deliver_with_retry(subscription, event)

    def _drain_queue(self) -> None:
        """Deliver any remaining queued events before shutdown."""
        while not self._queue.empty():
            try:
                item = self._queue.get_nowait()
                if item is not None:
                    subscription, event = item
                    self._deliver_with_retry(subscription, event)
            except queue.Empty:
                break

    def _deliver_with_retry(
        self, subscription: Subscription, event: Event
    ) -> None:
        """Attempt delivery with exponential backoff retry."""
        body = json.dumps(event.to_dict())

        for attempt in range(self._max_retries + 1):
            try:
                status_code = self._post(subscription, body, event)

                if 200 <= status_code < 300:
                    subscription.record_success(status_code)
                    with self._stats_lock:
                        self._events_sent += 1
                    self._logger.debug(
                        f"Webhook delivered: {event.event_id} → "
                        f"{subscription.webhook_url} ({status_code})"
                    )
                    return
                elif status_code >= 500:
                    # Server error — retry
                    subscription.record_failure(
                        f"HTTP {status_code}", http_status=status_code
                    )
                    if attempt < self._max_retries:
                        # Exponential backoff: 1s, 2s, 4s (for base_delay=1.0)
                        delay = self._retry_base_delay * (2 ** attempt)
                        self._logger.debug(
                            f"Webhook {status_code}, retry {attempt + 1} "
                            f"in {delay}s: {event.event_id}"
                        )
                        time.sleep(delay)
                        continue
                else:
                    # Client error (4xx) — don't retry
                    subscription.record_failure(
                        f"HTTP {status_code}", http_status=status_code
                    )
                    self._logger.warning(
                        f"Webhook rejected ({status_code}): {event.event_id} "
                        f"→ {subscription.webhook_url}"
                    )
                    with self._stats_lock:
                        self._events_failed += 1
                    return

            except Exception as e:
                subscription.record_failure(str(e))
                if attempt < self._max_retries:
                    delay = self._retry_base_delay * (2 ** attempt)
                    self._logger.debug(
                        f"Webhook error, retry {attempt + 1} in {delay}s: {e}"
                    )
                    time.sleep(delay)
                    continue

        # All retries exhausted
        self._logger.warning(
            f"Webhook delivery failed after {self._max_retries + 1} attempts: "
            f"{event.event_id} → {subscription.webhook_url}"
        )
        with self._stats_lock:
            self._events_failed += 1

    # ------------------------------------------------------------------
    # HTTP POST
    # ------------------------------------------------------------------

    def _post(
        self, subscription: Subscription, body: str, event: Event
    ) -> int:
        """
        POST the event payload to the subscription's webhook URL.

        Returns the HTTP status code.
        """
        url = subscription.webhook_url

        # Log warnings for insecure configs (once per subscription)
        sub_id = subscription.subscription_id
        if not subscription.verify_ssl and sub_id not in self._warned_ssl:
            self._logger.warning(
                f"Subscription {sub_id}: SSL verification disabled"
            )
            self._warned_ssl.add(sub_id)
        if url.startswith("http://") and sub_id not in self._warned_http:
            self._logger.warning(
                f"Subscription {sub_id}: using plain HTTP (not HTTPS)"
            )
            self._warned_http.add(sub_id)

        # Build headers
        headers = {
            "Content-Type": "application/json",
            "X-Event-Id": event.event_id,
            "X-Event-Type": event.event_type,
            "X-Subscription-Id": subscription.subscription_id,
        }

        # Auth
        body_bytes = body.encode("utf-8")

        if subscription.auth_mode == "bearer" and subscription.auth_token:
            headers["Authorization"] = f"Bearer {subscription.auth_token}"

        elif subscription.auth_mode == "hmac" and subscription.auth_token:
            timestamp = str(int(time.time()))
            signature = hmac.new(
                subscription.auth_token.encode("utf-8"),
                body_bytes,
                hashlib.sha256,
            ).hexdigest()
            headers["X-Webhook-Signature"] = f"sha256={signature}"
            headers["X-Webhook-Timestamp"] = timestamp

        # Build request
        req = urllib.request.Request(
            url, data=body_bytes, headers=headers, method="POST"
        )

        # SSL context
        ssl_context = None
        if url.startswith("https://"):
            if subscription.verify_ssl:
                ssl_context = ssl.create_default_context()
            else:
                ssl_context = ssl._create_unverified_context()

        # Execute
        try:
            response = urllib.request.urlopen(
                req, timeout=self._timeout, context=ssl_context
            )
            return response.getcode()
        except urllib.error.HTTPError as e:
            # HTTPError carries the status code — return it so the caller
            # can distinguish 4xx (no retry) from 5xx (retry).
            return e.code
