"""
Tests for subscription handler — MCP tool CRUD operations.
"""

import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

# Add plugin to path
plugin_path = Path(__file__).parent.parent / "MCP Server.indigoPlugin/Contents/Server Plugin"
sys.path.insert(0, str(plugin_path))

from mcp_server.events.subscription_handler import SubscriptionHandler
from mcp_server.events.subscription_manager import SubscriptionManager
from mcp_server.events.webhook_dispatcher import WebhookDispatcher


@pytest.fixture
def handler():
    manager = SubscriptionManager(logger=Mock())
    dispatcher = WebhookDispatcher(logger=Mock())
    return SubscriptionHandler(
        subscription_manager=manager,
        webhook_dispatcher=dispatcher,
        logger=Mock(),
    )


class TestCreateSubscription:
    """Tests for create_event_subscription tool."""

    def test_create_basic(self, handler):
        result = handler.create_subscription(
            webhook_url="https://example.com/hook",
            entity_type="device",
            conditions={"onState": False},
        )
        assert result["success"] is True
        assert "subscription_id" in result["data"]
        assert result["data"]["webhook_url"] == "https://example.com/hook"

    def test_create_with_all_options(self, handler):
        result = handler.create_subscription(
            webhook_url="https://example.com/hook",
            entity_type="device",
            entity_id=100,
            conditions={"onState": False},
            auth={"mode": "hmac", "token": "secret123", "verify_ssl": False},
            duration_seconds=60,
            description="Front door opened",
        )
        assert result["success"] is True
        data = result["data"]
        assert data["entity_id"] == 100
        assert data["auth_mode"] == "hmac"
        assert data["auth_token"] == "***"  # Redacted
        assert data["verify_ssl"] is False
        assert data["duration_seconds"] == 60
        assert data["description"] == "Front door opened"

    def test_create_missing_url(self, handler):
        result = handler.create_subscription(
            entity_type="device",
            conditions={"onState": False},
        )
        assert result["success"] is False
        assert "webhook_url" in result.get("error", "") or "missing" in result.get("error", "").lower()

    def test_create_missing_entity_type(self, handler):
        result = handler.create_subscription(
            webhook_url="https://example.com/hook",
            conditions={"onState": False},
        )
        assert result["success"] is False

    def test_create_missing_conditions(self, handler):
        result = handler.create_subscription(
            webhook_url="https://example.com/hook",
            entity_type="device",
        )
        assert result["success"] is False

    def test_create_invalid_entity_type(self, handler):
        result = handler.create_subscription(
            webhook_url="https://example.com/hook",
            entity_type="action",
            conditions={"onState": False},
        )
        assert result["success"] is False
        assert "entity_type" in result["error"]

    def test_create_invalid_url_scheme(self, handler):
        result = handler.create_subscription(
            webhook_url="ftp://example.com/hook",
            entity_type="device",
            conditions={"onState": False},
        )
        assert result["success"] is False
        assert "scheme" in result["error"].lower() or "url" in result["error"].lower()

    def test_create_invalid_auth_mode(self, handler):
        result = handler.create_subscription(
            webhook_url="https://example.com/hook",
            entity_type="device",
            conditions={"onState": False},
            auth={"mode": "oauth"},
        )
        assert result["success"] is False
        assert "auth" in result["error"].lower()

    def test_create_bearer_without_token(self, handler):
        result = handler.create_subscription(
            webhook_url="https://example.com/hook",
            entity_type="device",
            conditions={"onState": False},
            auth={"mode": "bearer", "token": ""},
        )
        assert result["success"] is False
        assert "token" in result["error"].lower()

    def test_create_empty_conditions(self, handler):
        result = handler.create_subscription(
            webhook_url="https://example.com/hook",
            entity_type="device",
            conditions={},
        )
        assert result["success"] is False

    def test_create_invalid_duration(self, handler):
        result = handler.create_subscription(
            webhook_url="https://example.com/hook",
            entity_type="device",
            conditions={"onState": False},
            duration_seconds=0,
        )
        assert result["success"] is False

    def test_create_with_max_fires(self, handler):
        result = handler.create_subscription(
            webhook_url="https://example.com/hook",
            entity_type="device",
            conditions={"onState": False},
            max_fires=1,
        )
        assert result["success"] is True
        assert result["data"]["max_fires"] == 1

    def test_create_invalid_max_fires(self, handler):
        result = handler.create_subscription(
            webhook_url="https://example.com/hook",
            entity_type="device",
            conditions={"onState": False},
            max_fires=0,
        )
        assert result["success"] is False


class TestListSubscriptions:
    """Tests for list_event_subscriptions tool."""

    def test_list_empty(self, handler):
        result = handler.list_subscriptions()
        assert result["success"] is True
        assert result["data"]["count"] == 0
        assert result["data"]["subscriptions"] == []

    def test_list_with_subscriptions(self, handler):
        handler.create_subscription(
            webhook_url="https://a.com", entity_type="device", conditions={"onState": True}
        )
        handler.create_subscription(
            webhook_url="https://b.com", entity_type="variable", conditions={"value": "x"}
        )
        result = handler.list_subscriptions()
        assert result["success"] is True
        assert result["data"]["count"] == 2

    def test_list_single_by_id(self, handler):
        create_result = handler.create_subscription(
            webhook_url="https://a.com", entity_type="device", conditions={"onState": True}
        )
        sub_id = create_result["data"]["subscription_id"]

        result = handler.list_subscriptions(subscription_id=sub_id)
        assert result["success"] is True
        assert result["data"]["subscription_id"] == sub_id

    def test_list_nonexistent_id(self, handler):
        result = handler.list_subscriptions(subscription_id="nonexistent")
        assert result["success"] is False

    def test_list_includes_dispatcher_stats(self, handler):
        result = handler.list_subscriptions()
        assert "dispatcher" in result["data"]
        assert "events_sent" in result["data"]["dispatcher"]

    def test_list_redacts_auth_token(self, handler):
        """Auth tokens should be redacted in list output."""
        handler.create_subscription(
            webhook_url="https://example.com/hook",
            entity_type="device",
            conditions={"onState": False},
            auth={"mode": "bearer", "token": "my-secret"},
        )
        result = handler.list_subscriptions()
        assert result["success"] is True
        assert result["data"]["count"] == 1

        sub_data = result["data"]["subscriptions"][0]
        assert sub_data["auth_token"] == "***"
        assert sub_data["auth_token"] != "my-secret"


class TestDeleteSubscription:
    """Tests for delete_event_subscription tool."""

    def test_delete_existing(self, handler):
        create_result = handler.create_subscription(
            webhook_url="https://a.com", entity_type="device", conditions={"onState": True}
        )
        sub_id = create_result["data"]["subscription_id"]

        result = handler.delete_subscription(subscription_id=sub_id)
        assert result["success"] is True
        assert result["data"]["deleted"] is True

    def test_delete_nonexistent(self, handler):
        result = handler.delete_subscription(subscription_id="nonexistent")
        assert result["success"] is False

    def test_delete_missing_id(self, handler):
        result = handler.delete_subscription()
        assert result["success"] is False
