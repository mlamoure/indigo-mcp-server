"""
Core MCP server implementation separated from Indigo plugin logic.
"""

import json
import logging
import os
import threading
import uvicorn
from typing import Optional

from fastmcp import FastMCP
from fastmcp.server.auth import BearerAuthProvider

from .adapters.data_provider import DataProvider
from .adapters.vector_store_interface import VectorStoreInterface
from .common.vector_store.vector_store_manager import VectorStoreManager
from .tools.search_entities import SearchEntitiesHandler
from .resources import DeviceResource, VariableResource, ActionResource
from .security import AuthManager, CertManager, SecurityConfig, AccessMode
from .common.json_encoder import safe_json_dumps


class MCPServerCore:
    """Core MCP server implementation without Indigo dependencies."""
    
    def __init__(
        self,
        data_provider: DataProvider,
        server_name: str = "indigo-mcp-server",
        port: int = 8080,
        access_mode: AccessMode = AccessMode.LOCAL_ONLY,
        bearer_token: Optional[str] = None,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize the MCP server core.
        
        Args:
            data_provider: Data provider for accessing entity data
            server_name: Name for the MCP server
            port: HTTP port for the server
            access_mode: Server access mode (local only or remote access)
            bearer_token: Bearer token for authentication
            logger: Optional logger instance
        """
        self.data_provider = data_provider
        self.server_name = server_name
        self.port = port
        self.logger = logger or logging.getLogger("Plugin")
        
        # Get database path from environment variable
        db_path = os.environ.get("DB_FILE")
        if not db_path:
            raise ValueError("DB_FILE environment variable must be set")
        
        # Initialize security configuration
        base_security_path = os.path.dirname(db_path)
        self.security_config = SecurityConfig(
            base_path=base_security_path,
            access_mode=access_mode,
            bearer_token=bearer_token,
            logger=self.logger
        )
        
        # Initialize certificate manager for SSL/TLS
        self.cert_manager = CertManager(
            cert_dir=self.security_config.get_ssl_cert_dir(),
            logger=self.logger
        )
        
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
            
            # Disable authentication for now due to FastMCP compatibility issues
            # TODO: Implement proper TokenVerifier-compatible authentication
            auth_provider = None
            
            # Create FastMCP instance without authentication
            self.mcp_server = FastMCP(self.server_name, auth=auth_provider)
            
            # Register tools
            self._register_tools()
            
            # Initialize resource handlers
            self.device_resource = DeviceResource(self.mcp_server, self.data_provider, self.logger)
            self.variable_resource = VariableResource(self.mcp_server, self.data_provider, self.logger)
            self.action_resource = ActionResource(self.mcp_server, self.data_provider, self.logger)
            
            # Ensure SSL certificates if SSL is enabled
            if self.security_config.is_ssl_enabled():
                self.cert_manager.ensure_certificates()
            
            # Start server in separate thread
            self.mcp_thread = threading.Thread(
                target=self._run_server,
                daemon=True,
                name="MCP-Server-Thread"
            )
            self.mcp_thread.start()
            self._running = True
            
            # Log comprehensive configuration
            self._log_server_configuration()
            
        except Exception as e:
            self.logger.error(f"Failed to start MCP server: {e}")
            raise
    
    def stop(self) -> None:
        """Stop the MCP server."""
        if not self._running:
            return
        
        try:
            self._running = False
            
            # Wait for thread to finish
            if self.mcp_thread and self.mcp_thread.is_alive():
                self.mcp_thread.join(timeout=5.0)
            
            # Stop vector store manager
            self.vector_store_manager.stop()
            
            self.logger.info("MCP server stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping MCP server: {e}")
    
    def _run_server(self) -> None:
        """Run the MCP server with HTTP transport and optional SSL."""
        try:
            host = self.security_config.get_host_address()
            
            # Prepare uvicorn configuration
            uvicorn_config = {
                "host": host,
                "port": self.port,
                "log_level": "warning"  # Reduce uvicorn logging noise
            }
            
            # Add SSL configuration if enabled
            if self.security_config.is_ssl_enabled():
                cert_file, key_file = self.cert_manager.ensure_certificates()
                uvicorn_config.update({
                    "ssl_keyfile": key_file,
                    "ssl_certfile": cert_file
                })
            
            # Use FastMCP's built-in HTTP server with uvicorn configuration
            # FastMCP handles the ASGI app internally
            self.mcp_server.run(
                transport="http",
                **uvicorn_config
            )
            
        except Exception as e:
            self.logger.error(f"MCP server error: {e}")
    
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
                return safe_json_dumps(results)
                
            except Exception as e:
                self.logger.error(f"Search error: {e}")
                return safe_json_dumps({"error": str(e), "query": query})
    
    def _create_static_token_auth(self):
        """
        Create a static token authentication provider.
        Note: This is a simplified implementation for static tokens.
        """
        class StaticTokenAuth:
            def __init__(self, token):
                self.token = token
            
            def __call__(self, request):
                auth_header = request.headers.get("Authorization", "")
                expected = f"Bearer {self.token}"
                return auth_header == expected
        
        return StaticTokenAuth(self.security_config.bearer_token)
    
    def _log_server_configuration(self) -> None:
        """Log comprehensive server configuration for easy copy/paste."""
        status_info = self.security_config.get_status_info(self.port)
        claude_config = self.security_config.get_claude_desktop_config(self.port)
        
        # Create formatted configuration message
        config_lines = [
            "MCP Server Configuration:",
            f"  Access Mode: {status_info['access_mode'].replace('_', ' ').title()}",
            f"  Server URL: {status_info['server_url']}",
            f"  Host Address: {status_info['host_address']}:{self.port}",
            f"  SSL Enabled: {status_info['ssl_enabled']}",
            f"  Authentication: Disabled (temporarily due to FastMCP compatibility)"
        ]
        
        if status_info['ssl_enabled']:
            config_lines.append(f"  SSL Cert Dir: {status_info['ssl_cert_dir']}")
        
        # Create simplified Claude config without bearer token
        simplified_config = {
            "mcpServers": {
                "indigo": {
                    "command": "npx",
                    "args": [
                        "mcp-remote",
                        status_info['server_url'] + "/mcp"
                    ]
                }
            }
        }
        
        config_lines.extend([
            "",
            "Claude Desktop (or other MCP compatible tool) setup:",
            json.dumps(simplified_config, indent=2)
        ])
        
        # Log as a single multi-line message
        self.logger.info("\n".join(config_lines))
    
    @property
    def is_running(self) -> bool:
        """Check if the MCP server is running."""
        return self._running
    
    def get_security_config(self) -> SecurityConfig:
        """Get the security configuration."""
        return self.security_config