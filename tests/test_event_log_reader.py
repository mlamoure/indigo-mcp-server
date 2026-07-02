"""
Tests for the daily Events.txt reader (file selection, parsing, filtering).
"""

import datetime
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

plugin_path = Path(__file__).parent.parent / "MCP Server.indigoPlugin/Contents/Server Plugin"
sys.path.insert(0, str(plugin_path))

from mcp_server.tools.log_search.event_log_reader import (  # noqa: E402
    EventLogReader,
    parse_log_line,
)

LOGS_DIR = Path(__file__).parent / "fixtures" / "event_logs"


@pytest.fixture
def reader():
    return EventLogReader(logs_folder_supplier=lambda: str(LOGS_DIR), logger=Mock())


class TestParseLogLine:
    def test_standard_line(self):
        entry = parse_log_line("2026-07-01 06:00:00.000\tTrigger\tFront door opens at night\n")
        assert entry.timestamp == datetime.datetime(2026, 7, 1, 6, 0, 0)
        assert entry.type == "Trigger"
        assert entry.message == "Front door opens at night"

    def test_message_containing_tabs_is_preserved(self):
        entry = parse_log_line("2026-07-01 06:00:00.000\tScript\ta\tb\tc\n")
        assert entry.message == "a\tb\tc"

    def test_continuation_line_returns_none(self):
        assert parse_log_line("Traceback (most recent call last):\n") is None

    def test_line_without_type_column(self):
        entry = parse_log_line("2026-07-01 06:00:00.000\tjust a message\n")
        assert entry.type is None
        assert entry.message == "just a message"


class TestReadDay:
    def test_continuation_lines_attach_to_previous(self, reader):
        entries = reader.read_day(str(LOGS_DIR / "2026-06-30 Events.txt"))
        error_entry = next(e for e in entries if e.type == "Example Plugin Error")
        assert "Traceback" in error_entry.message
        assert 'File "plugin.py"' in error_entry.message

    def test_chronological_order(self, reader):
        entries = reader.read_day(str(LOGS_DIR / "2026-06-30 Events.txt"))
        stamps = [e.timestamp for e in entries]
        assert stamps == sorted(stamps)


class TestSearch:
    def test_newest_first_across_files(self, reader):
        result = reader.search(query="Porch Light")
        stamps = [e["timestamp"] for e in result["entries"]]
        assert stamps == sorted(stamps, reverse=True)
        assert stamps[0].startswith("2026-07-01")

    def test_type_filter(self, reader):
        result = reader.search(types=["Action Group"])
        assert result["count"] == 2
        assert all(e["type"] == "Action Group" for e in result["entries"])

    def test_time_range(self, reader):
        result = reader.search(
            start_time=datetime.datetime(2026, 6, 30, 22, 0),
            end_time=datetime.datetime(2026, 6, 30, 23, 30),
        )
        assert result["count"] == 3  # camera trigger, plugin error, porch off

    def test_regex(self, reader):
        result = reader.search(query=r"status update is (on|off)", regex=True)
        assert result["count"] == 3

    def test_invalid_regex_is_error(self, reader):
        assert "error" in reader.search(query="[", regex=True)

    def test_limit_offset(self, reader):
        all_matches = reader.search(query="Porch Light")
        page = reader.search(query="Porch Light", limit=1, offset=1)
        assert page["count"] == 1
        assert page["entries"][0] == all_matches["entries"][1]

    def test_missing_folder_degrades(self):
        reader = EventLogReader(logs_folder_supplier=lambda: None, logger=Mock())
        result = reader.search(query="anything")
        assert result["entries"] == []
        assert result["files_scanned"] == 0


class TestEntriesAround:
    def test_window_and_types(self, reader):
        center = datetime.datetime(2026, 6, 30, 21, 59, 33, 400000)
        entries = reader.entries_around(
            center, lookback_seconds=60, lookahead_seconds=5,
            types=["Trigger", "Schedule", "Action Group"],
        )
        names = [e.message for e in entries]
        assert names == ["Run Goodnight at Sunset", "Goodnight", "Evening Scene"]

    def test_cross_midnight_window(self, reader):
        center = datetime.datetime(2026, 7, 1, 0, 0, 30)
        entries = reader.entries_around(center, lookback_seconds=7200, lookahead_seconds=0)
        assert any(e.timestamp.date() == datetime.date(2026, 6, 30) for e in entries)
