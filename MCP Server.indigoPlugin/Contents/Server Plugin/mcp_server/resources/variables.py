"""
Variable resource handler for MCP Server.
"""

import json
import logging
from typing import Optional

from fastmcp import FastMCP
from ..adapters.data_provider import DataProvider
from ..common.json_encoder import safe_json_dumps
from ..handlers import ListHandlers


class VariableResource:
    """Handles variable-related MCP resources."""
    
    def __init__(self, mcp_server: FastMCP, data_provider: DataProvider, logger: Optional[logging.Logger] = None):
        """
        Initialize the variable resource handler.
        
        Args:
            mcp_server: FastMCP server instance
            data_provider: Data provider for accessing entity data
            logger: Optional logger instance
        """
        self.mcp_server = mcp_server
        self.data_provider = data_provider
        self.logger = logger or logging.getLogger("Plugin")
        self.list_handlers = ListHandlers(data_provider, logger)
        
        # Register resources
        self._register_resources()
    
    def _register_resources(self) -> None:
        """Register variable-related resources with the MCP server."""
        
        @self.mcp_server.resource("indigo://variables")
        def list_variables() -> str:
            """List all Indigo variables."""
            try:
                variables = self.list_handlers.list_all_variables()
                return safe_json_dumps(variables)
                
            except Exception as e:
                self.logger.error(f"Error listing variables: {e}")
                return safe_json_dumps({"error": str(e)})
        
        @self.mcp_server.resource("indigo://variables/{variable_id}")
        def get_variable(variable_id: str) -> str:
            """Get details for a specific variable."""
            try:
                variable = self.data_provider.get_variable(int(variable_id))
                if variable is None:
                    return safe_json_dumps({"error": f"Variable {variable_id} not found"})
                
                return safe_json_dumps(variable)
                    
            except Exception as e:
                self.logger.error(f"Error getting variable {variable_id}: {e}")
                return safe_json_dumps({"error": str(e)})