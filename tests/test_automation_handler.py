"""
Tests for the automation introspection handler and explain renderer,
using a Mock data provider plus the real structure store over the fixture.
"""

import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

plugin_path = Path(__file__).parent.parent / "MCP Server.indigoPlugin/Contents/Server Plugin"
sys.path.insert(0, str(plugin_path))

from mcp_server.adapters.indidb.store import IndiDbStructureStore  # noqa: E402
from mcp_server.tools.automation.automation_handler import AutomationHandler  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "sample_indidb.xml"

LIVE_TRIGGER = {
    "id": 4000001,
    "name": "Front door opens at night",
    "description": "",
    "enabled": True,
    "folderId": 7000001,
    "folderName": "Security",
    "type": "device_state_change",
    "deviceId": 1000222,
    "stateSelector": "onOffState",
    "stateChangeType": "becomes_true",
    "stateValue": "",
}

LIVE_SCHEDULE = {
    "id": 5000001,
    "name": "Run Goodnight at Sunset",
    "description": "",
    "enabled": True,
    "folderId": 0,
    "type": "schedule",
    "date_type": "every_day",
    "time_type": "sunset",
    "sun_delta_seconds": 0,
    "randomize_by_seconds": 0,
    "auto_delete": False,
    "next_execution": "2026-07-02T20:41:00",
    "absolute_time": None,
    "absolute_date": None,
}


@pytest.fixture
def data_provider():
    provider = Mock()
    provider.get_trigger.return_value = dict(LIVE_TRIGGER)
    provider.get_schedule.return_value = dict(LIVE_SCHEDULE)
    provider.get_action_group.return_value = {
        "id": 3000001, "name": "Evening Scene", "description": "", "folderId": 0
    }
    provider.get_all_triggers.return_value = [dict(LIVE_TRIGGER)]
    provider.get_all_schedules.return_value = [dict(LIVE_SCHEDULE)]
    provider.get_dependencies.return_value = {
        "triggers": [], "schedules": [], "action_groups": [],
        "devices": [], "variables": [], "control_pages": [],
    }
    return provider


@pytest.fixture
def handler(data_provider):
    store = IndiDbStructureStore(db_path_supplier=lambda: str(FIXTURE), logger=Mock())
    return AutomationHandler(
        data_provider=data_provider, structure_store=store, logger=Mock()
    )


class TestGetDetails:
    def test_trigger_explained(self, handler):
        doc = handler.get_details("trigger", 4000001)

        assert doc["name"] == "Front door opens at night"
        assert doc["enabled"] is True

        event = doc["trigger_event"]
        assert event["kind"] == "device_state_change"
        assert event["device"] == {"id": 1000222, "name": "Front Door Sensor"}
        assert event["change_type"] == "becomes_true"

        conditions = doc["conditions"]
        assert conditions["type"] == "condition_list"
        assert conditions["logic"] == "and"
        kinds = [item["kind"] for item in conditions["items"]]
        assert kinds == [
            "variable_compare", "time_date_compare", "device_state_compare", "condition_type_12"
        ]
        var_cond = conditions["items"][0]
        assert var_cond["variable"] == {"id": 2000888, "name": "isDaytime"}
        assert var_cond["comparison"] == "is_false"
        time_cond = conditions["items"][1]
        assert time_cond["start_time"] == "22:00:00"
        assert time_cond["end_time"] == "06:00:00"
        dev_cond = conditions["items"][2]
        assert dev_cond["device"] == {"id": 1000111, "name": "Porch Light"}
        assert dev_cond["state"] == "onOffState"

        steps = doc["action_steps"]
        assert [step["kind"] for step in steps] == [
            "device_action", "variable_action", "execute_action_group"
        ]
        assert steps[0]["device"] == {"id": 1000111, "name": "Porch Light"}
        assert steps[0]["command"] == "turn_on"
        assert steps[1]["variable"] == {"id": 2000999, "name": "houseMode"}
        assert steps[1]["value"] == "true"
        assert steps[1]["delay_seconds"] == 5
        assert steps[2]["action_group"] == {"id": 3000002, "name": "Goodnight"}

        assert doc["meta"]["structure_available"] is True
        assert doc["meta"]["structure_stale"] is False

    def test_schedule_explained(self, handler):
        doc = handler.get_details("schedule", 5000001)
        assert doc["next_execution"] == "2026-07-02T20:41:00"
        timing = doc["schedule_timing"]
        assert timing["date_type"] == "every_day"
        assert timing["time_type"] == "sunset"
        assert doc["action_steps"][0]["action_group"] == {"id": 3000002, "name": "Goodnight"}
        assert doc["conditions"]["items"][0]["variable"]["name"] == "isDaytime"

    def test_action_group_explained(self, handler):
        doc = handler.get_details("action_group", 3000001)
        steps = doc["action_steps"]
        assert [step["kind"] for step in steps] == [
            "device_action", "plugin_action", "embedded_script"
        ]
        plugin_step = steps[1]
        assert plugin_step["plugin_id"] == "com.example.sonos"
        assert plugin_step["action_label"] == "Sonos: Play"
        assert plugin_step["config"]["mode"] == "Play Now"
        script_step = steps[2]
        assert script_step["script_source"] == 'indigo.server.log("evening scene ran")'
        assert script_step["script_truncated"] is False

    def test_unknown_action_class_renders_unknown(self, handler, data_provider):
        data_provider.get_action_group.return_value = {
            "id": 3000002, "name": "Goodnight", "description": "", "folderId": 0
        }
        doc = handler.get_details("action_group", 3000002)
        unknown = doc["action_steps"][1]
        assert unknown["kind"] == "action_class_47"
        assert unknown["raw"]["MysteryField"] == "future format"

    def test_include_scripts_false(self, handler, data_provider):
        data_provider.get_action_group.return_value = {
            "id": 3000001, "name": "Evening Scene", "description": "", "folderId": 0
        }
        doc = handler.get_details("action_group", 3000001, include_scripts=False)
        script_step = doc["action_steps"][2]
        assert "script_source" not in script_step
        assert script_step["script_first_line"].startswith("indigo.server.log")

    def test_plugin_trigger_config_from_xml(self, handler, data_provider):
        data_provider.get_trigger.return_value = {
            "id": 4000002, "name": "Camera sees a person", "description": "",
            "enabled": False, "folderId": 0, "type": "plugin_event",
            "pluginId": "com.example.camera", "pluginTypeId": "cameramotion",
        }
        doc = handler.get_details("trigger", 4000002)
        event = doc["trigger_event"]
        assert event["kind"] == "plugin_event"
        assert event["plugin_id"] == "com.example.camera"
        assert event["config"]["sensitivity"] == 7

    def test_stale_name_flag(self, handler, data_provider):
        renamed = dict(LIVE_TRIGGER, name="Renamed just now")
        data_provider.get_trigger.return_value = renamed
        doc = handler.get_details("trigger", 4000001)
        assert doc["meta"]["structure_stale"] is True

    def test_not_found(self, handler, data_provider):
        data_provider.get_trigger.return_value = None
        result = handler.get_details("trigger", 424242)
        assert "error" in result

    def test_invalid_entity_type(self, handler):
        result = handler.get_details("widget", 1)
        assert "error" in result

    def test_structure_missing_but_live_present(self, handler, data_provider):
        fresh = dict(LIVE_TRIGGER, id=999999999)
        data_provider.get_trigger.return_value = fresh
        doc = handler.get_details("trigger", 999999999)
        assert doc["meta"]["structure_available"] is False
        assert "action_steps" not in doc


class TestListTriggers:
    def test_watching_summary(self, handler):
        result = handler.list_triggers()
        assert result["count"] == 1
        trigger = result["triggers"][0]
        assert 'device "Front Door Sensor"' in trigger["watching"]
        assert "becomes_true" in trigger["watching"]

    def test_filters(self, handler, data_provider):
        data_provider.get_all_triggers.return_value = [
            dict(LIVE_TRIGGER),
            {"id": 2, "name": "Other", "enabled": False, "folderId": 0,
             "type": "server_startup", "description": ""},
        ]
        assert handler.list_triggers(enabled_only=True)["count"] == 1
        assert handler.list_triggers(name_contains="other")["count"] == 1
        assert handler.list_triggers(trigger_type="server_startup")["count"] == 1
        assert handler.list_triggers(folder_id=7000001)["count"] == 1

    def test_pagination(self, handler, data_provider):
        data_provider.get_all_triggers.return_value = [
            {"id": i, "name": f"T{i:03d}", "enabled": True, "folderId": 0,
             "type": "server_startup", "description": ""}
            for i in range(10)
        ]
        page = handler.list_triggers(limit=3, offset=8)
        assert page["count"] == 2
        assert page["total_count"] == 10
        assert page["has_more"] is False


class TestListSchedules:
    def test_timing_summary_and_sort(self, handler, data_provider):
        data_provider.get_all_schedules.return_value = [
            dict(LIVE_SCHEDULE, id=1, name="B", next_execution=None),
            dict(LIVE_SCHEDULE, id=2, name="A", next_execution="2026-07-03T09:00:00"),
        ]
        result = handler.list_schedules()
        # next_execution=None sorts last
        assert [s["id"] for s in result["schedules"]] == [2, 1]
        assert result["schedules"][0]["timing_summary"] == "every day at sunset"

    def test_sunset_delta_summary(self, handler):
        summary = handler._schedule_timing_summary(
            dict(LIVE_SCHEDULE, sun_delta_seconds=-1200)
        )
        assert summary == "every day at sunset -20m"


class TestFindReferences:
    def test_names_and_sources(self, handler):
        result = handler.find_references("device", 1000111, include_server_check=False)
        assert result["target"]["name"] == "Porch Light"
        by_id = {(r["entity_type"], r["id"], r["role"]): r for r in result["references"]}
        direct = by_id[("action_group", 3000001, "acts_on")]
        assert direct["name"] == "Evening Scene"
        assert direct["source"] == "database_file"
        chained = next(
            r for r in result["references"]
            if r["entity_type"] == "schedule" and r.get("via_action_groups")
        )
        assert chained["via_action_groups"][0]["name"] == "Goodnight"

    def test_server_merge_adds_and_marks(self, handler, data_provider):
        data_provider.get_dependencies.return_value = {
            "triggers": [{"id": 4000001, "name": "Front door opens at night"}],
            "schedules": [],
            "action_groups": [],
            "devices": [],
            "variables": [],
            "control_pages": [{"id": 6000001, "name": "Wall Panel"}],
        }
        result = handler.find_references("device", 1000111)
        sources = {
            (r["entity_type"], r["id"]): r["source"] for r in result["references"]
        }
        assert sources[("trigger", 4000001)] == "database_file+server"
        assert sources[("control_page", 6000001)] == "server"

    def test_server_error_degrades_with_note(self, handler, data_provider):
        data_provider.get_dependencies.return_value = {"error": "server busy"}
        result = handler.find_references("device", 1000111)
        assert any("server busy" in note for note in result["notes"])
        assert result["count"] > 0

    def test_invalid_entity_type(self, handler):
        assert "error" in handler.find_references("trigger", 4000001)
