"""
Get devices by type handler for retrieving all devices of a specific type.
"""

import logging
from typing import Dict, List, Any, Optional

from ...adapters.data_provider import DataProvider
from ...common.indigo_device_types import IndigoDeviceType, DeviceClassifier
from ..base_handler import BaseToolHandler


class GetDevicesByTypeHandler(BaseToolHandler):
    """Handler for retrieving all devices of a specific type."""
    
    def __init__(
        self, 
        data_provider: DataProvider,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize the get devices by type handler.
        
        Args:
            data_provider: Data provider for accessing entity data
            logger: Optional logger instance
        """
        super().__init__(tool_name="get_devices_by_type", logger=logger)
        self.data_provider = data_provider
    
    def get_devices(self, device_type: str) -> Dict[str, Any]:
        """
        Get all devices of a specific type.
        
        Args:
            device_type: The device type to filter by (dimmer, relay, sensor, etc.)
            
        Returns:
            Dictionary with list of devices and metadata
        """
        try:
            # Validate device type
            if not IndigoDeviceType.is_valid_type(device_type):
                return {
                    "error": f"Invalid device type: {device_type}",
                    "valid_types": IndigoDeviceType.get_all_types(),
                    "success": False
                }
            
            self.info_log(f"Retrieving all devices of type: {device_type}")
            
            # Get all devices
            all_devices = self.data_provider.get_all_devices_unfiltered()
            
            # Filter by device type using the new classifier
            filtered_devices = DeviceClassifier.filter_devices_by_type(all_devices, device_type)
            
            # Sort by name for consistent output
            filtered_devices.sort(key=lambda d: d.get("name", "").lower())
            
            # Log results
            device_count = len(filtered_devices)
            self.info_log(f"Found {device_count} devices of type '{device_type}'")
            
            if device_count > 0:
                # Log first few device names
                names = [device.get("name", device.get("id", "unknown")) for device in filtered_devices[:5]]
                more_text = f" (and {device_count - 5} more)" if device_count > 5 else ""
                self.info_log(f"Devices: {', '.join(names)}{more_text}")
            
            return {
                "device_type": device_type,
                "count": device_count,
                "devices": filtered_devices,
                "success": True
            }
            
        except Exception as e:
            return self.handle_exception(e, f"retrieving devices of type '{device_type}'")