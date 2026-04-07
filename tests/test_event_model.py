"""
Tests for event model and ULID generator.
"""

import sys
import time
from pathlib import Path

import pytest

# Add plugin to path
plugin_path = Path(__file__).parent.parent / "MCP Server.indigoPlugin/Contents/Server Plugin"
sys.path.insert(0, str(plugin_path))

from mcp_server.events.event_model import Event, generate_ulid, SCHEMA_VERSION


class TestULIDGeneration:
    """Tests for the ULID generator."""

    def test_ulid_length(self):
        """ULID should be 26 characters."""
        ulid = generate_ulid()
        assert len(ulid) == 26

    def test_ulid_uniqueness(self):
        """Multiple ULIDs should be unique."""
        ulids = [generate_ulid() for _ in range(100)]
        assert len(set(ulids)) == 100

    def test_ulid_sortable(self):
        """ULIDs generated in sequence should be lexicographically ordered."""
        first = generate_ulid()
        time.sleep(0.002)  # Ensure different timestamp
        second = generate_ulid()
        assert first < second

    def test_ulid_characters(self):
        """ULID should use only Crockford base32 characters."""
        crockford = set("0123456789ABCDEFGHJKMNPQRSTVWXYZ")
        ulid = generate_ulid()
        assert all(c in crockford for c in ulid)


class TestEventModel:
    """Tests for the Event dataclass."""

    def test_event_default_fields(self):
        """Event should have sensible defaults."""
        event = Event()
        assert len(event.event_id) == 26
        assert event.schema_version == SCHEMA_VERSION
        assert event.source["system"] == "indigo"
        assert event.source["plugin"] == "com.vtmikel.mcp_server"
        assert event.timestamp  # non-empty
        assert event.event_type == ""
        assert event.entity == {}
        assert event.state == {}
        assert event.trigger == {}
        assert event.human == {}

    def test_event_custom_fields(self):
        """Event should accept custom field values."""
        event = Event(
            event_type="device.state_changed",
            entity={"kind": "device", "id": 123, "name": "Front Door"},
            state={"changed_keys": ["onState"], "old": {"onState": True}, "new": {"onState": False}},
            dedupe_key="indigo:device:123:state:onState:false",
            trigger={"subscription_id": "abc123", "conditions_matched": {"onState": False}},
            human={"title": "Front Door opened", "summary": "Front Door: onState=False"},
        )
        assert event.event_type == "device.state_changed"
        assert event.entity["name"] == "Front Door"
        assert event.state["new"]["onState"] is False
        assert event.trigger["subscription_id"] == "abc123"

    def test_event_to_dict(self):
        """to_dict() should return a plain dictionary."""
        event = Event(event_type="device.state_changed")
        d = event.to_dict()
        assert isinstance(d, dict)
        assert d["event_type"] == "device.state_changed"
        assert d["schema_version"] == SCHEMA_VERSION
        assert "event_id" in d
        assert "timestamp" in d
        assert "source" in d

    def test_event_to_dict_serializable(self):
        """to_dict() output should be JSON-serializable."""
        import json
        event = Event(
            event_type="variable.value_changed",
            entity={"kind": "variable", "id": 456, "name": "test_var"},
            state={"changed_keys": ["value"], "old": {"value": "a"}, "new": {"value": "b"}},
        )
        json_str = json.dumps(event.to_dict())
        assert json_str  # non-empty valid JSON
