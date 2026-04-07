"""
Tests for subscription manager — CRUD and state change evaluation.
"""

import sys
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

# Add plugin to path
plugin_path = Path(__file__).parent.parent / "MCP Server.indigoPlugin/Contents/Server Plugin"
sys.path.insert(0, str(plugin_path))

from mcp_server.events.subscription_manager import SubscriptionManager
from mcp_server.events.subscription_model import Subscription


class TestSubscriptionCRUD:
    """Tests for subscription create/list/get/delete."""

    @pytest.fixture
    def manager(self):
        return SubscriptionManager(logger=Mock())

    def test_create_subscription(self, manager):
        sub = manager.create(
            webhook_url="https://example.com/hook",
            entity_type="device",
            conditions={"onState": False},
            description="Test subscription",
        )
        assert sub.subscription_id
        assert sub.webhook_url == "https://example.com/hook"
        assert sub.entity_type == "device"
        assert sub.conditions == {"onState": False}

    def test_list_subscriptions(self, manager):
        manager.create(webhook_url="https://a.com", entity_type="device", conditions={"onState": True})
        manager.create(webhook_url="https://b.com", entity_type="variable", conditions={"value": "x"})
        subs = manager.list_all()
        assert len(subs) == 2

    def test_get_subscription(self, manager):
        sub = manager.create(webhook_url="https://a.com", entity_type="device", conditions={"onState": True})
        retrieved = manager.get(sub.subscription_id)
        assert retrieved is sub

    def test_get_nonexistent(self, manager):
        assert manager.get("nonexistent") is None

    def test_delete_subscription(self, manager):
        sub = manager.create(webhook_url="https://a.com", entity_type="device", conditions={"onState": True})
        assert manager.delete(sub.subscription_id) is True
        assert manager.get(sub.subscription_id) is None
        assert manager.count() == 0

    def test_delete_nonexistent(self, manager):
        assert manager.delete("nonexistent") is False

    def test_count(self, manager):
        assert manager.count() == 0
        manager.create(webhook_url="https://a.com", entity_type="device", conditions={"onState": True})
        assert manager.count() == 1


class TestDeviceChangeEvaluation:
    """Tests for evaluate_device_change with transition detection."""

    @pytest.fixture
    def manager(self):
        return SubscriptionManager(logger=Mock())

    def test_transition_into_match(self, manager):
        """Webhook should fire when state transitions INTO matching condition."""
        manager.create(
            webhook_url="https://example.com/hook",
            entity_type="device",
            entity_id=100,
            conditions={"onState": False},
        )
        orig = {"id": 100, "name": "Front Door", "deviceTypeId": "sensor", "onState": True}
        new = {"id": 100, "name": "Front Door", "deviceTypeId": "sensor", "onState": False}

        matches = manager.evaluate_device_change(orig, new)
        assert len(matches) == 1
        sub, event = matches[0]
        assert event.event_type == "device.state_changed"
        assert event.entity["id"] == 100
        assert event.state["new"]["onState"] is False

    def test_no_fire_when_already_matching(self, manager):
        """Webhook should NOT fire when state was already matching."""
        manager.create(
            webhook_url="https://example.com/hook",
            entity_type="device",
            entity_id=100,
            conditions={"onState": False},
        )
        # Both old and new have onState=False — no transition
        orig = {"id": 100, "name": "Front Door", "deviceTypeId": "sensor", "onState": False, "brightness": 0}
        new = {"id": 100, "name": "Front Door", "deviceTypeId": "sensor", "onState": False, "brightness": 50}

        matches = manager.evaluate_device_change(orig, new)
        assert len(matches) == 0

    def test_no_fire_on_transition_out(self, manager):
        """Webhook should NOT fire when state transitions OUT of matching condition."""
        manager.create(
            webhook_url="https://example.com/hook",
            entity_type="device",
            entity_id=100,
            conditions={"onState": False},
        )
        orig = {"id": 100, "name": "Front Door", "deviceTypeId": "sensor", "onState": False}
        new = {"id": 100, "name": "Front Door", "deviceTypeId": "sensor", "onState": True}

        matches = manager.evaluate_device_change(orig, new)
        assert len(matches) == 0

    def test_entity_id_filter(self, manager):
        """Subscription with entity_id should only match that device."""
        manager.create(
            webhook_url="https://example.com/hook",
            entity_type="device",
            entity_id=100,
            conditions={"onState": False},
        )
        # Different device ID
        orig = {"id": 200, "name": "Back Door", "deviceTypeId": "sensor", "onState": True}
        new = {"id": 200, "name": "Back Door", "deviceTypeId": "sensor", "onState": False}

        matches = manager.evaluate_device_change(orig, new)
        assert len(matches) == 0

    def test_wildcard_entity(self, manager):
        """Subscription without entity_id should match any device."""
        manager.create(
            webhook_url="https://example.com/hook",
            entity_type="device",
            conditions={"onState": False},
        )
        orig = {"id": 999, "name": "Any Device", "deviceTypeId": "sensor", "onState": True}
        new = {"id": 999, "name": "Any Device", "deviceTypeId": "sensor", "onState": False}

        matches = manager.evaluate_device_change(orig, new)
        assert len(matches) == 1

    def test_complex_condition_gt(self, manager):
        """Complex conditions with operators should work."""
        manager.create(
            webhook_url="https://example.com/hook",
            entity_type="device",
            conditions={"brightness": {"gt": 80}},
        )
        orig = {"id": 100, "name": "Lamp", "deviceTypeId": "dimmer", "onState": True, "brightness": 50}
        new = {"id": 100, "name": "Lamp", "deviceTypeId": "dimmer", "onState": True, "brightness": 90}

        matches = manager.evaluate_device_change(orig, new)
        assert len(matches) == 1

    def test_no_state_change_quick_reject(self, manager):
        """Should quickly reject when no meaningful state changed."""
        manager.create(
            webhook_url="https://example.com/hook",
            entity_type="device",
            conditions={"onState": False},
        )
        # Same state — only name changed (config update, not state)
        orig = {"id": 100, "name": "Old Name", "deviceTypeId": "sensor", "onState": True, "states": {}}
        new = {"id": 100, "name": "New Name", "deviceTypeId": "sensor", "onState": True, "states": {}}

        matches = manager.evaluate_device_change(orig, new)
        assert len(matches) == 0

    def test_multiple_subscriptions_match(self, manager):
        """Multiple subscriptions can match the same event."""
        manager.create(webhook_url="https://a.com", entity_type="device", conditions={"onState": False})
        manager.create(webhook_url="https://b.com", entity_type="device", conditions={"onState": False})

        orig = {"id": 100, "name": "Door", "deviceTypeId": "sensor", "onState": True}
        new = {"id": 100, "name": "Door", "deviceTypeId": "sensor", "onState": False}

        matches = manager.evaluate_device_change(orig, new)
        assert len(matches) == 2

    def test_states_dict_condition(self, manager):
        """Conditions can reference nested states dict values."""
        manager.create(
            webhook_url="https://example.com/hook",
            entity_type="device",
            conditions={"sensorValue": {"lt": 32}},
        )
        orig = {"id": 100, "name": "Temp", "deviceTypeId": "sensor", "onState": True,
                "states": {"sensorValue": 40}}
        new = {"id": 100, "name": "Temp", "deviceTypeId": "sensor", "onState": True,
               "states": {"sensorValue": 28}}

        matches = manager.evaluate_device_change(orig, new)
        assert len(matches) == 1


class TestVariableChangeEvaluation:
    """Tests for evaluate_variable_change."""

    @pytest.fixture
    def manager(self):
        return SubscriptionManager(logger=Mock())

    def test_variable_value_change(self, manager):
        manager.create(
            webhook_url="https://example.com/hook",
            entity_type="variable",
            entity_id=50,
            conditions={"value": "alert"},
        )
        orig = {"id": 50, "name": "status", "value": "normal"}
        new = {"id": 50, "name": "status", "value": "alert"}

        matches = manager.evaluate_variable_change(orig, new)
        assert len(matches) == 1
        sub, event = matches[0]
        assert event.event_type == "variable.value_changed"

    def test_variable_no_change(self, manager):
        manager.create(
            webhook_url="https://example.com/hook",
            entity_type="variable",
            conditions={"value": "alert"},
        )
        orig = {"id": 50, "name": "status", "value": "alert"}
        new = {"id": 50, "name": "status", "value": "alert"}

        matches = manager.evaluate_variable_change(orig, new)
        assert len(matches) == 0

    def test_event_payload_structure(self, manager):
        """Verify the event payload has all required fields."""
        manager.create(
            webhook_url="https://example.com/hook",
            entity_type="variable",
            entity_id=50,
            conditions={"value": "on"},
        )
        orig = {"id": 50, "name": "flag", "value": "off"}
        new = {"id": 50, "name": "flag", "value": "on"}

        matches = manager.evaluate_variable_change(orig, new)
        assert len(matches) == 1
        _, event = matches[0]

        d = event.to_dict()
        assert "event_id" in d
        assert "schema_version" in d
        assert "dedupe_key" in d
        assert "source" in d
        assert "timestamp" in d
        assert "event_type" in d
        assert "entity" in d
        assert "state" in d
        assert "trigger" in d
        assert "human" in d
        assert d["trigger"]["conditions_matched"] == {"value": "on"}


class TestDwellTimerIntegration:
    """Tests for dwell timer integration within SubscriptionManager."""

    @pytest.fixture
    def dispatch_mock(self):
        return Mock()

    @pytest.fixture
    def manager(self, dispatch_mock):
        mgr = SubscriptionManager(logger=Mock())
        mgr.set_dispatch_callback(dispatch_mock)
        return mgr

    def test_dwell_timer_starts_on_match_with_duration(self, manager, dispatch_mock):
        """When a subscription has duration_seconds, a matching transition should
        NOT appear in returned matches (deferred to dwell timer). The dispatch
        callback should fire after the duration elapses."""
        manager.create(
            webhook_url="https://example.com/hook",
            entity_type="device",
            entity_id=100,
            conditions={"onState": False},
            duration_seconds=1,
        )
        orig = {"id": 100, "name": "Door", "deviceTypeId": "sensor", "onState": True}
        new = {"id": 100, "name": "Door", "deviceTypeId": "sensor", "onState": False}

        matches = manager.evaluate_device_change(orig, new)

        # The event should be deferred, not in immediate matches
        assert len(matches) == 0

        # Wait for the dwell timer to fire (1s duration + buffer)
        time.sleep(1.5)

        # The dispatch callback should have been called once with (sub, event)
        assert dispatch_mock.call_count == 1
        call_args = dispatch_mock.call_args[0]
        sub_arg, event_arg = call_args
        assert sub_arg.entity_id == 100
        assert event_arg.event_type == "device.state_changed"

        manager.shutdown()

    def test_dwell_timer_cancels_on_revert(self, manager, dispatch_mock):
        """When the condition reverts before the dwell duration, the timer should
        be cancelled and the callback should never fire."""
        manager.create(
            webhook_url="https://example.com/hook",
            entity_type="device",
            entity_id=100,
            conditions={"onState": False},
            duration_seconds=5,
        )
        # Step 1: Transition INTO match — starts the dwell timer
        orig = {"id": 100, "name": "Door", "deviceTypeId": "sensor", "onState": True}
        new = {"id": 100, "name": "Door", "deviceTypeId": "sensor", "onState": False}
        matches = manager.evaluate_device_change(orig, new)
        assert len(matches) == 0  # deferred

        # Step 2: Revert — condition no longer matches, should cancel the timer
        orig_reverted = {"id": 100, "name": "Door", "deviceTypeId": "sensor", "onState": False}
        new_reverted = {"id": 100, "name": "Door", "deviceTypeId": "sensor", "onState": True}
        matches = manager.evaluate_device_change(orig_reverted, new_reverted)
        assert len(matches) == 0  # transition out, no match

        # Wait a bit to confirm the timer was truly cancelled
        time.sleep(1)
        assert dispatch_mock.call_count == 0

        manager.shutdown()
