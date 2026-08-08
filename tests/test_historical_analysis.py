"""
Tests for mcp_server.tools.historical_analysis — window resolution, numeric
summaries, frozen-sensor detection, and the change-log cap.
"""

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
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


# The handler reaches for ...adapters.data_provider and ...common.influxdb, so
# those packages have to exist before the relative imports resolve. conftest
# already stubs mcp_server / mcp_server.common / mcp_server.tools.
_stub_package("mcp_server", BASE)
_stub_package("mcp_server.common", BASE / "common")
_stub_package("mcp_server.tools", BASE / "tools")
_stub_package("mcp_server.adapters", BASE / "adapters")
_stub_package("mcp_server.tools.historical_analysis", BASE / "tools" / "historical_analysis")

_load_module_from_file(
    "mcp_server.adapters.data_provider", BASE / "adapters" / "data_provider.py"
)
_load_module_from_file(
    "mcp_server.common.log_style", BASE / "common" / "log_style.py"
)
_load_module_from_file(
    "mcp_server.tools.base_handler", BASE / "tools" / "base_handler.py"
)
_load_module_from_file(
    "mcp_server.common.influxdb.client", BASE / "common" / "influxdb" / "client.py"
)
_load_module_from_file(
    "mcp_server.common.influxdb.time_utils", BASE / "common" / "influxdb" / "time_utils.py"
)
queries_mod = _load_module_from_file(
    "mcp_server.common.influxdb.queries", BASE / "common" / "influxdb" / "queries.py"
)
_load_module_from_file(
    "mcp_server.common.influxdb.main", BASE / "common" / "influxdb" / "main.py"
)
_load_module_from_file(
    "mcp_server.common.influxdb", BASE / "common" / "influxdb" / "__init__.py"
)

historical_mod = _load_module_from_file(
    "mcp_server.tools.historical_analysis.main",
    BASE / "tools" / "historical_analysis" / "main.py",
)

HistoricalAnalysisHandler = historical_mod.HistoricalAnalysisHandler
InfluxDBQueryBuilder = queries_mod.InfluxDBQueryBuilder


@pytest.fixture
def handler():
    return HistoricalAnalysisHandler(data_provider=MagicMock())


def _records(values, start=None, step_minutes=15, key="sensorValue"):
    """Build InfluxDB-shaped records, oldest first, one per step."""
    start = start or datetime(2026, 8, 8, 0, 0, 0, tzinfo=timezone.utc)
    return [
        {
            "time": (start + timedelta(minutes=step_minutes * i)).strftime(
                "%Y-%m-%dT%H:%M:%S.%f"
            ),
            key: value,
        }
        for i, value in enumerate(values)
    ]


class TestResolveWindow:
    def test_hours_win_over_days(self, handler):
        assert handler._resolve_window(30, 4) == timedelta(hours=4)

    def test_days_used_when_no_hours(self, handler):
        assert handler._resolve_window(7, None) == timedelta(days=7)

    def test_defaults_to_thirty_days(self, handler):
        assert handler._resolve_window(None, None) == timedelta(days=30)

    def test_fractional_hours(self, handler):
        assert handler._resolve_window(None, 1.5) == timedelta(minutes=90)

    @pytest.mark.parametrize("hours", [4, 24, 8760])
    def test_accepted_windows_are_in_bounds(self, handler, hours):
        window = handler._resolve_window(None, hours)
        assert historical_mod._MIN_WINDOW <= window <= historical_mod._MAX_WINDOW

    @pytest.mark.parametrize("hours", [0.5, 8761])
    def test_out_of_bounds_windows_rejected(self, handler, hours):
        result = handler.analyze_historical_data(
            query="temperature", entity_names=["Kitchen"], time_range_hours=hours
        )
        assert result["success"] is False
        assert "1 hour and 365 days" in result["error"]


class TestFormatWindowLabel:
    @pytest.mark.parametrize(
        "window,expected",
        [
            (timedelta(hours=1), "the last 1 hour"),
            (timedelta(hours=4), "the last 4 hours"),
            (timedelta(hours=1.5), "the last 1.5 hours"),
            (timedelta(days=1), "the last 24 hours"),
            (timedelta(days=7), "the last 7 days"),
            (timedelta(days=30), "the last 30 days"),
        ],
    )
    def test_labels(self, handler, window, expected):
        assert handler._format_window_label(window) == expected


class TestSummarizeNumeric:
    def test_rising_series(self, handler):
        stats = handler._summarize_numeric([83.3, 84.8, 85.8, 86.2], "sensorValue")
        assert stats["current"] == 86.2
        assert stats["min"] == 83.3
        assert stats["max"] == 86.2
        assert stats["mean"] == pytest.approx(85.025)
        assert stats["trend"] == "rising"
        assert stats["sample_count"] == 4
        assert stats["distinct_count"] == 4

    def test_falling_series(self, handler):
        stats = handler._summarize_numeric([93.6, 90.1, 84.2], "sensorValue")
        assert stats["trend"] == "falling"
        assert stats["delta"] == pytest.approx(-9.4)

    def test_flat_series_is_steady(self, handler):
        stats = handler._summarize_numeric([69.1] * 5, "sensorValue")
        assert stats["trend"] == "steady"
        assert stats["distinct_count"] == 1

    def test_sub_noise_movement_is_steady(self, handler):
        stats = handler._summarize_numeric([70.0, 70.05], "sensorValue")
        assert stats["trend"] == "steady"

    def test_booleans_are_not_numeric(self, handler):
        assert handler._summarize_numeric([True, False, True], "onState") is None

    def test_strings_are_not_numeric(self, handler):
        assert handler._summarize_numeric(["on", "off", "on"], "state") is None

    def test_single_sample_returns_none(self, handler):
        assert handler._summarize_numeric([72.0], "sensorValue") is None

    def test_ignores_none_values(self, handler):
        stats = handler._summarize_numeric([70.0, None, 72.0], "sensorValue")
        assert stats["sample_count"] == 2
        assert stats["max"] == 72.0


class TestEntityReport:
    def test_numeric_device_gets_stats(self, handler):
        report = handler._build_entity_report(
            label="Kitchen Temperature.sensorValue",
            entity_name="Kitchen Temperature",
            property_name="sensorValue",
            records=_records([83.2, 84.1, 85.0]),
            value_key="sensorValue",
            window=timedelta(hours=4),
        )
        assert report["stats"]["trend"] == "rising"
        assert report["warning"] is None
        assert report["total_changes"] == 3
        assert report["truncated"] is False

    def test_onoff_device_gets_no_stats(self, handler):
        report = handler._build_entity_report(
            label="Living Room Lamp.onState",
            entity_name="Living Room Lamp",
            property_name="onState",
            records=_records([False, True, False], key="onState"),
            value_key="onState",
            window=timedelta(hours=4),
        )
        assert report["stats"] is None
        assert report["warning"] is None
        assert "was off for" in report["messages"][0]
        assert "is currently off" in report["messages"][-1]

    def test_narrative_is_capped_with_explicit_notice(self, handler):
        # Alternating values so every record is a distinct run
        values = [70.0 + (i % 2) for i in range(700)]
        report = handler._build_entity_report(
            label="Busy Sensor.sensorValue",
            entity_name="Busy Sensor",
            property_name="sensorValue",
            records=_records(values),
            value_key="sensorValue",
            window=timedelta(days=30),
        )
        assert report["total_changes"] == 700
        assert len(report["messages"]) == historical_mod._MAX_CHANGE_LINES
        assert report["truncated"] is True

    def test_cap_keeps_the_most_recent_lines(self, handler):
        values = [70.0 + (i % 2) for i in range(700)]
        report = handler._build_entity_report(
            label="Busy Sensor.sensorValue",
            entity_name="Busy Sensor",
            property_name="sensorValue",
            records=_records(values),
            value_key="sensorValue",
            window=timedelta(days=30),
        )
        assert "is currently" in report["messages"][-1]

    def test_empty_records_return_none(self, handler):
        assert (
            handler._build_entity_report(
                label="Nothing.sensorValue",
                entity_name="Nothing",
                property_name="sensorValue",
                records=[],
                value_key="sensorValue",
                window=timedelta(hours=4),
            )
            is None
        )


class TestFrozenSensorDetection:
    def test_flat_series_triggers_warning(self, handler):
        report = handler._build_entity_report(
            label="Living Room Temperature.sensorValue",
            entity_name="Living Room Temperature",
            property_name="sensorValue",
            records=_records([69.1] * 20),
            value_key="sensorValue",
            window=timedelta(hours=4),
        )
        assert report["warning"] is not None
        assert "did not change at all" in report["warning"]

    def test_changing_series_has_no_warning(self, handler):
        report = handler._build_entity_report(
            label="Kitchen Temperature.sensorValue",
            entity_name="Kitchen Temperature",
            property_name="sensorValue",
            records=_records([83.2] * 10 + [83.5] * 10),
            value_key="sensorValue",
            window=timedelta(hours=4),
        )
        assert report["warning"] is None

    def test_too_few_samples_has_no_warning(self, handler):
        report = handler._build_entity_report(
            label="Quiet.sensorValue",
            entity_name="Quiet",
            property_name="sensorValue",
            records=_records([70.0, 70.0]),
            value_key="sensorValue",
            window=timedelta(hours=4),
        )
        assert report["warning"] is None

    def test_warning_names_the_last_actual_change(self, handler):
        client = MagicMock()
        client.execute_query.return_value = [
            {"time": "2026-03-24T23:52:37.627214", "sensorValue": 70.0}
        ]

        report = handler._build_entity_report(
            label="Living Room Temperature.sensorValue",
            entity_name="Living Room Temperature",
            property_name="sensorValue",
            records=_records([69.1] * 20),
            value_key="sensorValue",
            window=timedelta(hours=4),
            client=client,
            query_builder=InfluxDBQueryBuilder(),
        )

        assert "Last actual change: 2026-03-24" in report["warning"]
        assert "likely offline" in report["warning"]

    def test_probe_failure_degrades_gracefully(self, handler):
        client = MagicMock()
        client.execute_query.side_effect = RuntimeError("influx down")

        report = handler._build_entity_report(
            label="Living Room Temperature.sensorValue",
            entity_name="Living Room Temperature",
            property_name="sensorValue",
            records=_records([69.1] * 20),
            value_key="sensorValue",
            window=timedelta(hours=4),
            client=client,
            query_builder=InfluxDBQueryBuilder(),
        )

        assert "did not change at all" in report["warning"]
        assert "may be offline" in report["warning"]


class TestStatsLine:
    def test_temperature_units_from_property_name(self, handler):
        stats = handler._summarize_numeric([83.3, 84.8, 85.8], "temperatureInput1")
        line = handler._format_stats_line(stats)
        assert "current 85.8°" in line
        assert "range 83.3°–85.8°" in line
        assert "rising" in line

    def test_device_unit_is_appended_to_bare_numbers(self, handler):
        stats = handler._summarize_numeric([83.3, 84.8, 85.8], "sensorValue")
        line = handler._format_stats_line(stats, unit="°F")
        assert "current 85.8 °F" in line
        assert "range 83.3 °F–85.8 °F" in line

    def test_device_unit_does_not_double_up(self, handler):
        stats = handler._summarize_numeric([83.3, 85.8], "temperatureInput1")
        line = handler._format_stats_line(stats, unit="°F")
        assert "°F" not in line
        assert "current 85.8°" in line

    def test_no_unit_leaves_bare_numbers(self, handler):
        stats = handler._summarize_numeric([83.0, 85.0], "sensorValue")
        assert handler._format_stats_line(stats) == (
            "current 85 | range 83–85 | mean 84 | rising"
        )

    def test_none_stats_yields_no_line(self, handler):
        assert handler._format_stats_line(None) is None


class TestPropertyUnit:
    def test_unit_read_from_ui_state(self, handler):
        handler.data_provider.get_all_devices.return_value = [
            {"name": "Living Room Temperature", "states": {"sensorValue.ui": "69.1 °F"}}
        ]
        assert handler._get_property_unit("Living Room Temperature", "sensorValue") == "°F"

    def test_word_units(self, handler):
        handler.data_provider.get_all_devices.return_value = [
            {"name": "Living Room Luminance", "states": {"sensorValue.ui": "57 lux"}}
        ]
        assert handler._get_property_unit("Living Room Luminance", "sensorValue") == "lux"

    def test_negative_values(self, handler):
        handler.data_provider.get_all_devices.return_value = [
            {"name": "Back Patio", "states": {"sensorValue.ui": "-4.5 °C"}}
        ]
        assert handler._get_property_unit("Back Patio", "sensorValue") == "°C"

    def test_unitless_ui_state(self, handler):
        handler.data_provider.get_all_devices.return_value = [
            {"name": "Counter", "states": {"sensorValue.ui": "42"}}
        ]
        assert handler._get_property_unit("Counter", "sensorValue") is None

    def test_unknown_device(self, handler):
        handler.data_provider.get_all_devices.return_value = []
        assert handler._get_property_unit("Nope", "sensorValue") is None

    def test_provider_failure_is_swallowed(self, handler):
        handler.data_provider.get_all_devices.side_effect = RuntimeError("boom")
        assert handler._get_property_unit("Whatever", "sensorValue") is None


class TestReportFormatting:
    def _report(self, handler, records, prop="sensorValue", name="Kitchen Temperature"):
        return handler._build_entity_report(
            label=f"{name}.{prop}",
            entity_name=name,
            property_name=prop,
            records=records,
            value_key=prop,
            window=timedelta(hours=4),
        )

    def test_stats_precede_the_change_log(self, handler):
        report = self._report(handler, _records([83.2, 84.1, 85.0]))
        stats = handler._calculate_summary_statistics(
            [report], ["Kitchen Temperature"], timedelta(hours=4), 1.0
        )
        text = handler._format_analysis_report(
            [report], ["Kitchen Temperature"], timedelta(hours=4), stats
        )

        assert "Analysis Period: the last 4 hours" in text
        assert text.index("current ") < text.index("  • ")

    def test_truncation_notice_is_explicit(self, handler):
        values = [70.0 + (i % 2) for i in range(700)]
        report = self._report(handler, _records(values))
        stats = handler._calculate_summary_statistics(
            [report], ["Kitchen Temperature"], timedelta(days=30), 1.0
        )
        text = handler._format_analysis_report(
            [report], ["Kitchen Temperature"], timedelta(days=30), stats
        )

        assert "showing the most recent 50 of 700 changes" in text

    def test_totals_count_every_change_not_just_shown(self, handler):
        values = [70.0 + (i % 2) for i in range(700)]
        report = self._report(handler, _records(values))
        stats = handler._calculate_summary_statistics(
            [report], ["Kitchen Temperature"], timedelta(days=30), 1.0
        )
        assert stats["total_state_changes"] == 700

    def test_onoff_report_has_no_stats_line(self, handler):
        report = self._report(
            handler, _records([False, True], key="onState"), prop="onState", name="Lamp"
        )
        stats = handler._calculate_summary_statistics(
            [report], ["Lamp"], timedelta(hours=4), 1.0
        )
        text = handler._format_analysis_report(
            [report], ["Lamp"], timedelta(hours=4), stats
        )

        assert "current " not in text
        assert "Lamp.onState was off for" in text


class TestDevicePropertyDiscovery:
    def test_real_states_are_not_padded_with_generic_fields(self, handler):
        handler.data_provider.get_all_devices.return_value = [
            {
                "id": 1,
                "name": "Living Room Temperature",
                "states": {"sensorValue": 69.1, "sensorValue.ui": "69.1 °F"},
            }
        ]
        props = handler._get_device_properties("Living Room Temperature")

        assert "sensorValue" in props
        assert "temperature" not in props
        assert "temperatureInput1" not in props

    def test_unknown_device_falls_back_to_generic_fields(self, handler):
        handler.data_provider.get_all_devices.return_value = []
        props = handler._get_device_properties("Nonexistent")
        assert props == historical_mod._ALTERNATIVE_FIELDS


class TestQueryBuilders:
    def test_variable_time_range_query(self):
        builder = InfluxDBQueryBuilder()
        start = datetime(2026, 8, 8, 12, 0, 0)
        end = datetime(2026, 8, 8, 16, 0, 0)
        query = builder.build_variable_time_range_query("Away Mode", start, end)

        assert 'SELECT "value" FROM "variable_changes"' in query
        assert "\"varname\" = 'Away Mode'" in query
        assert f"time >= {int(start.timestamp() * 1000)}ms" in query
        assert f"time <= {int(end.timestamp() * 1000)}ms" in query
        assert "ORDER BY time ASC" in query

    def test_last_different_value_query_numeric(self):
        builder = InfluxDBQueryBuilder()
        query = builder.build_last_different_value_query(
            "Living Room Temperature", "sensorValue", 69.1
        )

        assert '"sensorValue" != 69.1' in query
        assert "ORDER BY time DESC LIMIT 1" in query

    def test_last_different_value_query_string(self):
        builder = InfluxDBQueryBuilder()
        query = builder.build_last_different_value_query("Front Door", "state", "closed")
        assert "\"state\" != 'closed'" in query
