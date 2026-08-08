"""
Tests for search_entities returning live entity state.

The vector store only rewrites a record when an entity's static fields change,
so its stored state can be arbitrarily old. Results must reflect the data
provider, not the index.
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PLUGIN_SRC = Path(__file__).parent.parent / "MCP Server.indigoPlugin/Contents/Server Plugin"
BASE = PLUGIN_SRC / "mcp_server"


def _load_module_from_file(name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _stub_package(name: str, path: Path):
    if name in sys.modules and getattr(sys.modules[name], "__path__", None):
        return sys.modules[name]
    mod = MagicMock()
    mod.__path__ = [str(path)]
    mod.__spec__ = None
    mod.__package__ = name
    sys.modules[name] = mod
    return mod


_stub_package("mcp_server", BASE)
_stub_package("mcp_server.common", BASE / "common")
_stub_package("mcp_server.tools", BASE / "tools")
_stub_package("mcp_server.adapters", BASE / "adapters")
_stub_package("mcp_server.tools.search_entities", BASE / "tools" / "search_entities")

for _name, _path in [
    ("mcp_server.adapters.data_provider", BASE / "adapters" / "data_provider.py"),
    ("mcp_server.adapters.vector_store_interface", BASE / "adapters" / "vector_store_interface.py"),
    ("mcp_server.common.log_style", BASE / "common" / "log_style.py"),
    ("mcp_server.common.state_filter", BASE / "common" / "state_filter.py"),
    ("mcp_server.common.json_encoder", BASE / "common" / "json_encoder.py"),
    ("mcp_server.common.indigo_device_types", BASE / "common" / "indigo_device_types.py"),
    ("mcp_server.tools.base_handler", BASE / "tools" / "base_handler.py"),
    ("mcp_server.tools.search_entities.query_parser", BASE / "tools" / "search_entities" / "query_parser.py"),
    ("mcp_server.tools.search_entities.result_formatter", BASE / "tools" / "search_entities" / "result_formatter.py"),
]:
    _load_module_from_file(_name, _path)

search_mod = _load_module_from_file(
    "mcp_server.tools.search_entities.main", BASE / "tools" / "search_entities" / "main.py"
)

SearchEntitiesHandler = search_mod.SearchEntitiesHandler


# The state the index captured a year ago, versus what the device reads now.
STALE_DEVICE = {
    "id": 528656030,
    "name": "Living Room Temperature",
    "displayStateValRaw": 76.7,
    "lastChanged": "2025-08-11T14:20:49",
    "states": {"sensorValue": 76.7},
    "_similarity_score": 0.765,
}

LIVE_DEVICE = {
    "id": 528656030,
    "name": "Living Room Temperature",
    "displayStateValRaw": 69.1,
    "lastChanged": "2026-08-08T16:10:43",
    "states": {"sensorValue": 69.1},
}


@pytest.fixture
def handler():
    return SearchEntitiesHandler(data_provider=MagicMock(), vector_store=MagicMock())


class TestRefreshWithLiveState:
    def test_device_state_comes_from_the_provider(self, handler):
        handler.data_provider.get_device.return_value = LIVE_DEVICE

        result = handler._refresh_with_live_state({"devices": [STALE_DEVICE]})
        device = result["devices"][0]

        assert device["displayStateValRaw"] == 69.1
        assert device["lastChanged"] == "2026-08-08T16:10:43"
        assert device["states"]["sensorValue"] == 69.1
        handler.data_provider.get_device.assert_called_once_with(528656030)

    def test_similarity_score_survives_the_refresh(self, handler):
        """
        The formatter turns _similarity_score into the user-facing
        relevance_score, so losing it here silently zeroes every result.
        """
        handler.data_provider.get_device.return_value = LIVE_DEVICE

        result = handler._refresh_with_live_state({"devices": [STALE_DEVICE]})

        assert result["devices"][0]["_similarity_score"] == 0.765

    def test_all_search_annotations_survive_the_refresh(self, handler):
        handler.data_provider.get_device.return_value = LIVE_DEVICE
        annotated = dict(STALE_DEVICE, _entity_type="device", _distance=0.235)

        result = handler._refresh_with_live_state({"devices": [annotated]})
        device = result["devices"][0]

        assert device["_entity_type"] == "device"
        assert device["_distance"] == 0.235
        assert device["displayStateValRaw"] == 69.1

    def test_missing_entity_keeps_the_stored_record(self, handler):
        handler.data_provider.get_device.return_value = None

        result = handler._refresh_with_live_state({"devices": [STALE_DEVICE]})

        assert result["devices"] == [STALE_DEVICE]

    def test_lookup_error_keeps_the_stored_record(self, handler):
        handler.data_provider.get_device.side_effect = RuntimeError("provider down")

        result = handler._refresh_with_live_state({"devices": [STALE_DEVICE]})

        assert result["devices"] == [STALE_DEVICE]

    def test_nothing_is_dropped(self, handler):
        handler.data_provider.get_device.side_effect = [LIVE_DEVICE, None]

        result = handler._refresh_with_live_state(
            {"devices": [STALE_DEVICE, {"id": 99, "name": "Gone"}]}
        )

        assert len(result["devices"]) == 2

    def test_entity_without_id_is_passed_through(self, handler):
        orphan = {"name": "No Id"}

        result = handler._refresh_with_live_state({"devices": [orphan]})

        assert result["devices"] == [orphan]
        handler.data_provider.get_device.assert_not_called()

    @pytest.mark.parametrize(
        "bucket,lookup",
        [
            ("variables", "get_variable"),
            ("actions", "get_action"),
            ("triggers", "get_trigger"),
            ("schedules", "get_schedule"),
        ],
    )
    def test_every_entity_type_is_refreshed(self, handler, bucket, lookup):
        getattr(handler.data_provider, lookup).return_value = {"id": 7, "value": "fresh"}

        result = handler._refresh_with_live_state({bucket: [{"id": 7, "value": "stale"}]})

        assert result[bucket][0]["value"] == "fresh"
        getattr(handler.data_provider, lookup).assert_called_once_with(7)

    def test_unknown_bucket_is_left_alone(self, handler):
        payload = {"widgets": [{"id": 1}]}
        assert handler._refresh_with_live_state(payload) == payload

    def test_empty_buckets_are_preserved(self, handler):
        assert handler._refresh_with_live_state({"devices": []}) == {"devices": []}


class TestStateFilterSeesLiveState:
    def test_filtering_runs_against_refreshed_values(self, handler):
        """
        The refresh happens before StateFilter, so a filter matching the live
        value finds the device even when the index still holds the old one.
        """
        handler.data_provider.get_device.return_value = LIVE_DEVICE

        refreshed = handler._refresh_with_live_state({"devices": [STALE_DEVICE]})
        state_filter = search_mod.StateFilter.filter_by_state(
            refreshed["devices"], {"displayStateValRaw": 69.1}
        )

        assert len(state_filter) == 1
