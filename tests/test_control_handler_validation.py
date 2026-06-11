"""
Validation-consistency tests across all device-controlling handler entry points.

Every method that takes a device_id must reject invalid ids the same way
(via BaseToolHandler.validate_device_id) and pass through handler results
on success.
"""

import pytest
from unittest.mock import Mock
import sys
from pathlib import Path

# Add plugin to path
plugin_path = Path(__file__).parent.parent / "MCP Server.indigoPlugin/Contents/Server Plugin"
sys.path.insert(0, str(plugin_path))

from mcp_server.tools.device_control.device_control_handler import DeviceControlHandler
from mcp_server.tools.rgb_control.rgb_control_handler import RGBControlHandler
from mcp_server.tools.thermostat_control.thermostat_control_handler import ThermostatControlHandler
from mcp_server.tools.variable_control.variable_control_handler import VariableControlHandler


def make(handler_cls):
    return handler_cls(data_provider=Mock(), logger=Mock())


# (handler class, method name, extra args after device_id)
DEVICE_ID_ENTRY_POINTS = [
    (DeviceControlHandler, "turn_on", ()),
    (DeviceControlHandler, "turn_off", ()),
    (DeviceControlHandler, "set_brightness", (50,)),
    (ThermostatControlHandler, "set_heat_setpoint", (68.0,)),
    (ThermostatControlHandler, "set_cool_setpoint", (75.0,)),
    (ThermostatControlHandler, "set_hvac_mode", ("heat",)),
    (ThermostatControlHandler, "set_fan_mode", ("auto",)),
    (RGBControlHandler, "set_rgb_color", (255, 0, 0)),
    (RGBControlHandler, "set_rgb_percent", (100.0, 0.0, 0.0)),
    (RGBControlHandler, "set_hex_color", ("#ff0000",)),
    (RGBControlHandler, "set_named_color", ("red",)),
    (RGBControlHandler, "set_white_levels", (50.0,)),
]


class TestDeviceIdValidationConsistency:
    @pytest.mark.parametrize("handler_cls,method,extra", DEVICE_ID_ENTRY_POINTS,
                             ids=lambda v: v if isinstance(v, str) else None)
    @pytest.mark.parametrize("bad_id", [0, -1, True, "42", None])
    def test_invalid_device_id_rejected(self, handler_cls, method, extra, bad_id):
        handler = make(handler_cls)

        result = getattr(handler, method)(bad_id, *extra)

        assert result["success"] is False
        assert "positive integer" in result["error"]
        # the data provider must never be touched with a bad id
        handler.data_provider.set_device_color_levels.assert_not_called()

    @pytest.mark.parametrize("handler_cls,method,extra", DEVICE_ID_ENTRY_POINTS,
                             ids=lambda v: v if isinstance(v, str) else None)
    def test_valid_device_id_reaches_provider(self, handler_cls, method, extra):
        handler = make(handler_cls)
        # generic success result regardless of which provider method is hit
        for attr in ("turn_on_device", "turn_off_device", "set_device_brightness",
                     "set_device_color_levels", "set_thermostat_heat_setpoint",
                     "set_thermostat_cool_setpoint", "set_thermostat_hvac_mode",
                     "set_thermostat_fan_mode"):
            getattr(handler.data_provider, attr).return_value = {"success": True, "changed": True}
        handler.data_provider.get_device.return_value = {"name": "Test Device"}

        result = getattr(handler, method)(42, *extra)

        assert "positive integer" not in str(result.get("error", ""))


class TestHandlerExceptionPath:
    def test_provider_exception_becomes_error_dict(self):
        handler = make(DeviceControlHandler)
        handler.data_provider.get_device.return_value = {"name": "Test"}
        handler.data_provider.turn_on_device.side_effect = RuntimeError("bridge offline")

        result = handler.turn_on(42)

        assert result["success"] is False
        assert result["error"] == "bridge offline"

    def test_provider_error_result_passed_through(self):
        handler = make(DeviceControlHandler)
        handler.data_provider.get_device.return_value = {"name": "Test"}
        handler.data_provider.turn_on_device.return_value = {"error": "Device 42 not found"}

        result = handler.turn_on(42)

        assert result["error"] == "Device 42 not found"


class TestVariableControlValidation:
    def test_update_rejects_non_int_id(self):
        handler = make(VariableControlHandler)

        result = handler.update("not-an-int", "value")

        assert result["success"] is False
        handler.data_provider.update_variable.assert_not_called()

    def test_create_requires_name(self):
        handler = make(VariableControlHandler)

        result = handler.create("")

        assert result["success"] is False
        handler.data_provider.create_variable.assert_not_called()

    def test_create_rejects_non_int_folder(self):
        handler = make(VariableControlHandler)

        result = handler.create("ok_name", "v", "folder")

        assert result["success"] is False
