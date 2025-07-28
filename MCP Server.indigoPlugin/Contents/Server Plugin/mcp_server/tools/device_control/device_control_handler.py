"""
Device control handler for MCP server.
"""

import logging
from typing import Dict, Any, Optional

from ...adapters.data_provider import DataProvider


class DeviceControlHandler:
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
        self.data_provider = data_provider
        self.logger = logger or logging.getLogger("Plugin")
    
    def turn_on(self, device_id: int) -> Dict[str, Any]:
        """
        Turn on a device.
        
        Args:
            device_id: The device ID to turn on
            
        Returns:
            Dictionary with operation results
        """
        try:
            # Validate device_id
            if not isinstance(device_id, int):
                return {"error": "device_id must be an integer"}
            
            self.logger.info(f"Turning on device {device_id}")
            result = self.data_provider.turn_on_device(device_id)
            
            if "error" in result:
                self.logger.error(f"Failed to turn on device {device_id}: {result['error']}")
            else:
                self.logger.info(f"Device {device_id} turned on successfully. Changed: {result.get('changed', False)}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Unexpected error turning on device {device_id}: {e}")
            return {"error": str(e)}
    
    def turn_off(self, device_id: int) -> Dict[str, Any]:
        """
        Turn off a device.
        
        Args:
            device_id: The device ID to turn off
            
        Returns:
            Dictionary with operation results
        """
        try:
            # Validate device_id
            if not isinstance(device_id, int):
                return {"error": "device_id must be an integer"}
            
            self.logger.info(f"Turning off device {device_id}")
            result = self.data_provider.turn_off_device(device_id)
            
            if "error" in result:
                self.logger.error(f"Failed to turn off device {device_id}: {result['error']}")
            else:
                self.logger.info(f"Device {device_id} turned off successfully. Changed: {result.get('changed', False)}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Unexpected error turning off device {device_id}: {e}")
            return {"error": str(e)}
    
    def set_brightness(self, device_id: int, brightness: float) -> Dict[str, Any]:
        """
        Set brightness level for a dimmer device.
        
        Args:
            device_id: The device ID
            brightness: Brightness level (0-1 or 0-100)
            
        Returns:
            Dictionary with operation results
        """
        try:
            # Validate device_id
            if not isinstance(device_id, int):
                return {"error": "device_id must be an integer"}
            
            # Validate brightness
            if not isinstance(brightness, (int, float)):
                return {"error": "brightness must be a number"}
            
            self.logger.info(f"Setting brightness for device {device_id} to {brightness}")
            result = self.data_provider.set_device_brightness(device_id, brightness)
            
            if "error" in result:
                self.logger.error(f"Failed to set brightness for device {device_id}: {result['error']}")
            else:
                self.logger.info(f"Device {device_id} brightness set successfully. Changed: {result.get('changed', False)}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Unexpected error setting brightness for device {device_id}: {e}")
            return {"error": str(e)}