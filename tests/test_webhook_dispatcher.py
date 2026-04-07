"""
Tests for webhook dispatcher — delivery, auth, retry.
"""

import hashlib
import hmac
import json
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from unittest.mock import Mock

import pytest

# Add plugin to path
plugin_path = Path(__file__).parent.parent / "MCP Server.indigoPlugin/Contents/Server Plugin"
sys.path.insert(0, str(plugin_path))

from mcp_server.events.event_model import Event
from mcp_server.events.subscription_model import Subscription
from mcp_server.events.webhook_dispatcher import WebhookDispatcher


class RecordingHandler(BaseHTTPRequestHandler):
    """HTTP handler that records received requests."""
    requests = []

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        self.__class__.requests.append({
            "headers": dict(self.headers),
            "body": json.loads(body),
            "path": self.path,
        })
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress server logs in test output


class FailingHandler(BaseHTTPRequestHandler):
    """HTTP handler that returns 500."""
    request_count = 0

    def do_POST(self):
        self.__class__.request_count += 1
        self.send_response(500)
        self.end_headers()

    def log_message(self, format, *args):
        pass


def _start_server(handler_class, port):
    """Start a test HTTP server in a background thread."""
    server = HTTPServer(("127.0.0.1", port), handler_class)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


class TestWebhookDispatcher:
    """Tests for webhook delivery."""

    def test_successful_delivery(self):
        """Events should be delivered to the webhook URL."""
        RecordingHandler.requests = []
        server = _start_server(RecordingHandler, 19876)
        try:
            dispatcher = WebhookDispatcher(logger=Mock(), timeout=5, max_retries=0)
            dispatcher.start()

            sub = Subscription(
                webhook_url="http://127.0.0.1:19876/events",
                entity_type="device",
                conditions={"onState": False},
            )
            event = Event(
                event_type="device.state_changed",
                entity={"kind": "device", "id": 100, "name": "Door"},
            )

            dispatcher.dispatch(sub, event)
            time.sleep(1)  # Wait for delivery
            dispatcher.stop()

            assert len(RecordingHandler.requests) == 1
            req = RecordingHandler.requests[0]
            assert req["body"]["event_type"] == "device.state_changed"
            assert req["body"]["entity"]["id"] == 100

            # Check custom headers
            assert req["headers"].get("X-Event-Id") == event.event_id
            assert req["headers"].get("X-Event-Type") == "device.state_changed"
            assert req["headers"].get("X-Subscription-Id") == sub.subscription_id
        finally:
            server.shutdown()

    def test_bearer_auth(self):
        """Bearer token should be in Authorization header."""
        RecordingHandler.requests = []
        server = _start_server(RecordingHandler, 19877)
        try:
            dispatcher = WebhookDispatcher(logger=Mock(), timeout=5, max_retries=0)
            dispatcher.start()

            sub = Subscription(
                webhook_url="http://127.0.0.1:19877/events",
                auth_mode="bearer",
                auth_token="test-secret-token",
                entity_type="device",
                conditions={"onState": False},
            )
            event = Event(event_type="device.state_changed")

            dispatcher.dispatch(sub, event)
            time.sleep(1)
            dispatcher.stop()

            assert len(RecordingHandler.requests) == 1
            auth = RecordingHandler.requests[0]["headers"].get("Authorization")
            assert auth == "Bearer test-secret-token"
        finally:
            server.shutdown()

    def test_hmac_auth(self):
        """HMAC signature should be computed correctly."""
        RecordingHandler.requests = []
        server = _start_server(RecordingHandler, 19878)
        try:
            dispatcher = WebhookDispatcher(logger=Mock(), timeout=5, max_retries=0)
            dispatcher.start()

            secret = "my-hmac-secret"
            sub = Subscription(
                webhook_url="http://127.0.0.1:19878/events",
                auth_mode="hmac",
                auth_token=secret,
                entity_type="device",
                conditions={"onState": False},
            )
            event = Event(event_type="device.state_changed")

            dispatcher.dispatch(sub, event)
            time.sleep(1)
            dispatcher.stop()

            assert len(RecordingHandler.requests) == 1
            req = RecordingHandler.requests[0]

            # Verify HMAC signature
            sig_header = req["headers"].get("X-Webhook-Signature")
            assert sig_header is not None
            assert sig_header.startswith("sha256=")

            # Recompute and verify
            body_bytes = json.dumps(event.to_dict()).encode("utf-8")
            expected_sig = hmac.new(
                secret.encode("utf-8"), body_bytes, hashlib.sha256
            ).hexdigest()
            assert sig_header == f"sha256={expected_sig}"

            # Timestamp header should be present
            assert req["headers"].get("X-Webhook-Timestamp") is not None
        finally:
            server.shutdown()

    def test_retry_on_server_error(self):
        """Dispatcher should retry on 500 errors."""
        FailingHandler.request_count = 0
        server = _start_server(FailingHandler, 19879)
        try:
            dispatcher = WebhookDispatcher(
                logger=Mock(), timeout=5, max_retries=2, retry_base_delay=0.1
            )
            dispatcher.start()

            sub = Subscription(
                webhook_url="http://127.0.0.1:19879/events",
                entity_type="device",
                conditions={"onState": False},
            )
            event = Event(event_type="device.state_changed")

            dispatcher.dispatch(sub, event)
            time.sleep(3)  # Wait for retries
            dispatcher.stop()

            # Should have been called 3 times (initial + 2 retries)
            assert FailingHandler.request_count == 3

            # Subscription stats should reflect failures
            assert sub.stats["errors"] >= 1
            assert sub.stats["consecutive_failures"] >= 1
        finally:
            server.shutdown()

    def test_subscription_stats_on_success(self):
        """Subscription stats should update on successful delivery."""
        RecordingHandler.requests = []
        server = _start_server(RecordingHandler, 19880)
        try:
            dispatcher = WebhookDispatcher(logger=Mock(), timeout=5, max_retries=0)
            dispatcher.start()

            sub = Subscription(
                webhook_url="http://127.0.0.1:19880/events",
                entity_type="device",
                conditions={"onState": False},
            )
            event = Event(event_type="device.state_changed")

            dispatcher.dispatch(sub, event)
            time.sleep(1)
            dispatcher.stop()

            assert sub.stats["fires"] == 1
            assert sub.stats["last_success_at"] is not None
            assert sub.stats["last_http_status"] == 200
            assert sub.stats["consecutive_failures"] == 0
        finally:
            server.shutdown()

    def test_dispatcher_stats(self):
        """Dispatcher-level stats should track sent/failed counts."""
        RecordingHandler.requests = []
        server = _start_server(RecordingHandler, 19881)
        try:
            dispatcher = WebhookDispatcher(logger=Mock(), timeout=5, max_retries=0)
            dispatcher.start()

            sub = Subscription(
                webhook_url="http://127.0.0.1:19881/events",
                entity_type="device",
                conditions={"onState": False},
            )
            for _ in range(3):
                dispatcher.dispatch(sub, Event(event_type="test"))

            time.sleep(2)
            stats = dispatcher.get_stats()
            dispatcher.stop()

            assert stats["events_sent"] == 3
            assert stats["events_failed"] == 0
        finally:
            server.shutdown()

    def test_no_retry_on_client_error(self):
        """Dispatcher should NOT retry on 4xx client errors."""

        class ClientErrorHandler(BaseHTTPRequestHandler):
            """HTTP handler that returns 400."""
            request_count = 0

            def do_POST(self):
                self.__class__.request_count += 1
                self.send_response(400)
                self.end_headers()

            def log_message(self, format, *args):
                pass

        ClientErrorHandler.request_count = 0
        server = _start_server(ClientErrorHandler, 19882)
        try:
            dispatcher = WebhookDispatcher(
                logger=Mock(), timeout=5, max_retries=3, retry_base_delay=0.1
            )
            dispatcher.start()

            sub = Subscription(
                webhook_url="http://127.0.0.1:19882/events",
                entity_type="device",
                conditions={"onState": False},
            )
            event = Event(event_type="device.state_changed")

            dispatcher.dispatch(sub, event)
            time.sleep(2)  # Wait for delivery attempt(s)
            dispatcher.stop()

            # 4xx should NOT be retried — only 1 request total
            assert ClientErrorHandler.request_count == 1

            # Subscription stats should reflect the error
            assert sub.stats["errors"] >= 1
            assert sub.stats["last_http_status"] == 400
        finally:
            server.shutdown()

    def test_start_idempotency(self):
        """Calling start() twice should not error and the dispatcher should
        still work correctly."""
        RecordingHandler.requests = []
        server = _start_server(RecordingHandler, 19883)
        try:
            dispatcher = WebhookDispatcher(logger=Mock(), timeout=5, max_retries=0)

            # Call start() twice
            dispatcher.start()
            dispatcher.start()

            sub = Subscription(
                webhook_url="http://127.0.0.1:19883/events",
                entity_type="device",
                conditions={"onState": False},
            )
            event = Event(event_type="device.state_changed")

            dispatcher.dispatch(sub, event)
            time.sleep(1)
            dispatcher.stop()

            # Should still deliver the event successfully
            assert len(RecordingHandler.requests) == 1
            assert RecordingHandler.requests[0]["body"]["event_type"] == "device.state_changed"
        finally:
            server.shutdown()

    def test_auto_expire_after_max_fires(self):
        """Subscription with max_fires=2 should trigger on_expired after 2 deliveries."""
        RecordingHandler.requests = []
        server = _start_server(RecordingHandler, 19884)
        try:
            expired_subs = []
            dispatcher = WebhookDispatcher(logger=Mock(), timeout=5, max_retries=0)
            dispatcher.set_on_expired(lambda sub: expired_subs.append(sub))
            dispatcher.start()

            sub = Subscription(
                webhook_url="http://127.0.0.1:19884/events",
                entity_type="device",
                conditions={"onState": False},
                max_fires=2,
            )

            # Fire twice
            dispatcher.dispatch(sub, Event(event_type="test.1"))
            dispatcher.dispatch(sub, Event(event_type="test.2"))
            time.sleep(2)
            dispatcher.stop()

            # Both should have been delivered
            assert len(RecordingHandler.requests) == 2
            assert sub.stats["fires"] == 2

            # on_expired should have been called once (after the 2nd fire)
            assert len(expired_subs) == 1
            assert expired_subs[0].subscription_id == sub.subscription_id
        finally:
            server.shutdown()
