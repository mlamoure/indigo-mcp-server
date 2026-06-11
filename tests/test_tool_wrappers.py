"""
Contract tests for ToolWrappers.

These pin the wrapper-layer behavior that the MCP dispatch relies on:
- every wrapper returns a JSON string,
- handler exceptions become {"error": ...} payloads (never raise),
- per-tool extra error fields (query, device_type) are preserved,
- get_*_by_id None results become "not found" errors,
- and crucially: calling a wrapper with a wrong keyword argument raises
  TypeError OUT of the wrapper — mcp_handler routes that TypeError to an
  MCP "Tool Execution Error" (isError) result so the model can self-correct.
"""

import json
import pytest
from unittest.mock import Mock
import sys
from pathlib import Path

# Add plugin to path
plugin_path = Path(__file__).parent.parent / "MCP Server.indigoPlugin/Contents/Server Plugin"
sys.path.insert(0, str(plugin_path))

from mcp_server.tool_wrappers import ToolWrappers


def make_wrappers(**overrides):
    """Build a ToolWrappers with Mock handlers (override any by name)."""
    kwargs = dict(
        search_handler=Mock(),
        get_devices_by_type_handler=Mock(),
        device_control_handler=Mock(),
        rgb_control_handler=Mock(),
        thermostat_control_handler=Mock(),
        variable_control_handler=Mock(),
        action_control_handler=Mock(),
        historical_analysis_handler=Mock(),
        list_handlers=Mock(),
        log_query_handler=Mock(),
        plugin_control_handler=Mock(),
        data_provider=Mock(),
        subscription_handler=Mock(),
        logger=Mock(),
    )
    kwargs.update(overrides)
    return ToolWrappers(**kwargs)


class TestReturnContract:
    """Every wrapper returns a JSON string."""

    def test_success_returns_json_string(self):
        wrappers = make_wrappers()
        wrappers.device_control_handler.turn_on.return_value = {"success": True, "device_id": 1}

        result = wrappers.tool_device_turn_on(1)

        assert isinstance(result, str)
        assert json.loads(result) == {"success": True, "device_id": 1}

    def test_all_simple_wrappers_return_json_string(self):
        wrappers = make_wrappers()
        calls = [
            (wrappers.tool_device_turn_on, (1,)),
            (wrappers.tool_device_turn_off, (1,)),
            (wrappers.tool_device_set_brightness, (1, 0.5)),
            (wrappers.tool_device_set_rgb_color, (1, 255, 0, 0)),
            (wrappers.tool_device_set_rgb_percent, (1, 100.0, 0.0, 0.0)),
            (wrappers.tool_device_set_hex_color, (1, "#ff0000")),
            (wrappers.tool_device_set_named_color, (1, "red")),
            (wrappers.tool_device_set_white_levels, (1,)),
            (wrappers.tool_thermostat_set_heat_setpoint, (1, 68.0)),
            (wrappers.tool_thermostat_set_cool_setpoint, (1, 75.0)),
            (wrappers.tool_thermostat_set_hvac_mode, (1, "heat")),
            (wrappers.tool_thermostat_set_fan_mode, (1, "auto")),
            (wrappers.tool_variable_update, (1, "x")),
            (wrappers.tool_variable_create, ("name",)),
            (wrappers.tool_action_execute_group, (1,)),
            (wrappers.tool_analyze_historical_data, ("q", ["d"])),
            (wrappers.tool_list_devices, ()),
            (wrappers.tool_list_variables, ()),
            (wrappers.tool_list_action_groups, ()),
            (wrappers.tool_list_variable_folders, ()),
            (wrappers.tool_query_event_log, ()),
            (wrappers.tool_list_plugins, ()),
            (wrappers.tool_get_plugin_by_id, ("a.b",)),
            (wrappers.tool_restart_plugin, ("a.b",)),
            (wrappers.tool_get_plugin_status, ("a.b",)),
            (wrappers.tool_list_event_subscriptions, ()),
            (wrappers.tool_delete_event_subscription, ("01ABC",)),
            (wrappers.resource_list_devices, ()),
            (wrappers.resource_list_variables, ()),
            (wrappers.resource_list_actions, ()),
        ]
        for fn, args in calls:
            result = fn(*args)
            assert isinstance(result, str), f"{fn.__name__} did not return str"
            json.loads(result)  # must be valid JSON


class TestErrorContract:
    """Handler exceptions become {"error": ...} payloads, never raise."""

    def test_handler_exception_becomes_error_payload(self):
        wrappers = make_wrappers()
        wrappers.device_control_handler.turn_on.side_effect = RuntimeError("boom")

        payload = json.loads(wrappers.tool_device_turn_on(1))

        assert payload["error"] == "boom"

    def test_search_error_preserves_query(self):
        wrappers = make_wrappers()
        wrappers.search_handler.search.side_effect = RuntimeError("index down")

        payload = json.loads(wrappers.tool_search_entities("kitchen"))

        assert payload["error"] == "index down"
        assert payload["query"] == "kitchen"

    def test_get_devices_by_type_error_preserves_device_type(self):
        wrappers = make_wrappers()
        wrappers.get_devices_by_type_handler.get_devices.side_effect = RuntimeError("nope")

        payload = json.loads(wrappers.tool_get_devices_by_type("dimmer"))

        assert payload["error"] == "nope"
        assert payload["device_type"] == "dimmer"

    def test_invalid_device_type_error_includes_suggestions_context(self):
        wrappers = make_wrappers()

        payload = json.loads(wrappers.tool_search_entities("x", device_types=["dimmmer"]))

        assert "Invalid device types" in payload["error"]
        assert payload["query"] == "x"
        wrappers.search_handler.search.assert_not_called()

    def test_invalid_entity_type_rejected(self):
        wrappers = make_wrappers()

        payload = json.loads(wrappers.tool_search_entities("x", entity_types=["bogus"]))

        assert "Invalid entity types" in payload["error"]
        wrappers.search_handler.search.assert_not_called()


class TestNotFoundContract:
    """get_*_by_id / resource_get_* None results become not-found errors."""

    def test_get_device_by_id_not_found(self):
        wrappers = make_wrappers()
        wrappers.data_provider.get_device.return_value = None

        payload = json.loads(wrappers.tool_get_device_by_id(42))

        assert "not found" in payload["error"]

    def test_get_variable_by_id_not_found(self):
        wrappers = make_wrappers()
        wrappers.data_provider.get_variable.return_value = None

        payload = json.loads(wrappers.tool_get_variable_by_id(42))

        assert "not found" in payload["error"]

    def test_get_action_group_by_id_not_found(self):
        wrappers = make_wrappers()
        wrappers.data_provider.get_action_group.return_value = None

        payload = json.loads(wrappers.tool_get_action_group_by_id(42))

        assert "not found" in payload["error"]

    def test_resource_get_device_coerces_string_id(self):
        wrappers = make_wrappers()
        wrappers.data_provider.get_device.return_value = {"id": 42}

        payload = json.loads(wrappers.resource_get_device("42"))

        wrappers.data_provider.get_device.assert_called_once_with(42)
        assert payload == {"id": 42}


class TestTypeErrorEscapes:
    """Wrong keyword arguments must raise TypeError OUT of the wrapper.

    mcp_handler._handle_tools_call catches TypeError/ValueError from the
    call site and produces an MCP isError tool result; if the wrapper
    swallowed it the model would lose its self-correction signal.
    """

    def test_unknown_kwarg_raises_typeerror(self):
        wrappers = make_wrappers()

        with pytest.raises(TypeError):
            wrappers.tool_device_turn_on(device_idd=1)

    def test_missing_required_arg_raises_typeerror(self):
        wrappers = make_wrappers()

        with pytest.raises(TypeError):
            wrappers.tool_thermostat_set_heat_setpoint(device_id=1)
