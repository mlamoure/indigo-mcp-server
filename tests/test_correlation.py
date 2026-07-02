"""
Tests for the cause-correlation tool (investigate_event) using the fixture
event logs together with the fixture .indiDb structure store.

Fixture topology: trigger "Front door opens at night" (4000001) directly
acts on Porch Light (1000111) and also executes AG Goodnight (3000002),
which executes AG Evening Scene (3000001), which acts on Porch Light.
Schedule "Run Goodnight at Sunset" (5000001) executes Goodnight.
"""

import datetime
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

plugin_path = Path(__file__).parent.parent / "MCP Server.indigoPlugin/Contents/Server Plugin"
sys.path.insert(0, str(plugin_path))

from mcp_server.adapters.indidb.store import IndiDbStructureStore  # noqa: E402
from mcp_server.tools.log_search.log_search_handler import LogSearchHandler  # noqa: E402

LOGS_DIR = Path(__file__).parent / "fixtures" / "event_logs"
DB_FIXTURE = Path(__file__).parent / "fixtures" / "sample_indidb.xml"


@pytest.fixture
def handler():
    provider = Mock()
    provider.get_logs_folder_path = lambda: str(LOGS_DIR)
    provider.get_device.return_value = {"id": 1000111, "name": "Porch Light"}
    store = IndiDbStructureStore(db_path_supplier=lambda: str(DB_FIXTURE), logger=Mock())
    return LogSearchHandler(data_provider=provider, structure_store=store, logger=Mock())


class TestInvestigateEvent:
    def test_direct_trigger_ranked_first(self, handler):
        # Most recent Porch Light line: 2026-07-01 06:00:01.2, preceded by
        # the front-door trigger firing 1.2s earlier.
        result = handler.investigate_event(device_id=1000111)

        assert result["target_event"]["device"] == {"id": 1000111, "name": "Porch Light"}
        assert result["target_event"]["timestamp"] == "2026-07-01T06:00:01.200000"

        top = result["candidates"][0]
        assert top["rank"] == 1
        assert top["entity_type"] == "trigger"
        assert top["id"] == 4000001
        assert top["relationship"]["role"] == "acts_on"
        assert "via_action_groups" not in top["relationship"]
        assert any("before the target event" in e for e in top["evidence"])

    def test_chain_ranking_and_decay(self, handler):
        # The 21:59:33 Porch Light update follows schedule → Goodnight →
        # Evening Scene. Direct actor outranks depth-1, which outranks depth-2.
        result = handler.investigate_event(
            device_id=1000111, around_time="2026-06-30T21:59:33"
        )
        by_name = {c["name"]: c for c in result["candidates"]}
        evening = by_name["Evening Scene"]
        goodnight = by_name["Goodnight"]
        schedule = by_name["Run Goodnight at Sunset"]

        assert evening["score"] > goodnight["score"] > schedule["score"]
        assert evening["relationship"]["role"] == "acts_on"
        assert goodnight["relationship"]["via_action_groups"] == [3000001]
        assert schedule["relationship"]["via_action_groups"] == [3000002, 3000001]
        assert schedule["entity_type"] == "schedule"
        assert schedule["id"] == 5000001

    def test_no_candidates_gives_manual_note(self, handler):
        result = handler.investigate_event(
            device_id=1000111, around_time="2026-06-30T23:00:00"
        )
        assert result["candidates"] == []
        assert any("manual" in note for note in result["notes"])

    def test_search_text_mode(self, handler):
        result = handler.investigate_event(
            search_text="status update is on", around_time="2026-07-01T06:00:01"
        )
        assert result["target_event"]["timestamp"] == "2026-07-01T06:00:01.200000"
        assert "device" not in result["target_event"]
        # Without a device id there is no structural evidence
        top = result["candidates"][0]
        assert "relationship" not in top

    def test_unknown_device(self, handler):
        handler.data_provider.get_device.return_value = None
        result = handler.investigate_event(device_id=42)
        assert "error" in result

    def test_missing_params(self, handler):
        assert "error" in handler.investigate_event()

    def test_bad_time_format(self, handler):
        result = handler.investigate_event(device_id=1000111, around_time="yesterday")
        assert "error" in result

    def test_no_log_match(self, handler):
        handler.data_provider.get_device.return_value = {
            "id": 5, "name": "Device Never Logged"
        }
        result = handler.investigate_event(device_id=5)
        assert "error" in result
        assert "searched_for" in result


class TestQueryEventLogHandler:
    def test_filtered_search_scans_files(self, handler):
        result = handler.query_event_log(query="Porch Light", types=["Z-Wave"], limit=10)
        assert result["count"] == 3
        assert result["source"] == "log_files"
        assert result["parameters"]["query"] == "Porch Light"

    def test_bad_time_is_error(self, handler):
        assert "error" in handler.query_event_log(start_time="not-a-time")

    def test_no_filters_uses_live_iom_tail(self, handler):
        # No filters → live path via get_event_log_list, normalized + newest-first.
        import datetime as _dt

        handler.data_provider.get_event_log_list.return_value = [
            {"TimeStamp": _dt.datetime(2026, 7, 2, 10, 0, 0), "TypeStr": "Trigger",
             "Message": "\t\tolder line"},
            {"TimeStamp": _dt.datetime(2026, 7, 2, 10, 0, 5), "TypeStr": "Schedule",
             "Message": "newer line"},
        ]
        result = handler.query_event_log(limit=10)
        assert result["source"] == "live"
        assert result["count"] == 2
        # newest first
        assert result["entries"][0]["type"] == "Schedule"
        assert result["entries"][0]["timestamp"] == "2026-07-02T10:00:05"
        # leading indentation tabs stripped
        assert result["entries"][1]["message"] == "older line"

    def test_live_path_handles_string_fallback(self, handler):
        handler.data_provider.get_event_log_list.return_value = ["a raw line"]
        result = handler.query_event_log()
        assert result["source"] == "live"
        assert result["entries"][0]["message"] == "a raw line"


class TestOccurrence:
    def test_second_most_recent(self, handler):
        result = handler.investigate_event(device_id=1000111, occurrence=2)
        assert result["target_event"]["timestamp"] == "2026-06-30T23:00:00"

    def test_datetime_object_direct(self, handler):
        # correlator accepts datetime via handler ISO string only; sanity-check
        # the reader window helper with a datetime directly
        entries = handler.reader.entries_around(
            datetime.datetime(2026, 7, 1, 6, 0, 1), 60, 5
        )
        assert entries
