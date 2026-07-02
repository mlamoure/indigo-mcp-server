"""
Tests for the .indiDb XML parser (mcp_server/adapters/indidb/parser.py).
"""

import sys
from pathlib import Path

import pytest

plugin_path = Path(__file__).parent.parent / "MCP Server.indigoPlugin/Contents/Server Plugin"
sys.path.insert(0, str(plugin_path))

from mcp_server.adapters.indidb.parser import parse_indidb, decode_element  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "sample_indidb.xml"


@pytest.fixture(scope="module")
def parsed():
    return parse_indidb(str(FIXTURE))


class TestParseCounts:
    def test_structure_counts(self, parsed):
        assert parsed.counts() == {"triggers": 3, "schedules": 1, "action_groups": 2}

    def test_name_maps(self, parsed):
        assert parsed.device_names == {
            1000111: "Porch Light",
            1000222: "Front Door Sensor",
            1000333: "Living Room Sonos",
        }
        assert parsed.variable_names == {2000888: "isDaytime", 2000999: "houseMode"}


class TestDecoding:
    def test_trigger_scalar_types(self, parsed):
        trigger = parsed.triggers[4000001]
        assert trigger["Name"] == "Front door opens at night"
        assert trigger["Enabled"] is True
        assert trigger["Class"] == 501
        assert trigger["DeviceID"] == 1000222
        assert trigger["DeviceStateSelector"] == "onOffState"

    def test_nested_action_steps(self, parsed):
        steps = parsed.triggers[4000001]["ActionGroup"]["ActionSteps"]
        assert len(steps) == 3
        assert steps[0]["Class"] == 1
        assert steps[1] == {
            "Class": 201,
            "DelayAction": True,
            "DelayAmount": 5,
            "ObjVers": 14,
            "ReplaceExistingDelayedAction": True,
            "VarAction": 0,
            "VarID": 2000999,
            "VarValue": "true",
        }
        assert steps[2]["ActionGroupID"] == 3000002

    def test_condition_tree(self, parsed):
        condition = parsed.triggers[4000001]["Condition"]
        assert condition["Type"] == 100
        items = condition["ConditionList"]["Conditions"]
        assert [item["Type"] for item in items] == [3, 5, 7, 12]
        assert condition["ConditionList"]["Logic"] == 1

    def test_plugin_meta_props(self, parsed):
        trigger = parsed.triggers[4000002]
        assert trigger["PluginID"] == "com.example.camera"
        assert trigger["MetaProps"]["com.example.camera"]["cameraDevice"] == "1000333"
        assert trigger["MetaProps"]["com.example.camera"]["sensitivity"] == 7

    def test_multiline_script_source(self, parsed):
        steps = parsed.triggers[4000003]["ActionGroup"]["ActionSteps"]
        assert "indigo.server.log" in steps[0]["ScriptSource"]

    def test_unknown_action_class_passes_through(self, parsed):
        steps = parsed.action_groups[3000002]["ActionSteps"]
        unknown = steps[1]
        assert unknown["Class"] == 47
        assert unknown["MysteryField"] == "future format"

    def test_schedule_fields(self, parsed):
        sched = parsed.schedules[5000001]
        assert sched["Name"] == "Run Goodnight at Sunset"
        assert sched["TimeType"] == 2
        assert sched["DateType"] == 0
        assert sched["ActionGroup"]["ActionSteps"][0]["ActionGroupID"] == 3000002


class TestDecodeElement:
    def test_unknown_type_with_children_decodes_as_dict(self):
        import xml.etree.ElementTree as ET

        elem = ET.fromstring("<Thing><A type='integer'>5</A></Thing>")
        assert decode_element(elem) == {"A": 5}

    def test_bad_integer_falls_back_to_text(self):
        import xml.etree.ElementTree as ET

        elem = ET.fromstring("<N type='integer'>not-a-number</N>")
        assert decode_element(elem) == "not-a-number"


class TestMalformedFile:
    def test_malformed_xml_raises(self, tmp_path):
        bad = tmp_path / "torn.indiDb"
        bad.write_text("<?xml version='1.0'?><Database type='dict'><TriggerList type='vec")
        with pytest.raises(Exception):
            parse_indidb(str(bad))
