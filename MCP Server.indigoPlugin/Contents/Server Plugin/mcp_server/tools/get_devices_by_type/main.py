"""
Get devices by type handler for retrieving all devices of a specific type.
"""

import logging
from typing import Dict, List, Any, Optional

from ...adapters.data_provider import DataProvider
from ...common.indigo_device_types import IndigoDeviceType, DeviceClassifier, DeviceTypeResolver
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
    
    def get_devices(self, device_type: str, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        """
        Get devices of a specific type with pagination support.

        Args:
            device_type: The device type to filter by (dimmer, relay, sensor, etc.)
            limit: Maximum number of devices to return (default: 50)
            offset: Number of devices to skip (default: 0)

        Returns:
            Dictionary with list of devices and pagination metadata
        """
        try:
            # Resolve device type using alias system
            resolved_device_type = DeviceTypeResolver.resolve_device_type(device_type)
            if not resolved_device_type:
                # Generate helpful error message with suggestions
                error_parts = [f"Invalid device type: {device_type}"]
                error_parts.append(f"Valid types: {IndigoDeviceType.get_all_types()}")

                # Add suggestions
                suggestions = DeviceTypeResolver.get_suggestions_for_invalid_type(device_type)
                if suggestions:
                    error_parts.append(f"Did you mean: {', '.join(suggestions)}")

                return {
                    "error": " | ".join(error_parts),
                    "success": False
                }

            # Use the resolved device type
            device_type = resolved_device_type

            # Get all devices
            all_devices = self.data_provider.get_all_devices_unfiltered()

            # Filter by device type using the new classifier
            filtered_devices = DeviceClassifier.filter_devices_by_type(all_devices, device_type)

            # Sort by name for consistent output
            filtered_devices.sort(key=lambda d: d.get("name", "").lower())

            # Calculate pagination
            total_count = len(filtered_devices)
            start_idx = offset
            end_idx = offset + limit
            paginated_devices = filtered_devices[start_idx:end_idx]
            has_more = end_idx < total_count

            # Log results
            self.info_log(f"💡 Found {total_count} '{device_type}' devices (returning {len(paginated_devices)} from offset {offset})")

            return {
                "device_type": device_type,
                "devices": paginated_devices,
                "count": len(paginated_devices),
                "total_count": total_count,
                "offset": offset,
                "has_more": has_more,
                "success": True
            }

        except Exception as e:
            return self.handle_exception(e, f"retrieving devices of type '{device_type}'")