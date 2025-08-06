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
from .tools.get_devices_by_type import GetDevicesByTypeHandler
from .tools.device_control import DeviceControlHandler
from .tools.variable_control import VariableControlHandler
from .tools.action_control import ActionControlHandler
from .tools.historical_analysis import HistoricalAnalysisHandler
from .resources import DeviceResource, VariableResource, ActionResource
from .security import AuthManager, CertManager, SecurityConfig, AccessMode
from .common.json_encoder import safe_json_dumps
from .common.indigo_device_types import IndigoDeviceType, IndigoEntityType


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
            
            # Initialize get devices by type handler
            self.get_devices_by_type_handler = GetDevicesByTypeHandler(
                data_provider=self.data_provider,
                logger=self.logger
            )
            
            # Initialize control handlers
            self.device_control_handler = DeviceControlHandler(
                data_provider=self.data_provider,
                logger=self.logger
            )
            self.variable_control_handler = VariableControlHandler(
                data_provider=self.data_provider,
                logger=self.logger
            )
            self.action_control_handler = ActionControlHandler(
                data_provider=self.data_provider,
                logger=self.logger
            )
            self.historical_analysis_handler = HistoricalAnalysisHandler(
                data_provider=self.data_provider,
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
        def search_entities(
            query: str,
            device_types: list[str] = None,
            entity_types: list[str] = None
        ) -> str:
            """
            Search for Indigo entities using natural language with intelligent result limiting.
            
            This tool performs semantic search across your Indigo system to find devices, 
            variables, and actions that match your query. It uses AI embeddings to understand
            the meaning and context of your search, with smart result limits and field optimization.
            
            RESULT LIMITING:
            The search automatically adjusts result count and detail level based on your query:
            - Default queries: 10 results with full entity details
            - "few"/"some" queries: 5 results with full details  
            - "many"/"list" queries: 20 results with minimal fields for performance
            - "all" queries: 50 results with minimal fields for performance
            - "one"/"single" queries: 1 result with full details
            
            When results are truncated, you'll receive a clear message like:
            "Found 855 entities (showing top 10 - use more specific query for additional results)"
            
            FIELD OPTIMIZATION:
            Large result sets (20+ results) automatically use minimal fields including:
            name, class, id, deviceTypeId, description, model, onOffState, states
            
            Args:
                query: Natural language search query (e.g., "temperature sensors", "few lights in bedroom")
                device_types: Optional list of device types to filter by. When provided, only 
                             devices will be returned. Valid types: dimmer, relay, sensor, multiio,
                             speedcontrol, sprinkler, thermostat, device
                entity_types: Optional list of entity types to search. Valid types: device, variable, action
                             Note: device_types and entity_types are mutually exclusive - if device_types
                             is provided, entity_types is ignored and only devices are searched.
                
            Returns:
                JSON with search results grouped by entity type, including relevance scores and
                metadata about truncation/field reduction when applicable
                
            Examples:
                - search_entities("temperature sensors") - Returns 10 sensors with full details
                - search_entities("show me all lights") - Returns 50 lights with minimal fields
                - search_entities("few dimmer switches") - Returns 5 dimmers with full details
                - search_entities("many motion sensors") - Returns 20 sensors with minimal fields
                - search_entities("lights", device_types=["dimmer"]) - Find only dimmer devices
                - search_entities("morning", entity_types=["action"]) - Find only actions
            """
            try:
                # Validate device types
                if device_types:
                    invalid_device_types = [dt for dt in device_types if not IndigoDeviceType.is_valid_type(dt)]
                    if invalid_device_types:
                        return safe_json_dumps({
                            "error": f"Invalid device types: {invalid_device_types}. Valid types: {IndigoDeviceType.get_all_types()}",
                            "query": query
                        })
                
                # Validate entity types
                if entity_types:
                    invalid_entity_types = [et for et in entity_types if not IndigoEntityType.is_valid_type(et)]
                    if invalid_entity_types:
                        return safe_json_dumps({
                            "error": f"Invalid entity types: {invalid_entity_types}. Valid types: {IndigoEntityType.get_all_types()}",
                            "query": query
                        })
                
                results = self.search_handler.search(query, device_types, entity_types)
                return safe_json_dumps(results)
                
            except Exception as e:
                self.logger.error(f"Search error: {e}")
                return safe_json_dumps({"error": str(e), "query": query})
        
        @self.mcp_server.tool()
        def get_devices_by_type(device_type: str) -> str:
            """
            Get all devices of a specific type with complete properties.
            
            This tool retrieves all devices that match a specific device type. Unlike search_entities,
            this returns ALL devices of the type without semantic filtering, making it ideal for
            getting complete device lists or when you know exactly what type you need.
            
            Args:
                device_type: The device type to retrieve. Valid types: dimmer, relay, sensor, 
                           multiio, speedcontrol, sprinkler, thermostat, device
                
            Returns:
                JSON with all devices of the specified type, including all properties
                
            Examples:
                - get_devices_by_type("dimmer") - Get all dimmer devices
                - get_devices_by_type("sensor") - Get all sensor devices
                - get_devices_by_type("thermostat") - Get all thermostat devices
                
            When to use this vs search_entities:
                - Use this when you need ALL devices of a specific type
                - Use this when you don't need semantic/natural language matching
                - Use search_entities when you need to find devices by context or description
            """
            try:
                result = self.get_devices_by_type_handler.get_devices(device_type)
                return safe_json_dumps(result)
            except Exception as e:
                self.logger.error(f"Get devices by type error: {e}")
                return safe_json_dumps({"error": str(e), "device_type": device_type})
        
        @self.mcp_server.tool()
        def device_turn_on(device_id: int) -> str:
            """
            Turn on a device.
            
            Args:
                device_id: The ID of the device to turn on
                
            Returns:
                JSON string with operation results
            """
            try:
                result = self.device_control_handler.turn_on(device_id)
                return safe_json_dumps(result)
            except Exception as e:
                self.logger.error(f"Device turn on error: {e}")
                return safe_json_dumps({"error": str(e)})
        
        @self.mcp_server.tool()
        def device_turn_off(device_id: int) -> str:
            """
            Turn off a device.
            
            Args:
                device_id: The ID of the device to turn off
                
            Returns:
                JSON string with operation results
            """
            try:
                result = self.device_control_handler.turn_off(device_id)
                return safe_json_dumps(result)
            except Exception as e:
                self.logger.error(f"Device turn off error: {e}")
                return safe_json_dumps({"error": str(e)})
        
        @self.mcp_server.tool()
        def device_set_brightness(device_id: int, brightness: float) -> str:
            """
            Set the brightness level of a dimmable device.
            
            Args:
                device_id: The ID of the device
                brightness: Brightness level (0-1 or 0-100)
                
            Returns:
                JSON string with operation results
            """
            try:
                result = self.device_control_handler.set_brightness(device_id, brightness)
                return safe_json_dumps(result)
            except Exception as e:
                self.logger.error(f"Device set brightness error: {e}")
                return safe_json_dumps({"error": str(e)})
        
        @self.mcp_server.tool()
        def variable_update(variable_id: int, value: str) -> str:
            """
            Update a variable's value.
            
            Args:
                variable_id: The ID of the variable to update
                value: The new value for the variable
                
            Returns:
                JSON string with operation results
            """
            try:
                result = self.variable_control_handler.update(variable_id, value)
                return safe_json_dumps(result)
            except Exception as e:
                self.logger.error(f"Variable update error: {e}")
                return safe_json_dumps({"error": str(e)})
        
        @self.mcp_server.tool()
        def action_execute_group(action_group_id: int, delay: int = None) -> str:
            """
            Execute an action group.
            
            Args:
                action_group_id: The ID of the action group to execute
                delay: Optional delay in seconds before execution
                
            Returns:
                JSON string with operation results
            """
            try:
                result = self.action_control_handler.execute(action_group_id, delay)
                return safe_json_dumps(result)
            except Exception as e:
                self.logger.error(f"Action execute error: {e}")
                return safe_json_dumps({"error": str(e), "success": False})
        
        @self.mcp_server.tool()
        def analyze_historical_data(
            query: str,
            device_names: list[str],
            time_range_days: int = 30
        ) -> str:
            """
            Analyze historical device data using natural language queries and LangGraph workflow.
            
            Args:
                query: Natural language query about device behavior or patterns
                device_names: List of device names to analyze
                time_range_days: Number of days to analyze (1-365, default: 30)
                
            Returns:
                JSON string with analysis results and insights
            """
            try:
                result = self.historical_analysis_handler.analyze_historical_data(
                    query=query,
                    device_names=device_names,
                    time_range_days=time_range_days
                )
                return safe_json_dumps(result)
            except Exception as e:
                self.logger.error(f"Historical analysis error: {e}")
                return safe_json_dumps({"error": str(e), "success": False})
    
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