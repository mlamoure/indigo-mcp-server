"""
Comprehensive tests for refactored MCP handler.

Tests that mcp_handler.py with its extracted modules (tool_registry,
tool_wrappers) registers exactly the companion tool set: the tools Indigo
2026.1's built-in MCP Control does not provide. Device control, variable
writes, plain listings/lookups and plugin management are MCP Control's, and
must never be registered here.
"""

import json
import os
import pytest
from unittest.mock import Mock, patch
import sys
from pathlib import Path

# Add plugin to path
plugin_path = Path(__file__).parent.parent / "MCP Advanced Tools.indigoPlugin/Contents/Server Plugin"
sys.path.insert(0, str(plugin_path))

from mcp_server.mcp_handler import MCPHandler
from mcp_server.tool_registry import (
    MCP_CONTROL_EQUIVALENTS,
    MOVED_TO_PLUGINS,
    WRITE_TOOLS,
    get_tool_schemas,
    removed_tool_hint,
)
from mcp_server.tool_wrappers import ToolWrappers

# Always registered
STATIC_TOOLS = {
    "search_entities",
    "list_triggers",
    "list_schedules",
    "get_trigger_details",
    "get_schedule_details",
    "get_action_group_details",
    "find_automation_references",
    "investigate_event",
    "query_event_log",
    "control_trigger",
    "control_schedule",
    "control_action_group",
    "update_trigger",
    "update_schedule",
    "update_action_group",
    "manage_tags",
    "tag_objects",
}

# Registered only when event webhooks are enabled
WEBHOOK_TOOLS = {
    "create_event_subscription",
    "list_event_subscriptions",
    "delete_event_subscription",
}

# Removed in the 2026.1 companion beta: Indigo's MCP Control provides them
REMOVED_TOOLS = {
    "get_devices_by_type",
    "device_turn_on",
    "device_turn_off",
    "device_set_brightness",
    "device_set_rgb_color",
    "device_set_rgb_percent",
    "device_set_hex_color",
    "device_set_named_color",
    "device_set_white_levels",
    "thermostat_set_heat_setpoint",
    "thermostat_set_cool_setpoint",
    "thermostat_set_hvac_mode",
    "thermostat_set_fan_mode",
    "variable_update",
    "variable_create",
    "action_execute_group",
    "list_devices",
    "list_variables",
    "list_action_groups",
    "list_variable_folders",
    "get_devices_by_state",
    "get_device_by_id",
    "get_variable_by_id",
    "get_action_group_by_id",
    "list_plugins",
    "get_plugin_by_id",
    "restart_plugin",
    "get_plugin_status",
}

# Moved to another plugin (the Grafana Home Dashboard plugin provides history)
MOVED_TOOLS = {"analyze_historical_data"}


def make_handler(mock_vsm, **kwargs):
    """Create an MCPHandler with a mocked vector store manager."""
    mock_vsm_instance = Mock()
    mock_vsm_instance.get_vector_store = Mock(return_value=Mock())
    mock_vsm_instance.start = Mock()
    mock_vsm.return_value = mock_vsm_instance

    os.environ['DB_FILE'] = '/tmp/test_db'
    return MCPHandler(data_provider=Mock(), logger=Mock(), **kwargs)


def make_wrappers(**overrides):
    """Build a ToolWrappers with Mock handlers (override any by name)."""
    kwargs = dict(
        search_handler=Mock(),
        automation_handler=Mock(),
        log_search_handler=Mock(),
        subscription_handler=Mock(),
        logger=Mock(),
    )
    kwargs.update(overrides)
    return ToolWrappers(**kwargs)


class TestToolSet:
    """The registered tool set is exactly the companion scope."""

    def test_expected_counts(self):
        assert len(STATIC_TOOLS) == 17
        assert len(STATIC_TOOLS | WEBHOOK_TOOLS) == 20
        assert len(REMOVED_TOOLS) == 28
        assert not (STATIC_TOOLS | WEBHOOK_TOOLS) & (REMOVED_TOOLS | MOVED_TOOLS)

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_exactly_20_tools_with_webhooks_and_none_removed(self, mock_vsm):
        handler = make_handler(mock_vsm, subscription_handler=Mock())

        names = set(handler._tools)

        assert names == STATIC_TOOLS | WEBHOOK_TOOLS
        assert not names & (REMOVED_TOOLS | MOVED_TOOLS)

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_exactly_17_tools_without_webhooks(self, mock_vsm):
        handler = make_handler(mock_vsm)

        assert set(handler._tools) == STATIC_TOOLS

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_tools_list_names_match_registry(self, mock_vsm):
        handler = make_handler(mock_vsm, subscription_handler=Mock())

        response = handler._handle_tools_list(msg_id=1, params={})

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        tools = response["result"]["tools"]
        assert {t["name"] for t in tools} == STATIC_TOOLS | WEBHOOK_TOOLS
        for tool in tools:
            assert tool["description"]
            assert tool["inputSchema"]["type"] == "object"

    def test_registry_builds_exactly_the_kept_tools(self):
        tool_functions = {name: Mock() for name in STATIC_TOOLS | WEBHOOK_TOOLS}

        tools = get_tool_schemas(tool_functions)

        assert set(tools) == STATIC_TOOLS | WEBHOOK_TOOLS
        for tool_def in tools.values():
            assert "description" in tool_def
            assert "inputSchema" in tool_def
            assert tool_def["function"] is not None

    def test_registry_omits_webhook_tools_when_not_supplied(self):
        tools = get_tool_schemas({name: Mock() for name in STATIC_TOOLS})

        assert set(tools) == STATIC_TOOLS

    def test_write_tools_are_all_kept_tools(self):
        assert WRITE_TOOLS <= STATIC_TOOLS | WEBHOOK_TOOLS
        assert not WRITE_TOOLS & REMOVED_TOOLS

    def test_no_wrapper_left_for_removed_tools(self):
        wrappers = make_wrappers()

        for name in REMOVED_TOOLS | MOVED_TOOLS:
            assert not hasattr(wrappers, f"tool_{name}"), name

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_registered_functions_are_callable(self, mock_vsm):
        handler = make_handler(mock_vsm, subscription_handler=Mock())

        for tool_name, tool_def in handler._tools.items():
            assert callable(tool_def["function"]), tool_name


class TestRemovedToolHints:
    """A call to a removed tool names its Indigo MCP Control replacement."""

    def test_every_removed_tool_has_an_equivalent(self):
        assert set(MCP_CONTROL_EQUIVALENTS) == REMOVED_TOOLS
        assert set(MOVED_TO_PLUGINS) == MOVED_TOOLS

    def test_history_hint_names_the_grafana_plugin_tool(self):
        hint = removed_tool_hint("analyze_historical_data")

        assert "`influxlog_query_history`" in hint
        assert "Grafana Home Dashboard" in hint

    def test_hint_names_the_equivalent_and_endpoint(self):
        hint = removed_tool_hint("device_turn_on")

        assert "`turn_on`" in hint
        assert "/v3/api/mcp" in hint

    def test_action_group_hint_mentions_confirm(self):
        hint = removed_tool_hint("action_execute_group")

        assert "`execute_action_group`" in hint
        assert "`confirm`" in hint
        assert "delay_seconds" not in hint

    def test_never_our_tool_gets_no_hint(self):
        assert removed_tool_hint("no_such_tool") is None
        assert removed_tool_hint("search_entities") is None

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_tools_call_on_removed_tool_returns_the_hint(self, mock_vsm):
        handler = make_handler(mock_vsm)

        response = handler._handle_tools_call(
            msg_id=7, params={"name": "thermostat_set_heat_setpoint", "arguments": {}})

        assert response["error"]["code"] == -32602
        message = response["error"]["message"]
        assert message.startswith("Unknown tool: thermostat_set_heat_setpoint.")
        assert "`set_heat_setpoint`" in message

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_tools_call_on_unknown_tool_is_unchanged(self, mock_vsm):
        handler = make_handler(mock_vsm)

        response = handler._handle_tools_call(
            msg_id=8, params={"name": "no_such_tool", "arguments": {}})

        assert response["error"] == {"code": -32602, "message": "Unknown tool: no_such_tool"}


class TestRegistrySchemas:
    """Schema details the dispatcher and clients rely on."""

    def test_paginated_tools_have_limit_and_offset(self):
        tools = get_tool_schemas({name: Mock() for name in STATIC_TOOLS})

        for tool_name in ("search_entities", "list_triggers", "list_schedules"):
            properties = tools[tool_name]["inputSchema"]["properties"]
            assert properties["limit"]["type"] == "integer", tool_name
            assert properties["offset"]["type"] == "integer", tool_name
            assert properties["limit"]["minimum"] == 1, tool_name
            assert properties["limit"]["maximum"] == 500, tool_name
            assert properties["offset"]["minimum"] == 0, tool_name

    def test_control_tools_do_not_execute(self):
        """Running automations is MCP Control's job; the descriptions say where."""
        tools = get_tool_schemas({name: Mock() for name in STATIC_TOOLS})

        for name, mcp_control_tool in (
            ("control_trigger", "execute_trigger"),
            ("control_schedule", "execute_schedule"),
            ("control_action_group", "execute_action_group"),
        ):
            assert "execute" not in tools[name]["inputSchema"]["properties"]["action"]["enum"], name
            assert mcp_control_tool in tools[name]["description"], name

    def test_only_enable_capable_tools_take_timing(self):
        tools = get_tool_schemas({name: Mock() for name in STATIC_TOOLS})

        for name in ("control_trigger", "control_schedule"):
            props = tools[name]["inputSchema"]["properties"]
            assert {"delay_seconds", "duration_seconds"} <= set(props), name
        ag_props = tools["control_action_group"]["inputSchema"]["properties"]
        assert not {"delay_seconds", "duration_seconds"} & set(ag_props)


class TestWrapperErrors:
    def test_tool_wrappers_error_handling(self):
        """Handler exceptions become error payloads, not raised exceptions."""
        automation_handler = Mock()
        automation_handler.get_details = Mock(side_effect=Exception("Test error"))
        wrappers = make_wrappers(automation_handler=automation_handler)

        result = json.loads(wrappers.tool_get_trigger_details(trigger_id=12345))

        assert "error" in result
        assert "Test error" in result["error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
