"""
Device control handler for MCP server.
"""

import logging
from typing import Dict, Any, Optional

from ...adapters.data_provider import DataProvider
from ..base_handler import BaseToolHandler


class DeviceControlHandler(BaseToolHandler):
    """Handler for device control operations."""
    
    def __init__(
        self,
        data_provider: DataProvider,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize the device control handler.
        
        Args:
            data_provider: Data provider for device operations
            logger: Optional logger instance
        """
        super().__init__(tool_name="device_control", logger=logger)
        self.data_provider = data_provider
    
    def turn_on(self, device_id: int) -> Dict[str, Any]:
        """
        Turn on a device.
        
        Args:
            device_id: The device ID to turn on
            
        Returns:
            Dictionary with operation results
        """
        # Log incoming request
        self.log_incoming_request("turn_on", {"device_id": device_id})
        
        try:
            # Validate device_id
            if not isinstance(device_id, int):
                error_result = {"error": "device_id must be an integer", "success": False}
                self.log_tool_outcome("turn_on", False, "Invalid device_id type")
                return error_result
            
            # Get device name for better logging
            device = self.data_provider.get_device(device_id)
            device_name = device.get('name', f'ID {device_id}') if device else f'ID {device_id}'
            
            self.debug_log(f"Attempting to turn on device {device_name}")
            result = self.data_provider.turn_on_device(device_id)
            
            if "error" in result:
                self.log_tool_outcome("turn_on", False, f"Device {device_name}: {result['error']}")
            else:
                device_name = result.get('device_name', device_name)
                changed = result.get('changed', False)
                details = f"Device {device_name}, changed: {changed}"
                self.log_tool_outcome("turn_on", True, details)
            
            return result
            
        except Exception as e:
            return self.handle_exception(e, f"turning on device ID {device_id}")
    
    def turn_off(self, device_id: int) -> Dict[str, Any]:
        """
        Turn off a device.
        
        Args:
            device_id: The device ID to turn off
            
        Returns:
            Dictionary with operation results
        """
        # Log incoming request
        self.log_incoming_request("turn_off", {"device_id": device_id})
        
        try:
            # Validate device_id
            if not isinstance(device_id, int):
                error_result = {"error": "device_id must be an integer", "success": False}
                self.log_tool_outcome("turn_off", False, "Invalid device_id type")
                return error_result
            
            # Get device name for better logging
            device = self.data_provider.get_device(device_id)
            device_name = device.get('name', f'ID {device_id}') if device else f'ID {device_id}'
            
            self.debug_log(f"Attempting to turn off device {device_name}")
            result = self.data_provider.turn_off_device(device_id)
            
            if "error" in result:
                self.log_tool_outcome("turn_off", False, f"Device {device_name}: {result['error']}")
            else:
                device_name = result.get('device_name', device_name)
                changed = result.get('changed', False)
                details = f"Device {device_name}, changed: {changed}"
                self.log_tool_outcome("turn_off", True, details)
            
            return result
            
        except Exception as e:
            return self.handle_exception(e, f"turning off device ID {device_id}")
    
    def set_brightness(self, device_id: int, brightness: float) -> Dict[str, Any]:
        """
        Set brightness level for a dimmer device.
        
        Args:
            device_id: The device ID
            brightness: Brightness level (0-1 or 0-100)
            
        Returns:
            Dictionary with operation results
        """
        # Log incoming request
        self.log_incoming_request("set_brightness", {"device_id": device_id, "brightness": brightness})
        
        try:
            # Validate device_id
            if not isinstance(device_id, int):
                error_result = {"error": "device_id must be an integer", "success": False}
                self.log_tool_outcome("set_brightness", False, "Invalid device_id type")
                return error_result
            
            # Validate brightness
            if not isinstance(brightness, (int, float)):
                error_result = {"error": "brightness must be a number", "success": False}
                self.log_tool_outcome("set_brightness", False, "Invalid brightness type")
                return error_result
            
            # Get device name for better logging
            device = self.data_provider.get_device(device_id)
            device_name = device.get('name', f'ID {device_id}') if device else f'ID {device_id}'
            
            self.debug_log(f"Attempting to set brightness for device {device_name} to {brightness}")
            result = self.data_provider.set_device_brightness(device_id, brightness)
            
            if "error" in result:
                self.log_tool_outcome("set_brightness", False, f"Device {device_name}: {result['error']}")
            else:
                device_name = result.get('device_name', device_name)
                changed = result.get('changed', False)
                details = f"Device {device_name} brightness set to {brightness}, changed: {changed}"
                self.log_tool_outcome("set_brightness", True, details)
            
            return result
            
        except Exception as e:
            return self.handle_exception(e, f"setting brightness for device ID {device_id}")