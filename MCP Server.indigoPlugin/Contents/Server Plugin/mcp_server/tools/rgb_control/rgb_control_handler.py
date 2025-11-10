"""
RGB device control handler for managing color-capable devices.

Provides tools for controlling RGB/RGBW devices with multiple color input formats:
- RGB values (0-255)
- RGB percentages (0-100)
- Hex color codes (#RRGGBB)
- Named colors (954 XKCD colors + custom aliases)
- White channel control (level and temperature)
"""

import logging
from typing import Dict, Any, Optional

from ..base_handler import BaseToolHandler
from ...adapters.data_provider import DataProvider
from ...common.color_utils import (
    rgb_to_percent,
    validate_percent,
    hex_to_rgb_percent,
    named_color_to_rgb_percent,
    validate_white_temperature,
    get_color_suggestions,
    get_available_colors
)


class RGBControlHandler(BaseToolHandler):
    """Handler for RGB device control operations."""

    def __init__(self, data_provider: DataProvider, logger: Optional[logging.Logger] = None):
        """
        Initialize RGB control handler.

        Args:
            data_provider: Data provider instance for accessing Indigo
            logger: Optional logger instance
        """
        super().__init__(tool_name="rgb_control", logger=logger)
        self.data_provider = data_provider

    def set_rgb_color(
        self,
        device_id: int,
        red: int,
        green: int,
        blue: int,
        delay: int = 0
    ) -> Dict[str, Any]:
        """
        Set RGB color using 0-255 values.

        Args:
            device_id: The device ID
            red: Red value (0-255)
            green: Green value (0-255)
            blue: Blue value (0-255)
            delay: Optional delay in seconds (default: 0)

        Returns:
            Operation result dictionary
        """
        try:
            # Validate device ID
            if not isinstance(device_id, int) or device_id <= 0:
                self.info_log(f"❌ Invalid device_id: {device_id}. Must be a positive integer.")
                return {"error": f"Invalid device_id: {device_id}. Must be a positive integer.", "success": False}

            # Convert RGB (0-255) to percentages (0-100)
            red_percent, green_percent, blue_percent = rgb_to_percent(red, green, blue)

            self.logger.debug(
                f"Converting RGB({red}, {green}, {blue}) to percentages: "
                f"({red_percent}, {green_percent}, {blue_percent})"
            )

            # Set color levels via data provider
            result = self.data_provider.set_device_color_levels(
                device_id=device_id,
                red_level=red_percent,
                green_level=green_percent,
                blue_level=blue_percent,
                delay=delay
            )

            if "error" in result:
                self.info_log(f"❌ {result['error']}")
                return result

            self.info_log(f"✅ Set RGB color for device {device_id}")
            return self.create_success_response(result, f"Set RGB color for device {device_id}")

        except ValueError as e:
            self.info_log(f"❌ {str(e)}")
            return {"error": str(e), "success": False}
        except Exception as e:
            return self.handle_exception(e, f"setting RGB color for device {device_id}")

    def set_rgb_percent(
        self,
        device_id: int,
        red_percent: float,
        green_percent: float,
        blue_percent: float,
        delay: int = 0
    ) -> Dict[str, Any]:
        """
        Set RGB color using 0-100 percentage values.

        Args:
            device_id: The device ID
            red_percent: Red percentage (0-100)
            green_percent: Green percentage (0-100)
            blue_percent: Blue percentage (0-100)
            delay: Optional delay in seconds (default: 0)

        Returns:
            Operation result dictionary
        """
        try:
            # Validate device ID
            if not isinstance(device_id, int) or device_id <= 0:
                self.info_log(f"❌ Invalid device_id: {device_id}. Must be a positive integer.")
                return {"error": f"Invalid device_id: {device_id}. Must be a positive integer.", "success": False}

            # Validate percentages
            red_percent, green_percent, blue_percent = validate_percent(
                red_percent, green_percent, blue_percent
            )

            self.logger.debug(
                f"Setting RGB percentages: ({red_percent}, {green_percent}, {blue_percent})"
            )

            # Set color levels via data provider
            result = self.data_provider.set_device_color_levels(
                device_id=device_id,
                red_level=red_percent,
                green_level=green_percent,
                blue_level=blue_percent,
                delay=delay
            )

            if "error" in result:
                self.info_log(f"❌ {result['error']}")
                return result

            self.info_log(f"✅ Set RGB percentage color for device {device_id}")
            return self.create_success_response(result, f"Set RGB percentage color for device {device_id}")

        except ValueError as e:
            self.info_log(f"❌ {str(e)}")
            return {"error": str(e), "success": False}
        except Exception as e:
            return self.handle_exception(e, f"setting RGB percentage for device {device_id}")

    def set_hex_color(
        self,
        device_id: int,
        hex_color: str,
        delay: int = 0
    ) -> Dict[str, Any]:
        """
        Set RGB color using hex color code.

        Args:
            device_id: The device ID
            hex_color: Hex color code (e.g., "#FF8000" or "FF8000")
            delay: Optional delay in seconds (default: 0)

        Returns:
            Operation result dictionary
        """
        try:
            # Validate device ID
            if not isinstance(device_id, int) or device_id <= 0:
                self.info_log(f"❌ Invalid device_id: {device_id}. Must be a positive integer.")
                return {"error": f"Invalid device_id: {device_id}. Must be a positive integer.", "success": False}

            # Convert hex to RGB percentages
            red_percent, green_percent, blue_percent = hex_to_rgb_percent(hex_color)

            self.logger.debug(
                f"Converting hex color {hex_color} to percentages: "
                f"({red_percent}, {green_percent}, {blue_percent})"
            )

            # Set color levels via data provider
            result = self.data_provider.set_device_color_levels(
                device_id=device_id,
                red_level=red_percent,
                green_level=green_percent,
                blue_level=blue_percent,
                delay=delay
            )

            if "error" in result:
                self.info_log(f"❌ {result['error']}")
                return result

            self.info_log(f"✅ Set hex color {hex_color} for device {device_id}")
            return self.create_success_response(result, f"Set hex color {hex_color} for device {device_id}")

        except ValueError as e:
            self.info_log(f"❌ {str(e)}")
            return {"error": str(e), "success": False}
        except Exception as e:
            return self.handle_exception(e, f"setting hex color for device {device_id}")

    def set_named_color(
        self,
        device_id: int,
        color_name: str,
        delay: int = 0
    ) -> Dict[str, Any]:
        """
        Set RGB color using named color.

        Supports 954 XKCD colors plus custom aliases like "warm white", "cool white".

        Args:
            device_id: The device ID
            color_name: Color name (e.g., "sky blue", "warm white", "burnt orange")
            delay: Optional delay in seconds (default: 0)

        Returns:
            Operation result dictionary
        """
        try:
            # Validate device ID
            if not isinstance(device_id, int) or device_id <= 0:
                self.info_log(f"❌ Invalid device_id: {device_id}. Must be a positive integer.")
                return {"error": f"Invalid device_id: {device_id}. Must be a positive integer.", "success": False}

            # Convert named color to RGB percentages
            try:
                red_percent, green_percent, blue_percent = named_color_to_rgb_percent(color_name)
            except ValueError as e:
                # Provide color suggestions
                suggestions = get_color_suggestions(color_name, max_suggestions=5)
                error_msg = str(e)
                if suggestions:
                    error_msg += f". Did you mean: {', '.join(suggestions)}?"
                self.info_log(f"❌ {error_msg}")
                return {"error": error_msg, "success": False}

            self.logger.debug(
                f"Converting color name '{color_name}' to percentages: "
                f"({red_percent}, {green_percent}, {blue_percent})"
            )

            # Set color levels via data provider
            result = self.data_provider.set_device_color_levels(
                device_id=device_id,
                red_level=red_percent,
                green_level=green_percent,
                blue_level=blue_percent,
                delay=delay
            )

            if "error" in result:
                self.info_log(f"❌ {result['error']}")
                return result

            self.info_log(f"✅ Set color '{color_name}' for device {device_id}")
            return self.create_success_response(result, f"Set color '{color_name}' for device {device_id}")

        except Exception as e:
            return self.handle_exception(e, f"setting named color for device {device_id}")

    def set_white_levels(
        self,
        device_id: int,
        white_level: Optional[float] = None,
        white_level2: Optional[float] = None,
        white_temperature: Optional[int] = None,
        delay: int = 0
    ) -> Dict[str, Any]:
        """
        Set white channel levels for RGBW devices.

        Args:
            device_id: The device ID
            white_level: White channel level (0-100), optional
            white_level2: Second white channel level (0-100), optional (for dual white devices)
            white_temperature: White temperature in Kelvin (1200-15000), optional
            delay: Optional delay in seconds (default: 0)

        Returns:
            Operation result dictionary
        """
        try:
            # Validate device ID
            if not isinstance(device_id, int) or device_id <= 0:
                self.info_log(f"❌ Invalid device_id: {device_id}. Must be a positive integer.")
                return {"error": f"Invalid device_id: {device_id}. Must be a positive integer.", "success": False}

            # Validate at least one white parameter is provided
            if white_level is None and white_level2 is None and white_temperature is None:
                error_msg = "At least one white parameter must be provided (white_level, white_level2, or white_temperature)"
                self.info_log(f"❌ {error_msg}")
                return {"error": error_msg, "success": False}

            # Validate white levels
            if white_level is not None:
                if not 0 <= white_level <= 100:
                    error_msg = f"white_level must be 0-100. Got: {white_level}"
                    self.info_log(f"❌ {error_msg}")
                    return {"error": error_msg, "success": False}

            if white_level2 is not None:
                if not 0 <= white_level2 <= 100:
                    error_msg = f"white_level2 must be 0-100. Got: {white_level2}"
                    self.info_log(f"❌ {error_msg}")
                    return {"error": error_msg, "success": False}

            # Validate white temperature
            if white_temperature is not None:
                try:
                    white_temperature = validate_white_temperature(white_temperature)
                except ValueError as e:
                    self.info_log(f"❌ {str(e)}")
                    return {"error": str(e), "success": False}

            self.logger.debug(
                f"Setting white levels: white_level={white_level}, "
                f"white_level2={white_level2}, white_temperature={white_temperature}"
            )

            # Set white levels via data provider
            result = self.data_provider.set_device_color_levels(
                device_id=device_id,
                white_level=white_level,
                white_level2=white_level2,
                white_temperature=white_temperature,
                delay=delay
            )

            if "error" in result:
                self.info_log(f"❌ {result['error']}")
                return result

            self.info_log(f"✅ Set white levels for device {device_id}")
            return self.create_success_response(result, f"Set white levels for device {device_id}")

        except Exception as e:
            return self.handle_exception(e, f"setting white levels for device {device_id}")

    def get_available_color_info(self) -> Dict[str, Any]:
        """
        Get information about available color names.

        Returns:
            Dictionary with color count information
        """
        try:
            color_info = get_available_colors()
            self.info_log("✅ Retrieved available color information")
            return self.create_success_response(color_info, "Retrieved available color information")
        except Exception as e:
            return self.handle_exception(e, "getting available color info")
