"""
Action resource handler for MCP Server.
"""

import json
import logging
from typing import Optional

from fastmcp import FastMCP
from ..adapters.data_provider import DataProvider


class ActionResource:
    """Handles action-related MCP resources."""
    
    def __init__(self, mcp_server: FastMCP, data_provider: DataProvider, logger: Optional[logging.Logger] = None):
        """
        Initialize the action resource handler.
        
        Args:
            mcp_server: FastMCP server instance
            data_provider: Data provider for accessing entity data
            logger: Optional logger instance
        """
        self.mcp_server = mcp_server
        self.data_provider = data_provider
        self.logger = logger or logging.getLogger("Plugin")
        
        # Register resources
        self._register_resources()
    
    def _register_resources(self) -> None:
        """Register action-related resources with the MCP server."""
        
        @self.mcp_server.resource("indigo://actions")
        def list_actions() -> str:
            """List all Indigo action groups."""
            try:
                actions = self.data_provider.get_all_actions()
                return json.dumps(actions, indent=2)
                
            except Exception as e:
                self.logger.error(f"Error listing actions: {e}")
                return json.dumps({"error": str(e)})
        
        @self.mcp_server.resource("indigo://actions/{action_id}")
        def get_action(action_id: str) -> str:
            """Get details for a specific action group."""
            try:
                action = self.data_provider.get_action(int(action_id))
                if action is None:
                    return json.dumps({"error": f"Action group {action_id} not found"})
                
                return json.dumps(action, indent=2)
                    
            except Exception as e:
                self.logger.error(f"Error getting action {action_id}: {e}")
                return json.dumps({"error": str(e)})