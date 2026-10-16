"""
Contract tests for ToolWrappers.

These pin the wrapper-layer behavior that the MCP dispatch relies on:
- every wrapper returns a JSON string,
- handler exceptions become {"error": ...} payloads (never raise),
- per-tool extra error fields (query) are preserved,
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
plugin_path = Path(__file__).parent.parent / "MCP Advanced Tools.indigoPlugin/Contents/Server Plugin"
sys.path.insert(0, str(plugin_path))

from mcp_server.tool_wrappers import ToolWrappers


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


class TestReturnContract:
    """Every wrapper returns a JSON string."""

    def test_success_returns_json_string(self):
        wrappers = make_wrappers()
        wrappers.automation_handler.get_details.return_value = {"id": 1, "name": "T"}

        result = wrappers.tool_get_trigger_details(1)

        assert isinstance(result, str)
        assert json.loads(result) == {"id": 1, "name": "T"}

    def test_all_simple_wrappers_return_json_string(self):
        wrappers = make_wrappers()
        calls = [
            (wrappers.tool_query_event_log, ()),
            (wrappers.tool_list_triggers, ()),
            (wrappers.tool_list_schedules, ()),
            (wrappers.tool_get_trigger_details, (1,)),
            (wrappers.tool_get_schedule_details, (1,)),
            (wrappers.tool_get_action_group_details, (1,)),
            (wrappers.tool_find_automation_references, ("device", 1)),
            (wrappers.tool_investigate_event, ()),
            (wrappers.tool_control_trigger, (1, "enable")),
            (wrappers.tool_control_schedule, (1, "disable")),
            (wrappers.tool_control_action_group, (1, "duplicate")),
            (wrappers.tool_update_trigger, (1, {"name": "x"})),
            (wrappers.tool_update_schedule, (1, {"name": "x"})),
            (wrappers.tool_update_action_group, (1, {"name": "x"})),
            (wrappers.tool_list_event_subscriptions, ()),
            (wrappers.tool_delete_event_subscription, ("01ABC",)),
        ]
        for fn, args in calls:
            result = fn(*args)
            assert isinstance(result, str), f"{fn.__name__} did not return str"
            json.loads(result)  # must be valid JSON


class TestErrorContract:
    """Handler exceptions become {"error": ...} payloads, never raise."""

    def test_handler_exception_becomes_error_payload(self):
        wrappers = make_wrappers()
        wrappers.automation_handler.control.side_effect = RuntimeError("boom")

        payload = json.loads(wrappers.tool_control_trigger(1, "enable"))

        assert payload["error"] == "boom"

    def test_search_error_preserves_query(self):
        wrappers = make_wrappers()
        wrappers.search_handler.search.side_effect = RuntimeError("index down")

        payload = json.loads(wrappers.tool_search_entities("kitchen"))

        assert payload["error"] == "index down"
        assert payload["query"] == "kitchen"

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


class TestControlActionGroup:
    """control_action_group has no execute and no delay (MCP Control runs action groups)."""

    def test_duplicate_reaches_the_automation_handler(self):
        wrappers = make_wrappers()
        wrappers.automation_handler.control.return_value = {"success": True}

        wrappers.tool_control_action_group(7, "duplicate", duplicate_name="Copy")

        kwargs = wrappers.automation_handler.control.call_args.kwargs
        assert kwargs["entity_type"] == "action_group"
        assert kwargs["action"] == "duplicate"
        assert kwargs["delay_seconds"] is None

    def test_delay_seconds_is_not_accepted(self):
        wrappers = make_wrappers()

        with pytest.raises(TypeError):
            wrappers.tool_control_action_group(7, "duplicate", delay_seconds=30)


class TestTypeErrorEscapes:
    """Wrong keyword arguments must raise TypeError OUT of the wrapper.

    mcp_handler._handle_tools_call catches TypeError/ValueError from the
    call site and produces an MCP isError tool result; if the wrapper
    swallowed it the model would lose its self-correction signal.
    """

    def test_unknown_kwarg_raises_typeerror(self):
        wrappers = make_wrappers()

        with pytest.raises(TypeError):
            wrappers.tool_get_trigger_details(trigger_idd=1)

    def test_missing_required_arg_raises_typeerror(self):
        wrappers = make_wrappers()

        with pytest.raises(TypeError):
            wrappers.tool_find_automation_references(entity_type="device")
