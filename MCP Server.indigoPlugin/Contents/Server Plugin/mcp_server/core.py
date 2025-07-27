"""
Core MCP server implementation separated from Indigo plugin logic.
"""

import asyncio
import json
import logging
import os
import threading
from typing import Optional

from mcp.server.fastmcp import FastMCP

from adapters.data_provider import DataProvider
from adapters.vector_store_interface import VectorStoreInterface
from common.vector_store_manager import VectorStoreManager
from .tools.search_entities import SearchEntitiesHandler
from resources import DeviceResource, VariableResource, ActionResource


class MCPServerCore:
    """Core MCP server implementation without Indigo dependencies."""
    
    def __init__(
        self,
        data_provider: DataProvider,
        server_name: str = "indigo-mcp-server",
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize the MCP server core.
        
        Args:
            data_provider: Data provider for accessing entity data
            server_name: Name for the MCP server
            logger: Optional logger instance
        """
        self.data_provider = data_provider
        self.server_name = server_name
        self.logger = logger or logging.getLogger(__name__)
        
        # Get database path from environment variable
        db_path = os.environ.get("DB_FILE")
        if not db_path:
            raise ValueError("DB_FILE environment variable must be set")
        
        # Initialize vector store manager
        self.vector_store_manager = VectorStoreManager(
            data_provider=data_provider,
            db_path=db_path,
            logger=self.logger,
            update_interval=300  # 5 minutes
        )
        
        # MCP server instance
        self.mcp_server = None
        self.mcp_thread = None
        self._mcp_loop = None
        self._running = False
    
    def start(self) -> None:
        """Start the MCP server."""
        if self._running:
            self.logger.warning("MCP server is already running")
            return
        
        try:
            # Start vector store manager
            self.vector_store_manager.start()
            
            # Initialize search handler with vector store
            self.search_handler = SearchEntitiesHandler(
                data_provider=self.data_provider,
                vector_store=self.vector_store_manager.get_vector_store(),
                logger=self.logger
            )
            
            # Create FastMCP instance
            self.mcp_server = FastMCP(self.server_name)
            
            # Register tools
            self._register_tools()
            
            # Initialize resource handlers
            self.device_resource = DeviceResource(self.mcp_server, self.data_provider, self.logger)
            self.variable_resource = VariableResource(self.mcp_server, self.data_provider, self.logger)
            self.action_resource = ActionResource(self.mcp_server, self.data_provider, self.logger)
            
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
            
            # Stop vector store manager
            self.vector_store_manager.stop()
            
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
    
    
    @property
    def is_running(self) -> bool:
        """Check if the MCP server is running."""
        return self._running