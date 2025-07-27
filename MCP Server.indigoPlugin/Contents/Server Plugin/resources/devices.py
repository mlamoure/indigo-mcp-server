"""
Device resource handler for MCP Server.
"""

import json
import logging
from typing import Optional

from mcp.server.fastmcp import FastMCP
from adapters.data_provider import DataProvider


class DeviceResource:
    """Handles device-related MCP resources."""
    
    def __init__(self, mcp_server: FastMCP, data_provider: DataProvider, logger: Optional[logging.Logger] = None):
        """
        Initialize the device resource handler.
        
        Args:
            mcp_server: FastMCP server instance
            data_provider: Data provider for accessing entity data
            logger: Optional logger instance
        """
        self.mcp_server = mcp_server
        self.data_provider = data_provider
        self.logger = logger or logging.getLogger(__name__)
        
        # Register resources
        self._register_resources()
    
    def _register_resources(self) -> None:
        """Register device-related resources with the MCP server."""
        
        @self.mcp_server.resource("indigo://devices")
        def list_devices() -> str:
            """List all Indigo devices."""
            try:
                devices = self.data_provider.get_all_devices()
                return json.dumps(devices, indent=2)
                
            except Exception as e:
                self.logger.error(f"Error listing devices: {e}")
                return json.dumps({"error": str(e)})
        
        @self.mcp_server.resource("indigo://devices/{device_id}")
        def get_device(device_id: str) -> str:
            """Get details for a specific device."""
            try:
                device = self.data_provider.get_device(int(device_id))
                if device is None:
                    return json.dumps({"error": f"Device {device_id} not found"})
                
                return json.dumps(device, indent=2)
                    
            except Exception as e:
                self.logger.error(f"Error getting device {device_id}: {e}")
                return json.dumps({"error": str(e)})