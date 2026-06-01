"""
Tests for the event-subscriptions web UI renderer.

The renderer is pure (no Indigo, no I/O), so it is tested in isolation against
display-safe subscription dicts produced by Subscription.to_dict().
"""

import sys
from pathlib import Path

from unittest.mock import Mock

plugin_path = Path(__file__).parent.parent / "MCP Server.indigoPlugin/Contents/Server Plugin"
sys.path.insert(0, str(plugin_path))

from mcp_server.events.web_ui import (
    parse_delete_subscription_id,
    render_disabled_page,
    render_subscriptions_page,
)
from mcp_server.events.subscription_manager import SubscriptionManager


def _make_sub(**overrides):
    """Create a display-safe subscription dict via the real manager/model."""
    manager = SubscriptionManager(logger=Mock())
    kwargs = dict(
        webhook_url="https://example.com/hook",
        entity_type="variable",
        entity_id=50,
        conditions={"value": "alert"},
        description="My subscription",
    )
    kwargs.update(overrides)
    sub = manager.create(**kwargs)
    return sub.to_dict(include_token=False)


class TestRenderEmptyState:
    def test_empty_list(self):
        html = render_subscriptions_page([])
        assert "No active subscriptions" in html
        assert "0 active subscriptions" in html
        assert "<!DOCTYPE html>" in html

    def test_disabled_page(self):
        html = render_disabled_page()
        assert "disabled" in html.lower()
        assert "Enable Event Webhooks" in html


class TestRenderSubscription:
    def test_renders_core_fields(self):
        sub = _make_sub()
        html = render_subscriptions_page([sub])
        assert "My subscription" in html
        assert "https://example.com/hook" in html
        assert sub["subscription_id"] in html
        assert "1 active subscription" in html

    def test_remove_form_has_subscription_id(self):
        sub = _make_sub()
        html = render_subscriptions_page([sub])
        assert 'name="subscription_id"' in html
        assert f'value="{sub["subscription_id"]}"' in html
        assert 'method="POST"' in html
        assert "Remove" in html

    def test_any_change_badge(self):
        sub = _make_sub(conditions={"any_change": True})
        html = render_subscriptions_page([sub])
        assert "any change" in html
        assert "badge" in html

    def test_stats_rendered(self):
        sub = _make_sub()
        sub["stats"]["fires"] = 7
        sub["stats"]["last_http_status"] = 200
        html = render_subscriptions_page([sub])
        assert "fires" in html
        assert "7" in html


class TestSecurity:
    def test_user_values_escaped(self):
        sub = _make_sub(description='<script>alert(1)</script>')
        html = render_subscriptions_page([sub])
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html

    def test_conditions_escaped(self):
        sub = _make_sub(conditions={"value": '<img src=x onerror=alert(1)>'})
        html = render_subscriptions_page([sub])
        assert "<img src=x" not in html

    def test_token_never_rendered(self):
        manager = SubscriptionManager(logger=Mock())
        sub_obj = manager.create(
            webhook_url="https://example.com/hook",
            entity_type="variable",
            conditions={"value": "x"},
            auth_mode="bearer",
            auth_token="super-secret-token",
        )
        sub = sub_obj.to_dict(include_token=False)
        html = render_subscriptions_page([sub])
        assert "super-secret-token" not in html
        # The redacted placeholder is not rendered either (token field omitted).
        assert "***" not in html


class TestParseDelete:
    def test_basic(self):
        assert parse_delete_subscription_id("subscription_id=01ABC") == "01ABC"

    def test_empty(self):
        assert parse_delete_subscription_id("") is None

    def test_missing_field(self):
        assert parse_delete_subscription_id("foo=bar") is None

    def test_url_encoded(self):
        assert parse_delete_subscription_id("subscription_id=01%2FABC&x=y") == "01/ABC"
