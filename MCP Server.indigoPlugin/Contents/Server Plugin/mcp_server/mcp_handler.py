"""
MCP Handler for Indigo IWS integration.
Implements standards-compliant MCP protocol over Indigo's built-in web server.
"""

import json
import logging
import os
import secrets
import time
from typing import Any, Dict, List, Optional, Union

from .adapters.data_provider import DataProvider
from .common.indigo_device_types import IndigoDeviceType, IndigoEntityType, DeviceTypeResolver
from .common.json_encoder import safe_json_dumps
from .common.vector_store.vector_store_manager import VectorStoreManager
from .handlers.list_handlers import ListHandlers
from .resource_registry import get_resource_schemas
from .tool_registry import get_tool_schemas
from .tool_wrappers import ToolWrappers
from .tools.action_control import ActionControlHandler
from .tools.device_control import DeviceControlHandler
from .tools.get_devices_by_type import GetDevicesByTypeHandler
from .tools.historical_analysis import HistoricalAnalysisHandler
from .tools.log_query import LogQueryHandler
from .tools.plugin_control import PluginControlHandler
from .tools.rgb_control import RGBControlHandler
from .tools.search_entities import SearchEntitiesHandler
from .tools.thermostat_control import ThermostatControlHandler
from .tools.variable_control import VariableControlHandler


class MCPHandler:
    """Handles MCP protocol requests through Indigo IWS."""
    
    # MCP Protocol version we support
    PROTOCOL_VERSION = "2025-11-25"
    
    def __init__(
        self,
        data_provider: DataProvider,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize the MCP handler.
        
        Args:
            data_provider: Data provider for accessing entity data
            logger: Optional logger instance
        """
        self.data_provider = data_provider
        self.logger = logger or logging.getLogger("Plugin")

        # Session management
        self._sessions = {}  # session_id -> {created, last_seen, client_info}

        # Get database path from environment variable
        db_path = os.environ.get("DB_FILE")
        if not db_path:
            raise ValueError("DB_FILE environment variable must be set")

        # Initialize vector store manager
        self.vector_store_manager = VectorStoreManager(
            data_provider=data_provider,
            db_path=db_path,
            logger=self.logger,
            update_interval=300,  # 5 minutes
        )

        # Start vector store manager (it will log its own progress)
        self.vector_store_manager.start()

        # Initialize handlers
        self._init_handlers()

        # Register tools and resources
        self._tools = {}
        self._resources = {}
        self._register_tools()
        self._register_resources()

        self.logger.info(f"\t🚀 MCP Server ready ({len(self._tools)} tools, {len(self._resources)} resources)")
        self.logger.info(f"\t🌐 Endpoint: /message/com.vtmikel.mcp_server/mcp/")
        
    def _init_handlers(self):
        """Initialize all handler instances."""
        # Search handler with vector store
        self.search_handler = SearchEntitiesHandler(
            data_provider=self.data_provider,
            vector_store=self.vector_store_manager.get_vector_store(),
            logger=self.logger,
        )

        # Get devices by type handler
        self.get_devices_by_type_handler = GetDevicesByTypeHandler(
            data_provider=self.data_provider,
            logger=self.logger
        )

        # List handlers for shared logic
        self.list_handlers = ListHandlers(
            data_provider=self.data_provider,
            logger=self.logger
        )

        # Control handlers
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
        self.rgb_control_handler = RGBControlHandler(
            data_provider=self.data_provider,
            logger=self.logger
        )
        self.thermostat_control_handler = ThermostatControlHandler(
            data_provider=self.data_provider,
            logger=self.logger
        )
        self.historical_analysis_handler = HistoricalAnalysisHandler(
            data_provider=self.data_provider,
            logger=self.logger
        )
        self.log_query_handler = LogQueryHandler(
            data_provider=self.data_provider,
            logger=self.logger
        )
        self.plugin_control_handler = PluginControlHandler(
            data_provider=self.data_provider,
            logger=self.logger
        )

        # Initialize tool wrappers with all handlers
        self.tool_wrappers = ToolWrappers(
            search_handler=self.search_handler,
            get_devices_by_type_handler=self.get_devices_by_type_handler,
            device_control_handler=self.device_control_handler,
            rgb_control_handler=self.rgb_control_handler,
            thermostat_control_handler=self.thermostat_control_handler,
            variable_control_handler=self.variable_control_handler,
            action_control_handler=self.action_control_handler,
            historical_analysis_handler=self.historical_analysis_handler,
            list_handlers=self.list_handlers,
            log_query_handler=self.log_query_handler,
            plugin_control_handler=self.plugin_control_handler,
            data_provider=self.data_provider,
            logger=self.logger
        )
    
    def stop(self):
        """Stop the MCP handler and cleanup resources."""
        if self.vector_store_manager:
            self.vector_store_manager.stop()
    
    def handle_request(
        self,
        method: str,
        headers: Dict[str, str],
        body: str
    ) -> Dict[str, Any]:
        """
        Handle an MCP request from Indigo IWS.

        Args:
            method: HTTP method (GET, POST, etc.)
            headers: Request headers
            body: Request body as string

        Returns:
            Dict with status, headers, and content for IWS response
        """
        # Normalize headers to lowercase
        headers = {k.lower(): v for k, v in headers.items()}
        accept = headers.get("accept", "")
        
        # Only support POST
        if method != "POST":
            return {
                "status": 405,
                "headers": {"Allow": "POST"},
                "content": ""
            }

        # Check Accept header - client must accept json, event-stream, or */* (wildcard)
        if "application/json" not in accept and "text/event-stream" not in accept and "*/*" not in accept:
            self.logger.debug(f"Invalid Accept header: '{accept}'")
            return {
                "status": 406,
                "headers": {"Content-Type": "text/plain"},
                "content": "Not Acceptable"
            }

        # Parse JSON body
        try:
            payload = json.loads(body) if body else None
        except Exception as e:
            self.logger.error(f"Failed to parse JSON body: {e}")
            return self._json_response(
                self._json_error(None, -32700, "Parse error"),
                status=200
            )

        # Handle empty or invalid payload
        if not payload:
            return self._json_response(
                self._json_error(None, -32600, "Invalid Request"),
                status=200
            )

        # MCP 2025-06-18 spec removes support for JSON-RPC batching
        if isinstance(payload, list):
            self.logger.debug("Batch requests not supported")
            return self._json_response(
                self._json_error(None, -32600, "Batch requests not supported"),
                status=200
            )
        
        # Process single message
        try:
            # Single message
            resp = self._dispatch_message(payload, headers)
            
            # If it was a notification (no id), return 200 with empty JSON for IWS compatibility
            if isinstance(payload, dict) and "id" not in payload:
                return {
                    "status": 200, 
                    "headers": {"Content-Type": "application/json; charset=utf-8"},
                    "content": "{}"
                }
            
            # Check for session ID in response
            extra_headers = {}
            if isinstance(resp, dict) and "_mcp_session_id" in resp:
                session_id = resp.pop("_mcp_session_id")
                extra_headers["Mcp-Session-Id"] = session_id
            
            return {
                "status": 200,
                "headers": {
                    "Content-Type": "application/json; charset=utf-8",
                    **extra_headers
                },
                "content": json.dumps(resp)
            }
                
        except Exception as e:
            self.logger.exception("Unhandled MCP error")
            return self._json_response(
                self._json_error(None, -32603, "Internal error"),
                status=200
            )
    
    def _dispatch_message(
        self,
        msg: Dict[str, Any],
        headers: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """
        Dispatch a single JSON-RPC message.

        Args:
            msg: JSON-RPC message
            headers: Request headers

        Returns:
            JSON-RPC response or None for notifications
        """
        # Validate JSON-RPC structure
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or "method" not in msg:
            self.logger.debug(f"Invalid JSON-RPC message structure")
            return self._json_error(msg.get("id"), -32600, "Invalid Request")

        msg_id = msg.get("id")  # May be None for notifications
        method = msg["method"]
        params = msg.get("params") or {}

        # Extract client IP from headers (check common proxy headers first)
        client_ip = (
            headers.get("x-forwarded-for", "").split(",")[0].strip() or
            headers.get("x-real-ip", "") or
            headers.get("remote-addr", "") or
            "unknown"
        )

        # Log incoming request at INFO level (concise)
        session_id = headers.get("mcp-session-id", "")
        session_short = session_id[:8] if session_id else "none"

        # Get client info from session if available
        client_label = client_ip
        if session_id and session_id in self._sessions:
            session_data = self._sessions[session_id]
            # Try to use client name if available
            client_info = session_data.get("client_info", {})
            client_name = client_info.get("name", "")
            if client_name:
                client_label = f"{client_name}@{client_ip}"

        # Format method for logging
        if method.startswith("notifications/"):
            log_method = method.replace("notifications/", "notify:")
        elif "/" in method:
            log_method = method.replace("/", ":")
        else:
            log_method = method

        # Only log significant MCP operations at INFO, move protocol to DEBUG
        significant_methods = ["tools/call", "resources/read"]
        if any(method.startswith(sm) for sm in significant_methods):
            self.logger.info(f"📨 {log_method} | {client_label} | session: {session_short}")
        else:
            self.logger.debug(f"📨 {log_method} | {client_label} | session: {session_short}")
        
        # MCP 2025-06-18 requires MCP-Protocol-Version header for HTTP transport
        protocol_version_header = headers.get("mcp-protocol-version")
        if method != "initialize" and not method.startswith("notifications/") and self._sessions:
            if protocol_version_header and protocol_version_header != self.PROTOCOL_VERSION:
                self.logger.debug(f"Invalid protocol version: {protocol_version_header}")
                return self._json_error(msg_id, -32600, f"Unsupported protocol version: {protocol_version_header}")

        # Session validation (skip for initialize and notifications)
        session_id = headers.get("mcp-session-id")
        if method != "initialize" and not method.startswith("notifications/") and self._sessions:
            if not session_id or session_id not in self._sessions:
                self.logger.debug(f"Invalid session ID for {method}")
                return self._json_error(msg_id, -32600, "Missing or invalid Mcp-Session-Id")
            # Update last seen
            self._sessions[session_id]["last_seen"] = time.time()

        # Route to appropriate handler
        if method == "initialize":
            return self._handle_initialize(msg_id, params, client_ip)
        elif method == "ping":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
        elif method == "notifications/cancelled":
            self._handle_cancelled(params)
            return None
        elif method == "notifications/initialized":
            return None
        
        # Tool methods
        elif method == "tools/list":
            return self._handle_tools_list(msg_id, params)
        elif method == "tools/call":
            return self._handle_tools_call(msg_id, params)
        
        # Resource methods
        elif method == "resources/list":
            return self._handle_resources_list(msg_id, params)
        elif method == "resources/read":
            return self._handle_resources_read(msg_id, params)
        
        # Prompt methods (stubs for now)
        elif method == "prompts/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"prompts": []}
            }
        elif method == "prompts/get":
            return self._json_error(msg_id, -32602, "Unknown prompt")
        
        # Unknown method
        else:
            if method.startswith("notifications/"):
                # Unknown notifications ignored gracefully
                return None
            else:
                self.logger.debug(f"Unknown method: {method}")
                return self._json_error(msg_id, -32601, "Method not found")
    
    def _handle_initialize(
        self,
        msg_id: Any,
        params: Dict[str, Any],
        client_ip: str = "unknown"
    ) -> Dict[str, Any]:
        """Handle initialize request."""
        requested_version = str(params.get("protocolVersion") or "")
        client_info = params.get("clientInfo", {})
        client_name = client_info.get("name", "Unknown")

        # Check if we support the requested version
        if requested_version == self.PROTOCOL_VERSION:
            # Create new session
            session_id = secrets.token_urlsafe(24)
            self._sessions[session_id] = {
                "created": time.time(),
                "last_seen": time.time(),
                "client_info": client_info,
                "client_ip": client_ip
            }

            # Log new session creation with client details
            self.logger.info(f"🔌 New session: {client_name}@{client_ip} | session: {session_id[:8]}")

            result = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": self.PROTOCOL_VERSION,
                    "capabilities": {
                        "logging": {},
                        "prompts": {"listChanged": True},
                        "resources": {"subscribe": False, "listChanged": True},
                        "tools": {"listChanged": True}
                    },
                    "serverInfo": {
                        "name": "Indigo MCP Server",
                        "version": "2025.0.1"
                    }
                }
            }

            # Add session ID for header
            result["_mcp_session_id"] = session_id

            self.logger.info(f"\t✅ Client initialized: {client_name} | session: {session_id[:8]}")

            return result
        else:
            # Unsupported version
            self.logger.debug(f"Unsupported protocol version: {requested_version}")

            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32602,
                    "message": "Unsupported protocol version",
                    "data": {
                        "supported": [self.PROTOCOL_VERSION],
                        "requested": requested_version
                    }
                }
            }
    
    def _handle_cancelled(self, params: Dict[str, Any]):
        """Handle cancellation notification."""
        # In a synchronous implementation, we can't really cancel ongoing work
        # This is for async implementations only
        pass
    
    def _handle_tools_list(
        self, 
        msg_id: Any, 
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle tools/list request."""
        # Convert tool functions to tool descriptions
        tools = []
        for name, info in self._tools.items():
            tools.append({
                "name": name,
                "description": info["description"],
                "inputSchema": info["inputSchema"]
            })
        
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": tools
            }
        }
    
    def _handle_tools_call(
        self, 
        msg_id: Any, 
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle tools/call request."""
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})
        
        if tool_name not in self._tools:
            return self._json_error(msg_id, -32602, f"Unknown tool: {tool_name}")
        
        try:
            # Call the tool function
            result = self._tools[tool_name]["function"](**tool_args)

            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": result
                        }
                    ]
                }
            }
        except (TypeError, ValueError) as e:
            # MCP 2025-11-25: Input validation errors return as Tool Execution Errors
            # This enables model self-correction by returning error as tool result
            self.logger.warning(f"Tool {tool_name} validation error: {e}")
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": safe_json_dumps({
                                "error": str(e),
                                "tool": tool_name,
                                "success": False
                            })
                        }
                    ],
                    "isError": True
                }
            }
        except Exception as e:
            # Internal errors still return as JSON-RPC errors
            self.logger.error(f"Tool {tool_name} internal error: {e}")
            return self._json_error(
                msg_id,
                -32603,
                f"Tool execution failed: {str(e)}"
            )
    
    def _handle_resources_list(
        self, 
        msg_id: Any, 
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle resources/list request."""
        resources = []
        for uri, info in self._resources.items():
            resources.append({
                "uri": uri,
                "name": info["name"],
                "description": info["description"],
                "mimeType": "application/json"
            })
        
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "resources": resources
            }
        }
    
    def _handle_resources_read(
        self, 
        msg_id: Any, 
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle resources/read request."""
        uri = params.get("uri")
        
        if not uri:
            return self._json_error(msg_id, -32602, "Missing uri parameter")
        
        # Try exact match first
        if uri in self._resources:
            try:
                content = self._resources[uri]["function"]()
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "contents": [
                            {
                                "uri": uri,
                                "mimeType": "application/json",
                                "text": content
                            }
                        ]
                    }
                }
            except Exception as e:
                self.logger.error(f"Resource {uri} error: {e}")
                return self._json_error(
                    msg_id, 
                    -32603, 
                    f"Resource read failed: {str(e)}"
                )
        
        # Try pattern matching for parameterized resources
        for pattern, info in self._resources.items():
            if "{" in pattern:  # Has parameters
                # Simple pattern matching (e.g., "indigo://devices/{id}")
                base_pattern = pattern.split("{")[0]
                if uri.startswith(base_pattern):
                    # Extract parameter value
                    param_value = uri[len(base_pattern):]
                    if param_value:
                        try:
                            content = info["function"](param_value)
                            return {
                                "jsonrpc": "2.0",
                                "id": msg_id,
                                "result": {
                                    "contents": [
                                        {
                                            "uri": uri,
                                            "mimeType": "application/json",
                                            "text": content
                                        }
                                    ]
                                }
                            }
                        except Exception as e:
                            self.logger.error(f"Resource {uri} error: {e}")
                            return self._json_error(
                                msg_id, 
                                -32603, 
                                f"Resource read failed: {str(e)}"
                            )
        
        return self._json_error(msg_id, -32002, f"Resource not found: {uri}")
    
    def _register_tools(self):
        """Register all available tools using extracted tool registry."""
        # Create tool functions dictionary mapping tool names to wrapper methods
        tool_functions = {
            "search_entities": self.tool_wrappers.tool_search_entities,
            "get_devices_by_type": self.tool_wrappers.tool_get_devices_by_type,
            "device_turn_on": self.tool_wrappers.tool_device_turn_on,
            "device_turn_off": self.tool_wrappers.tool_device_turn_off,
            "device_set_brightness": self.tool_wrappers.tool_device_set_brightness,
            "device_set_rgb_color": self.tool_wrappers.tool_device_set_rgb_color,
            "device_set_rgb_percent": self.tool_wrappers.tool_device_set_rgb_percent,
            "device_set_hex_color": self.tool_wrappers.tool_device_set_hex_color,
            "device_set_named_color": self.tool_wrappers.tool_device_set_named_color,
            "device_set_white_levels": self.tool_wrappers.tool_device_set_white_levels,
            "thermostat_set_heat_setpoint": self.tool_wrappers.tool_thermostat_set_heat_setpoint,
            "thermostat_set_cool_setpoint": self.tool_wrappers.tool_thermostat_set_cool_setpoint,
            "thermostat_set_hvac_mode": self.tool_wrappers.tool_thermostat_set_hvac_mode,
            "thermostat_set_fan_mode": self.tool_wrappers.tool_thermostat_set_fan_mode,
            "variable_update": self.tool_wrappers.tool_variable_update,
            "variable_create": self.tool_wrappers.tool_variable_create,
            "action_execute_group": self.tool_wrappers.tool_action_execute_group,
            "analyze_historical_data": self.tool_wrappers.tool_analyze_historical_data,
            "list_devices": self.tool_wrappers.tool_list_devices,
            "list_variables": self.tool_wrappers.tool_list_variables,
            "list_action_groups": self.tool_wrappers.tool_list_action_groups,
            "list_variable_folders": self.tool_wrappers.tool_list_variable_folders,
            "get_devices_by_state": self.tool_wrappers.tool_get_devices_by_state,
            "get_device_by_id": self.tool_wrappers.tool_get_device_by_id,
            "get_variable_by_id": self.tool_wrappers.tool_get_variable_by_id,
            "get_action_group_by_id": self.tool_wrappers.tool_get_action_group_by_id,
            "query_event_log": self.tool_wrappers.tool_query_event_log,
            "list_plugins": self.tool_wrappers.tool_list_plugins,
            "get_plugin_by_id": self.tool_wrappers.tool_get_plugin_by_id,
            "restart_plugin": self.tool_wrappers.tool_restart_plugin,
            "get_plugin_status": self.tool_wrappers.tool_get_plugin_status,
        }

        # Get tool schemas from registry
        self._tools = get_tool_schemas(tool_functions)

    def _register_resources(self):
        """Register all available resources using extracted resource registry."""
        # Create resource functions dictionary mapping resource names to wrapper methods
        resource_functions = {
            "list_devices": self.tool_wrappers.resource_list_devices,
            "get_device": self.tool_wrappers.resource_get_device,
            "list_variables": self.tool_wrappers.resource_list_variables,
            "get_variable": self.tool_wrappers.resource_get_variable,
            "list_actions": self.tool_wrappers.resource_list_actions,
            "get_action": self.tool_wrappers.resource_get_action,
        }

        # Get resource schemas from registry
        self._resources = get_resource_schemas(resource_functions)

    def _json_response(self, obj: Any, status: int = 200) -> Dict[str, Any]:
        """Create JSON response for IWS."""
        return {
            "status": status,
            "headers": {"Content-Type": "application/json; charset=utf-8"},
            "content": json.dumps(obj)
        }
    
    def _json_error(
        self, 
        msg_id: Any, 
        code: int, 
        message: str, 
        data: Any = None
    ) -> Dict[str, Any]:
        """Create JSON-RPC error response."""
        error = {
            "jsonrpc": "2.0",
            "error": {
                "code": code,
                "message": message
            }
        }
        
        if data is not None:
            error["error"]["data"] = data
        
        if msg_id is not None:
            error["id"] = msg_id
        
        return error