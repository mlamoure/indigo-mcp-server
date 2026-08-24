"""Tests for ExternalToolHandler dispatch (executeAction boundary)."""

import json
import sys
import time
from pathlib import Path
from unittest.mock import Mock, patch

plugin_path = Path(__file__).parent.parent / "MCP Server.indigoPlugin/Contents/Server Plugin"
sys.path.insert(0, str(plugin_path))

from mcp_server.external_tools import external_tool_handler as eth_module
from mcp_server.external_tools.external_tool_handler import ExternalToolHandler

PROVIDER = "com.example.myplugin"


def invoke(mock_plugin, arguments=None, timeout_seconds=5, write=False):
    handler = ExternalToolHandler(logger=Mock())
    mock_indigo = Mock()
    mock_indigo.server.getPlugin.return_value = mock_plugin
    with patch.object(eth_module, "indigo", mock_indigo):
        return handler.invoke(
            provider_id=PROVIDER,
            action_id="mcp_tool_invoke",
            bare_name="get_status",
            display_name="My Plugin",
            arguments=arguments or {},
            timeout_seconds=timeout_seconds,
            write=write,
        )


def running_plugin(reply):
    plugin = Mock()
    plugin.isRunning.return_value = True
    plugin.executeAction.return_value = reply
    return plugin


def test_provider_not_running():
    plugin = Mock()
    plugin.isRunning.return_value = False
    result = invoke(plugin)
    assert result["success"] is False
    assert "not running" in result["error"]
    plugin.executeAction.assert_not_called()


def test_ok_envelope():
    plugin = running_plugin(json.dumps({"status": "ok", "result": {"state": "on"}}))
    result = invoke(plugin, arguments={"a": 1, "b": None})
    assert result == {"success": True, "provider": PROVIDER, "result": {"state": "on"}}
    # arguments crossed the boundary as a JSON string
    _, kwargs = plugin.executeAction.call_args
    assert kwargs["props"]["tool"] == "get_status"
    assert json.loads(kwargs["props"]["arguments"]) == {"a": 1, "b": None}
    assert kwargs["waitUntilDone"] is True


def test_error_envelope_mapped():
    plugin = running_plugin(
        json.dumps(
            {
                "status": "error",
                "error": {
                    "type": "validation",
                    "message": "bad mode",
                    "details": {"errors": []},
                },
            }
        )
    )
    result = invoke(plugin)
    assert result["success"] is False
    assert result["error"] == "bad mode"
    assert result["error_type"] == "validation"
    assert result["details"] == {"errors": []}


def test_non_string_reply_is_protocol_violation():
    plugin = running_plugin({"status": "ok"})  # dict, not a JSON string
    result = invoke(plugin)
    assert result["success"] is False
    assert "protocol" in result["error"]


def test_non_json_reply_is_protocol_violation():
    plugin = running_plugin("<html>oops</html>")
    result = invoke(plugin)
    assert result["success"] is False
    assert "not valid JSON" in result["error"]


def test_envelope_without_status_is_protocol_violation():
    plugin = running_plugin(json.dumps({"data": 1}))
    result = invoke(plugin)
    assert result["success"] is False
    assert "protocol" in result["error"]


def test_execute_action_exception():
    plugin = Mock()
    plugin.isRunning.return_value = True
    plugin.executeAction.side_effect = Exception("action not defined")
    result = invoke(plugin)
    assert result["success"] is False
    assert "action not defined" in result["error"]
    assert "plugin.log" in result["error"]


def test_timeout():
    plugin = Mock()
    plugin.isRunning.return_value = True

    def slow_action(*args, **kwargs):
        time.sleep(1.0)
        return json.dumps({"status": "ok", "result": None})

    plugin.executeAction.side_effect = slow_action
    result = invoke(plugin, timeout_seconds=0.2)
    assert result["success"] is False
    assert result["timeout"] is True
