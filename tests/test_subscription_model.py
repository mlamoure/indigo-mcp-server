"""
Tests for Subscription.to_dict / from_dict round-trip (used for persistence).
"""

import sys
from pathlib import Path

plugin_path = Path(__file__).parent.parent / "MCP Server.indigoPlugin/Contents/Server Plugin"
sys.path.insert(0, str(plugin_path))

from mcp_server.events.subscription_model import Subscription


class TestFromDict:
    def test_full_round_trip(self):
        sub = Subscription(
            webhook_url="https://example.com/hook",
            auth_mode="hmac",
            auth_token="shared-secret",
            verify_ssl=False,
            entity_type="device",
            entity_id=12345,
            conditions={"onState": True},
            duration_seconds=600,
            max_fires=3,
            description="Garage left open",
        )
        sub.record_success(200)  # mutate stats

        restored = Subscription.from_dict(sub.to_dict(include_token=True))

        assert restored.subscription_id == sub.subscription_id
        assert restored.created_at == sub.created_at
        assert restored.auth_token == "shared-secret"
        assert restored.verify_ssl is False
        assert restored.conditions == {"onState": True}
        assert restored.duration_seconds == 600
        assert restored.max_fires == 3
        assert restored.stats["fires"] == 1
        assert restored.stats["last_http_status"] == 200

    def test_any_change_conditions_survive(self):
        sub = Subscription(
            webhook_url="https://example.com/hook",
            entity_type="variable",
            conditions={"any_change": True},
        )
        restored = Subscription.from_dict(sub.to_dict(include_token=True))
        assert restored.conditions == {"any_change": True}

    def test_missing_keys_use_defaults(self):
        restored = Subscription.from_dict({"subscription_id": "ABC123"})
        assert restored.subscription_id == "ABC123"
        assert restored.auth_mode == "none"
        assert restored.verify_ssl is True
        assert restored.conditions == {}
        assert restored.stats["fires"] == 0

    def test_generated_id_when_absent(self):
        restored = Subscription.from_dict({"webhook_url": "https://x.example/h"})
        assert restored.subscription_id  # non-empty ULID generated
