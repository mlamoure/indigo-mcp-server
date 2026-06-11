"""Tests for BaseToolHandler — validation, error handling, response shaping."""

import logging
import pytest
from unittest.mock import Mock
import sys
import importlib
from pathlib import Path

# Add plugin to path
plugin_path = Path(__file__).parent.parent / "MCP Server.indigoPlugin/Contents/Server Plugin"
sys.path.insert(0, str(plugin_path))

# conftest pre-loads this module standalone (stdlib-only chain)
base_handler = importlib.import_module("mcp_server.tools.base_handler")
BaseToolHandler = base_handler.BaseToolHandler


@pytest.fixture
def handler():
    lg = logging.getLogger("test_base_handler")
    lg.setLevel(logging.DEBUG)
    h = BaseToolHandler(tool_name="test_tool", logger=lg)
    return h


class TestValidateDeviceId:
    @pytest.mark.parametrize("bad", [0, -1, -999, True, False, "42", 4.2, None, [1]])
    def test_rejects_invalid(self, handler, bad):
        result = handler.validate_device_id(bad)

        assert result is not None
        assert result["success"] is False
        assert "positive integer" in result["error"]

    @pytest.mark.parametrize("good", [1, 42, 25405119])
    def test_accepts_positive_ints(self, handler, good):
        assert handler.validate_device_id(good) is None


class TestValidateRequiredParams:
    def test_missing_keys_reported(self, handler):
        result = handler.validate_required_params({"a": 1, "b": None}, ["a", "b", "c"])

        assert result["success"] is False
        assert set(result["missing_parameters"]) == {"b", "c"}
        assert result["tool"] == "test_tool"

    def test_all_present_returns_none(self, handler):
        assert handler.validate_required_params({"a": 1, "b": 2}, ["a", "b"]) is None


class TestHandleException:
    def test_shape(self, handler):
        result = handler.handle_exception(RuntimeError("boom"), "doing the thing")

        assert result == {
            "error": "boom",
            "tool": "test_tool",
            "context": "doing the thing",
            "success": False,
        }

    def test_logs_one_error_line(self, handler, caplog):
        with caplog.at_level(logging.ERROR, logger="test_base_handler"):
            handler.handle_exception(RuntimeError("boom"), "doing the thing")

        errors = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(errors) == 1
        assert errors[0].message.startswith("❌")


class TestCreateSuccessResponse:
    def test_shape(self, handler):
        result = handler.create_success_response({"x": 1})

        assert result == {"success": True, "tool": "test_tool", "data": {"x": 1}}

    def test_message_included_and_logged(self, handler, caplog):
        with caplog.at_level(logging.INFO, logger="test_base_handler"):
            result = handler.create_success_response([], "all done")

        assert result["message"] == "all done"


class TestErrorLog:
    def test_prepends_fail_emoji(self, handler, caplog):
        with caplog.at_level(logging.ERROR, logger="test_base_handler"):
            handler.error_log("something broke")

        assert caplog.records[0].message == "❌ something broke"

    def test_does_not_double_emoji(self, handler, caplog):
        with caplog.at_level(logging.ERROR, logger="test_base_handler"):
            handler.error_log("❌ already prefixed")

        assert caplog.records[0].message == "❌ already prefixed"


class TestActivityLog:
    def test_write_is_info_with_wrench(self, handler, caplog):
        with caplog.at_level(logging.DEBUG, logger="test_base_handler"):
            handler.activity_log("Kitchen Lights → on")

        assert caplog.records[0].levelno == logging.INFO
        assert caplog.records[0].message == "🔧 Kitchen Lights → on"

    def test_read_is_debug(self, handler, caplog):
        with caplog.at_level(logging.DEBUG, logger="test_base_handler"):
            handler.activity_log("Search 'x' → 0 results", write=False)

        assert caplog.records[0].levelno == logging.DEBUG


class TestDeviceLabel:
    def test_uses_provider_name(self, handler):
        handler.data_provider = Mock()
        handler.data_provider.get_device.return_value = {"name": "Kitchen Lights"}

        assert handler.device_label(42) == "Kitchen Lights"

    def test_falls_back_without_provider(self, handler):
        assert handler.device_label(42) == "device 42"

    def test_falls_back_on_provider_error(self, handler):
        handler.data_provider = Mock()
        handler.data_provider.get_device.side_effect = RuntimeError("down")

        assert handler.device_label(42) == "device 42"

    def test_falls_back_on_missing_device(self, handler):
        handler.data_provider = Mock()
        handler.data_provider.get_device.return_value = None

        assert handler.device_label(42) == "device 42"
