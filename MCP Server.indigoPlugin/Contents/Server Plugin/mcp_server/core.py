"""
Core MCP server implementation separated from Indigo plugin logic.
"""

import asyncio
import json
import logging
import threading
from typing import Optional

from mcp.server.fastmcp import FastMCP

from interfaces.data_provider import DataProvider
from interfaces.vector_store_interface import VectorStoreInterface
from .tools.search_entities import SearchEntitiesHandler


class MCPServerCore:
    """Core MCP server implementation without Indigo dependencies."""
    
    def __init__(
        self,
        data_provider: DataProvider,
        vector_store: VectorStoreInterface,
        server_name: str = "indigo-mcp-server",
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize the MCP server core.
        
        Args:
            data_provider: Data provider for accessing entity data
            vector_store: Vector store for semantic search
            server_name: Name for the MCP server
            logger: Optional logger instance
        """
        self.data_provider = data_provider
        self.vector_store = vector_store
        self.server_name = server_name
        self.logger = logger or logging.getLogger(__name__)
        
        # MCP server instance
        self.mcp_server = None
        self.mcp_thread = None
        self._mcp_loop = None
        self._running = False
        
        # Initialize components
        self.search_handler = SearchEntitiesHandler(
            data_provider=data_provider,
            vector_store=vector_store,
            logger=logger
        )
    
    def start(self) -> None:
        """Start the MCP server."""
        if self._running:
            self.logger.warning("MCP server is already running")
            return
        
        try:
            # Create FastMCP instance
            self.mcp_server = FastMCP(self.server_name)
            
            # Register tools and resources
            self._register_tools()
            self._register_resources()
            
            # Start server in separate thread
            self.mcp_thread = threading.Thread(
                target=self._run_server,
                daemon=True,
                name="MCP-Server-Thread"
            )
            self.mcp_thread.start()
            self._running = True
            
            self.logger.info(f"MCP server '{self.server_name}' started")
            
        except Exception as e:
            self.logger.error(f"Failed to start MCP server: {e}")
            raise
    
    def stop(self) -> None:
        """Stop the MCP server."""
        if not self._running:
            return
        
        try:
            self._running = False
            
            # Signal server to stop
            if self._mcp_loop:
                self._mcp_loop.call_soon_threadsafe(self._mcp_loop.stop)
            
            # Wait for thread to finish
            if self.mcp_thread and self.mcp_thread.is_alive():
                self.mcp_thread.join(timeout=5.0)
            
            self.logger.info("MCP server stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping MCP server: {e}")
    
    def _run_server(self) -> None:
        """Run the MCP server in its own event loop."""
        try:
            # Create new event loop for this thread
            self._mcp_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._mcp_loop)
            
            # Run the server
            self._mcp_loop.run_until_complete(
                self.mcp_server.run()
            )
            
        except Exception as e:
            self.logger.error(f"MCP server error: {e}")
        finally:
            if self._mcp_loop:
                self._mcp_loop.close()
    
    def _register_tools(self) -> None:
        """Register MCP tools."""
        
        @self.mcp_server.tool()
        def search_entities(query: str) -> str:
            """
            Search for Indigo devices, variables, and actions using natural language.
            
            Args:
                query: Natural language search query
                
            Returns:
                JSON string with search results
            """
            try:
                results = self.search_handler.search(query)
                return json.dumps(results, indent=2)
                
            except Exception as e:
                self.logger.error(f"Search error: {e}")
                return json.dumps({"error": str(e), "query": query})
    
    def _register_resources(self) -> None:
        """Register MCP resources for read-only access to Indigo entities."""
        
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
        
        @self.mcp_server.resource("indigo://variables")
        def list_variables() -> str:
            """List all Indigo variables."""
            try:
                variables = self.data_provider.get_all_variables()
                return json.dumps(variables, indent=2)
                
            except Exception as e:
                self.logger.error(f"Error listing variables: {e}")
                return json.dumps({"error": str(e)})
        
        @self.mcp_server.resource("indigo://variables/{variable_id}")
        def get_variable(variable_id: str) -> str:
            """Get details for a specific variable."""
            try:
                variable = self.data_provider.get_variable(int(variable_id))
                if variable is None:
                    return json.dumps({"error": f"Variable {variable_id} not found"})
                
                return json.dumps(variable, indent=2)
                    
            except Exception as e:
                self.logger.error(f"Error getting variable {variable_id}: {e}")
                return json.dumps({"error": str(e)})
        
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
    
    @property
    def is_running(self) -> bool:
        """Check if the MCP server is running."""
        return self._running