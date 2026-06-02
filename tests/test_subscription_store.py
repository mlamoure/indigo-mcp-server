"""
Tests for SubscriptionStore — on-disk persistence of event subscriptions.

Pure file IO; no Indigo. Uses a temp directory so nothing touches a real path.
"""

import json
import os
import stat
import sys
from pathlib import Path

import pytest

plugin_path = Path(__file__).parent.parent / "MCP Server.indigoPlugin/Contents/Server Plugin"
sys.path.insert(0, str(plugin_path))

from mcp_server.events.subscription_store import SubscriptionStore, SCHEMA_VERSION
from mcp_server.events.subscription_model import Subscription


def _make_sub(**overrides):
    kwargs = dict(
        webhook_url="https://example.com/hook",
        entity_type="variable",
        entity_id=88,
        conditions={"value": {"gt": 50}},
        auth_mode="bearer",
        auth_token="secret-token-abc",
        description="Garage temp",
    )
    kwargs.update(overrides)
    sub = Subscription(**kwargs)
    sub.stats["fires"] = 4
    sub.stats["last_http_status"] = 200
    return sub


@pytest.fixture
def store_path(tmp_path):
    return str(tmp_path / "subscriptions.json")


class TestRoundTrip:
    def test_save_then_load_preserves_all_fields(self, store_path):
        store = SubscriptionStore(store_path)
        sub = _make_sub()
        store.save([sub])

        loaded = store.load()
        assert len(loaded) == 1
        r = loaded[0]
        assert r.subscription_id == sub.subscription_id
        assert r.created_at == sub.created_at
        assert r.webhook_url == sub.webhook_url
        assert r.auth_mode == "bearer"
        assert r.auth_token == "secret-token-abc"  # token round-trips
        assert r.conditions == {"value": {"gt": 50}}
        assert r.entity_id == 88
        assert r.stats["fires"] == 4
        assert r.stats["last_http_status"] == 200

    def test_token_is_present_in_file(self, store_path):
        # Documents that the on-disk file IS the one place the token is stored.
        SubscriptionStore(store_path).save([_make_sub()])
        text = Path(store_path).read_text()
        assert "secret-token-abc" in text
        payload = json.loads(text)
        assert payload["version"] == SCHEMA_VERSION

    def test_multiple_and_empty(self, store_path):
        store = SubscriptionStore(store_path)
        store.save([_make_sub(), _make_sub(description="second")])
        assert len(store.load()) == 2
        store.save([])
        assert store.load() == []


class TestMissingAndCorrupt:
    def test_missing_file_returns_empty(self, store_path):
        assert SubscriptionStore(store_path).load() == []

    def test_corrupt_file_backed_up_and_empty(self, store_path):
        Path(store_path).write_text("{ this is not valid json ")
        store = SubscriptionStore(store_path)
        assert store.load() == []
        assert os.path.exists(store_path + ".corrupt")
        # original path is now free for a clean save
        assert not os.path.exists(store_path)


class TestAtomicAndPerms:
    def test_target_valid_after_save(self, store_path):
        SubscriptionStore(store_path).save([_make_sub()])
        assert os.path.exists(store_path)
        json.loads(Path(store_path).read_text())  # parses

    def test_file_mode_is_0600(self, store_path):
        SubscriptionStore(store_path).save([_make_sub()])
        mode = stat.S_IMODE(os.stat(store_path).st_mode)
        assert mode == 0o600

    def test_no_tempfiles_left_behind(self, store_path, tmp_path):
        SubscriptionStore(store_path).save([_make_sub()])
        leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".subscriptions-")]
        assert leftovers == []

    def test_overwrite_replaces_contents(self, store_path):
        store = SubscriptionStore(store_path)
        store.save([_make_sub(description="first")])
        store.save([_make_sub(description="second")])
        loaded = store.load()
        assert len(loaded) == 1
        assert loaded[0].description == "second"
