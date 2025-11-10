"""
Thermostat device control handler for managing HVAC devices.

Provides tools for controlling thermostats:
- Set heat setpoint
- Set cool setpoint
- Set HVAC mode (heat, cool, auto, off, program modes)
- Set fan mode (auto, alwaysOn)
"""

import logging
from typing import Dict, Any, Optional

from ..base_handler import BaseToolHandler
from ...adapters.data_provider import DataProvider


class ThermostatControlHandler(BaseToolHandler):
    """Handler for thermostat control operations."""

    # Valid HVAC modes
    VALID_HVAC_MODES = ["heat", "cool", "auto", "off", "heatcool", "programheat", "programcool", "programauto"]

    # Valid fan modes
    VALID_FAN_MODES = ["auto", "alwayson"]

    # Temperature range limits (Fahrenheit)
    MIN_TEMP_F = 40.0
    MAX_TEMP_F = 95.0

    def __init__(self, data_provider: DataProvider, logger: Optional[logging.Logger] = None):
        """
        Initialize thermostat control handler.

        Args:
            data_provider: Data provider instance for accessing Indigo
            logger: Optional logger instance
        """
        super().__init__(tool_name="thermostat_control", logger=logger)
        self.data_provider = data_provider

    def set_heat_setpoint(self, device_id: int, temperature: float) -> Dict[str, Any]:
        """
        Set heat setpoint for a thermostat device.

        Args:
            device_id: The device ID
            temperature: Temperature setpoint value (typically Fahrenheit)

        Returns:
            Operation result dictionary
        """
        try:
            # Validate device ID
            if not isinstance(device_id, int) or device_id <= 0:
                self.info_log(f"❌ Invalid device_id: {device_id}. Must be a positive integer.")
                return {"error": f"Invalid device_id: {device_id}. Must be a positive integer.", "success": False}

            # Validate temperature
            if not isinstance(temperature, (int, float)):
                self.info_log(f"❌ Invalid temperature: {temperature}. Must be a number.")
                return {"error": f"Invalid temperature: {temperature}. Must be a number.", "success": False}

            # Temperature range warning (not enforcing, as some systems may use Celsius)
            if not (self.MIN_TEMP_F <= temperature <= self.MAX_TEMP_F):
                self.logger.warning(
                    f"Temperature {temperature} is outside typical range "
                    f"({self.MIN_TEMP_F}-{self.MAX_TEMP_F}°F). "
                    f"Proceeding anyway in case system uses different scale."
                )

            self.logger.debug(f"Setting heat setpoint to {temperature} for device {device_id}")

            # Set heat setpoint via data provider
            result = self.data_provider.set_thermostat_heat_setpoint(device_id, temperature)

            if "error" in result:
                self.info_log(f"❌ {result['error']}")
                return result

            self.info_log(f"✅ Set heat setpoint to {temperature} for device {device_id}")
            return self.create_success_response(result, f"Set heat setpoint to {temperature} for device {device_id}")

        except Exception as e:
            return self.handle_exception(e, f"setting heat setpoint for device {device_id}")

    def set_cool_setpoint(self, device_id: int, temperature: float) -> Dict[str, Any]:
        """
        Set cool setpoint for a thermostat device.

        Args:
            device_id: The device ID
            temperature: Temperature setpoint value (typically Fahrenheit)

        Returns:
            Operation result dictionary
        """
        try:
            # Validate device ID
            if not isinstance(device_id, int) or device_id <= 0:
                self.info_log(f"❌ Invalid device_id: {device_id}. Must be a positive integer.")
                return {"error": f"Invalid device_id: {device_id}. Must be a positive integer.", "success": False}

            # Validate temperature
            if not isinstance(temperature, (int, float)):
                self.info_log(f"❌ Invalid temperature: {temperature}. Must be a number.")
                return {"error": f"Invalid temperature: {temperature}. Must be a number.", "success": False}

            # Temperature range warning (not enforcing, as some systems may use Celsius)
            if not (self.MIN_TEMP_F <= temperature <= self.MAX_TEMP_F):
                self.logger.warning(
                    f"Temperature {temperature} is outside typical range "
                    f"({self.MIN_TEMP_F}-{self.MAX_TEMP_F}°F). "
                    f"Proceeding anyway in case system uses different scale."
                )

            self.logger.debug(f"Setting cool setpoint to {temperature} for device {device_id}")

            # Set cool setpoint via data provider
            result = self.data_provider.set_thermostat_cool_setpoint(device_id, temperature)

            if "error" in result:
                self.info_log(f"❌ {result['error']}")
                return result

            self.info_log(f"✅ Set cool setpoint to {temperature} for device {device_id}")
            return self.create_success_response(result, f"Set cool setpoint to {temperature} for device {device_id}")

        except Exception as e:
            return self.handle_exception(e, f"setting cool setpoint for device {device_id}")

    def set_hvac_mode(self, device_id: int, mode: str) -> Dict[str, Any]:
        """
        Set HVAC operating mode for a thermostat device.

        Args:
            device_id: The device ID
            mode: HVAC mode (heat, cool, auto, off, heatcool, programheat, programcool, programauto)

        Returns:
            Operation result dictionary
        """
        try:
            # Validate device ID
            if not isinstance(device_id, int) or device_id <= 0:
                self.info_log(f"❌ Invalid device_id: {device_id}. Must be a positive integer.")
                return {"error": f"Invalid device_id: {device_id}. Must be a positive integer.", "success": False}

            # Validate mode
            if not isinstance(mode, str):
                self.info_log(f"❌ Invalid mode: {mode}. Must be a string.")
                return {"error": f"Invalid mode: {mode}. Must be a string.", "success": False}

            mode_lower = mode.lower()
            if mode_lower not in self.VALID_HVAC_MODES:
                error_msg = f"Invalid HVAC mode: {mode}. Valid modes: {', '.join(self.VALID_HVAC_MODES)}"
                self.info_log(f"❌ {error_msg}")
                return {"error": error_msg, "success": False}

            self.logger.debug(f"Setting HVAC mode to '{mode}' for device {device_id}")

            # Set HVAC mode via data provider
            result = self.data_provider.set_thermostat_hvac_mode(device_id, mode)

            if "error" in result:
                self.info_log(f"❌ {result['error']}")
                return result

            self.info_log(f"✅ Set HVAC mode to '{mode}' for device {device_id}")
            return self.create_success_response(result, f"Set HVAC mode to '{mode}' for device {device_id}")

        except Exception as e:
            return self.handle_exception(e, f"setting HVAC mode for device {device_id}")

    def set_fan_mode(self, device_id: int, mode: str) -> Dict[str, Any]:
        """
        Set fan operating mode for a thermostat device.

        Args:
            device_id: The device ID
            mode: Fan mode (auto, alwaysOn)

        Returns:
            Operation result dictionary
        """
        try:
            # Validate device ID
            if not isinstance(device_id, int) or device_id <= 0:
                self.info_log(f"❌ Invalid device_id: {device_id}. Must be a positive integer.")
                return {"error": f"Invalid device_id: {device_id}. Must be a positive integer.", "success": False}

            # Validate mode
            if not isinstance(mode, str):
                self.info_log(f"❌ Invalid mode: {mode}. Must be a string.")
                return {"error": f"Invalid mode: {mode}. Must be a string.", "success": False}

            mode_lower = mode.lower()
            if mode_lower not in self.VALID_FAN_MODES:
                error_msg = f"Invalid fan mode: {mode}. Valid modes: {', '.join(self.VALID_FAN_MODES)}"
                self.info_log(f"❌ {error_msg}")
                return {"error": error_msg, "success": False}

            self.logger.debug(f"Setting fan mode to '{mode}' for device {device_id}")

            # Set fan mode via data provider
            result = self.data_provider.set_thermostat_fan_mode(device_id, mode)

            if "error" in result:
                self.info_log(f"❌ {result['error']}")
                return result

            self.info_log(f"✅ Set fan mode to '{mode}' for device {device_id}")
            return self.create_success_response(result, f"Set fan mode to '{mode}' for device {device_id}")

        except Exception as e:
            return self.handle_exception(e, f"setting fan mode for device {device_id}")
