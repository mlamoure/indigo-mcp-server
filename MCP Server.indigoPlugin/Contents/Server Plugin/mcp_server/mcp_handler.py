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
from .common.indigo_device_types import IndigoDeviceType, IndigoEntityType
from .common.json_encoder import safe_json_dumps
from .common.vector_store.vector_store_manager import VectorStoreManager
from .handlers.list_handlers import ListHandlers
from .tools.action_control import ActionControlHandler
from .tools.device_control import DeviceControlHandler
from .tools.get_devices_by_type import GetDevicesByTypeHandler
from .tools.historical_analysis import HistoricalAnalysisHandler
from .tools.search_entities import SearchEntitiesHandler
from .tools.variable_control import VariableControlHandler


class MCPHandler:
    """Handles MCP protocol requests through Indigo IWS."""
    
    # MCP Protocol version we support
    PROTOCOL_VERSION = "2025-03-26"
    
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
        
        # Start vector store manager
        self.vector_store_manager.start()
        
        # Initialize handlers
        self._init_handlers()
        
        # Register tools and resources
        self._tools = {}
        self._resources = {}
        self._register_tools()
        self._register_resources()
        
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
        self.historical_analysis_handler = HistoricalAnalysisHandler(
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
        
        # Only support POST; GET returns 405
        if method == "GET":
            return {
                "status": 405,
                "headers": {"Allow": "POST"},
                "content": ""
            }
        
        if method != "POST":
            return {
                "status": 405,
                "headers": {"Allow": "POST"},
                "content": ""
            }
        
        # Check Accept header - client must accept json or event-stream
        if "application/json" not in accept and "text/event-stream" not in accept:
            return {"status": 406, "content": "Not Acceptable"}
        
        # Parse JSON body
        try:
            payload = json.loads(body) if body else None
        except Exception:
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
        
        # Check if this is a batch of notifications/responses only (no requests)
        if isinstance(payload, list) and all(
            isinstance(x, dict) and "id" not in x for x in payload
        ):
            # Only notifications/responses - return 202 Accepted with no body
            return {"status": 202, "content": ""}
        
        # Process single message or batch
        try:
            if isinstance(payload, list):
                # Batch request - process all messages with IDs
                responses = []
                session_id = None
                
                for msg in payload:
                    if isinstance(msg, dict) and "id" in msg:
                        resp = self._dispatch_message(msg, headers)
                        if resp:  # Skip empty responses (notifications)
                            responses.append(resp)
                            # Check for session ID in response
                            if isinstance(resp, dict) and "_mcp_session_id" in resp:
                                session_id = resp.pop("_mcp_session_id")
                
                # Add session header if present
                extra_headers = {}
                if session_id:
                    extra_headers["Mcp-Session-Id"] = session_id
                
                return {
                    "status": 200,
                    "headers": {
                        "Content-Type": "application/json; charset=utf-8",
                        **extra_headers
                    },
                    "content": json.dumps(responses)
                }
            else:
                # Single message
                resp = self._dispatch_message(payload, headers)
                
                # If it was a notification (no id), return 202
                if isinstance(payload, dict) and "id" not in payload:
                    return {"status": 202, "content": ""}
                
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
            return self._json_error(msg.get("id"), -32600, "Invalid Request")
        
        msg_id = msg.get("id")  # May be None for notifications
        method = msg["method"]
        params = msg.get("params") or {}
        
        # Session validation (skip for initialize)
        session_id = headers.get("mcp-session-id")
        if method != "initialize" and self._sessions:
            if not session_id or session_id not in self._sessions:
                return self._json_error(msg_id, -32600, "Missing or invalid Mcp-Session-Id")
            # Update last seen
            self._sessions[session_id]["last_seen"] = time.time()
        
        # Route to appropriate handler
        if method == "initialize":
            return self._handle_initialize(msg_id, params)
        elif method == "ping":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
        elif method == "notifications/cancelled":
            # Best effort notification, no response
            self._handle_cancelled(params)
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
                "result": {"prompts": [], "nextCursor": None}
            }
        elif method == "prompts/get":
            return self._json_error(msg_id, -32602, "Unknown prompt")
        
        # Unknown method
        else:
            return self._json_error(msg_id, -32601, "Method not found")
    
    def _handle_initialize(
        self, 
        msg_id: Any, 
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle initialize request."""
        requested_version = str(params.get("protocolVersion") or "")
        client_info = params.get("clientInfo", {})
        
        # Check if we support the requested version
        if requested_version == self.PROTOCOL_VERSION:
            # Create new session
            session_id = secrets.token_urlsafe(24)
            self._sessions[session_id] = {
                "created": time.time(),
                "last_seen": time.time(),
                "client_info": client_info
            }
            
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
            return result
        else:
            # Unsupported version
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
        request_id = params.get("requestId")
        reason = params.get("reason", "")
        
        # Log cancellation request
        self.logger.info(f"Cancellation requested for {request_id}: {reason}")
        
        # In a synchronous implementation, we can't really cancel ongoing work
        # This would be used in an async implementation to stop long-running tasks
    
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
                "tools": tools,
                "nextCursor": None
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
        except Exception as e:
            self.logger.error(f"Tool {tool_name} error: {e}")
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
                "resources": resources,
                "nextCursor": None
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
        """Register all available tools."""
        # Search entities tool
        self._tools["search_entities"] = {
            "description": "Search for Indigo entities using natural language",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query"
                    },
                    "device_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional device types to filter"
                    },
                    "entity_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional entity types to search"
                    },
                    "state_filter": {
                        "type": "object",
                        "description": "Optional state conditions to filter results"
                    }
                },
                "required": ["query"]
            },
            "function": self._tool_search_entities
        }
        
        # Get devices by type
        self._tools["get_devices_by_type"] = {
            "description": "Get all devices of a specific type",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "device_type": {
                        "type": "string",
                        "description": "Device type (dimmer, relay, sensor, etc.)"
                    }
                },
                "required": ["device_type"]
            },
            "function": self._tool_get_devices_by_type
        }
        
        # Device control tools
        self._tools["device_turn_on"] = {
            "description": "Turn on a device",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "integer",
                        "description": "The ID of the device to turn on"
                    }
                },
                "required": ["device_id"]
            },
            "function": self._tool_device_turn_on
        }
        
        self._tools["device_turn_off"] = {
            "description": "Turn off a device",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "integer",
                        "description": "The ID of the device to turn off"
                    }
                },
                "required": ["device_id"]
            },
            "function": self._tool_device_turn_off
        }
        
        self._tools["device_set_brightness"] = {
            "description": "Set device brightness level",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "integer",
                        "description": "The ID of the device"
                    },
                    "brightness": {
                        "type": "number",
                        "description": "Brightness level (0-1 or 0-100)"
                    }
                },
                "required": ["device_id", "brightness"]
            },
            "function": self._tool_device_set_brightness
        }
        
        # Variable control
        self._tools["variable_update"] = {
            "description": "Update a variable's value",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "variable_id": {
                        "type": "integer",
                        "description": "The ID of the variable"
                    },
                    "value": {
                        "type": "string",
                        "description": "The new value for the variable"
                    }
                },
                "required": ["variable_id", "value"]
            },
            "function": self._tool_variable_update
        }
        
        # Action group control
        self._tools["action_execute_group"] = {
            "description": "Execute an action group",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "action_group_id": {
                        "type": "integer",
                        "description": "The ID of the action group"
                    },
                    "delay": {
                        "type": "integer",
                        "description": "Optional delay in seconds"
                    }
                },
                "required": ["action_group_id"]
            },
            "function": self._tool_action_execute_group
        }
        
        # Historical analysis
        self._tools["analyze_historical_data"] = {
            "description": "Analyze historical device data",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language query about historical data"
                    },
                    "device_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Device names to analyze"
                    },
                    "time_range_days": {
                        "type": "integer",
                        "description": "Number of days to analyze (default: 30)"
                    }
                },
                "required": ["query", "device_names"]
            },
            "function": self._tool_analyze_historical_data
        }
        
        # List tools
        self._tools["list_devices"] = {
            "description": "List all devices with optional state filtering",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "state_filter": {
                        "type": "object",
                        "description": "Optional state conditions to filter devices"
                    }
                }
            },
            "function": self._tool_list_devices
        }
        
        self._tools["list_variables"] = {
            "description": "List all variables",
            "inputSchema": {
                "type": "object",
                "properties": {}
            },
            "function": self._tool_list_variables
        }
        
        self._tools["list_action_groups"] = {
            "description": "List all action groups",
            "inputSchema": {
                "type": "object",
                "properties": {}
            },
            "function": self._tool_list_action_groups
        }
        
        # State-based queries
        self._tools["get_devices_by_state"] = {
            "description": "Get devices by state conditions",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "state_conditions": {
                        "type": "object",
                        "description": "State conditions to match"
                    },
                    "device_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional device types to filter"
                    }
                },
                "required": ["state_conditions"]
            },
            "function": self._tool_get_devices_by_state
        }
        
        # Direct lookup tools
        self._tools["get_device_by_id"] = {
            "description": "Get a specific device by ID",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "integer",
                        "description": "The device ID"
                    }
                },
                "required": ["device_id"]
            },
            "function": self._tool_get_device_by_id
        }
        
        self._tools["get_variable_by_id"] = {
            "description": "Get a specific variable by ID",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "variable_id": {
                        "type": "integer",
                        "description": "The variable ID"
                    }
                },
                "required": ["variable_id"]
            },
            "function": self._tool_get_variable_by_id
        }
        
        self._tools["get_action_group_by_id"] = {
            "description": "Get a specific action group by ID",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "action_group_id": {
                        "type": "integer",
                        "description": "The action group ID"
                    }
                },
                "required": ["action_group_id"]
            },
            "function": self._tool_get_action_group_by_id
        }
    
    def _register_resources(self):
        """Register all available resources."""
        # Device resources
        self._resources["indigo://devices"] = {
            "name": "Devices",
            "description": "List all Indigo devices",
            "function": self._resource_list_devices
        }
        
        self._resources["indigo://devices/{device_id}"] = {
            "name": "Device",
            "description": "Get a specific device",
            "function": self._resource_get_device
        }
        
        # Variable resources
        self._resources["indigo://variables"] = {
            "name": "Variables",
            "description": "List all Indigo variables",
            "function": self._resource_list_variables
        }
        
        self._resources["indigo://variables/{variable_id}"] = {
            "name": "Variable",
            "description": "Get a specific variable",
            "function": self._resource_get_variable
        }
        
        # Action resources
        self._resources["indigo://actions"] = {
            "name": "Action Groups",
            "description": "List all action groups",
            "function": self._resource_list_actions
        }
        
        self._resources["indigo://actions/{action_id}"] = {
            "name": "Action Group",
            "description": "Get a specific action group",
            "function": self._resource_get_action
        }
    
    # Tool implementation methods
    def _tool_search_entities(
        self, 
        query: str,
        device_types: List[str] = None,
        entity_types: List[str] = None,
        state_filter: Dict = None
    ) -> str:
        """Search entities tool implementation."""
        try:
            # Validate device types
            if device_types:
                invalid_device_types = [
                    dt for dt in device_types
                    if not IndigoDeviceType.is_valid_type(dt)
                ]
                if invalid_device_types:
                    return safe_json_dumps({
                        "error": f"Invalid device types: {invalid_device_types}",
                        "query": query
                    })
            
            # Validate entity types
            if entity_types:
                invalid_entity_types = [
                    et for et in entity_types
                    if not IndigoEntityType.is_valid_type(et)
                ]
                if invalid_entity_types:
                    return safe_json_dumps({
                        "error": f"Invalid entity types: {invalid_entity_types}",
                        "query": query
                    })
            
            self.logger.info(
                f"[search_entities]: query: '{query}', "
                f"device_types: {device_types}, "
                f"entity_types: {entity_types}, "
                f"state_filter: {state_filter}"
            )
            
            results = self.search_handler.search(
                query, device_types, entity_types, state_filter
            )
            return safe_json_dumps(results)
            
        except Exception as e:
            self.logger.error(f"[search_entities]: Error - {e}")
            return safe_json_dumps({"error": str(e), "query": query})
    
    def _tool_get_devices_by_type(self, device_type: str) -> str:
        """Get devices by type tool implementation."""
        try:
            result = self.get_devices_by_type_handler.get_devices(device_type)
            return safe_json_dumps(result)
        except Exception as e:
            self.logger.error(f"Get devices by type error: {e}")
            return safe_json_dumps({"error": str(e), "device_type": device_type})
    
    def _tool_device_turn_on(self, device_id: int) -> str:
        """Turn on device tool implementation."""
        try:
            result = self.device_control_handler.turn_on(device_id)
            return safe_json_dumps(result)
        except Exception as e:
            self.logger.error(f"Device turn on error: {e}")
            return safe_json_dumps({"error": str(e)})
    
    def _tool_device_turn_off(self, device_id: int) -> str:
        """Turn off device tool implementation."""
        try:
            result = self.device_control_handler.turn_off(device_id)
            return safe_json_dumps(result)
        except Exception as e:
            self.logger.error(f"Device turn off error: {e}")
            return safe_json_dumps({"error": str(e)})
    
    def _tool_device_set_brightness(self, device_id: int, brightness: float) -> str:
        """Set device brightness tool implementation."""
        try:
            result = self.device_control_handler.set_brightness(device_id, brightness)
            return safe_json_dumps(result)
        except Exception as e:
            self.logger.error(f"Device set brightness error: {e}")
            return safe_json_dumps({"error": str(e)})
    
    def _tool_variable_update(self, variable_id: int, value: str) -> str:
        """Update variable tool implementation."""
        try:
            result = self.variable_control_handler.update(variable_id, value)
            return safe_json_dumps(result)
        except Exception as e:
            self.logger.error(f"Variable update error: {e}")
            return safe_json_dumps({"error": str(e)})
    
    def _tool_action_execute_group(
        self, 
        action_group_id: int, 
        delay: int = None
    ) -> str:
        """Execute action group tool implementation."""
        try:
            result = self.action_control_handler.execute(action_group_id, delay)
            return safe_json_dumps(result)
        except Exception as e:
            self.logger.error(f"Action execute error: {e}")
            return safe_json_dumps({"error": str(e)})
    
    def _tool_analyze_historical_data(
        self, 
        query: str, 
        device_names: List[str], 
        time_range_days: int = 30
    ) -> str:
        """Analyze historical data tool implementation."""
        try:
            result = self.historical_analysis_handler.analyze(
                query, device_names, time_range_days
            )
            return safe_json_dumps(result)
        except Exception as e:
            self.logger.error(f"Historical analysis error: {e}")
            return safe_json_dumps({"error": str(e)})
    
    def _tool_list_devices(self, state_filter: Dict = None) -> str:
        """List devices tool implementation."""
        try:
            devices = self.list_handlers.list_all_devices(state_filter)
            return safe_json_dumps(devices)
        except Exception as e:
            self.logger.error(f"List devices error: {e}")
            return safe_json_dumps({"error": str(e)})
    
    def _tool_list_variables(self) -> str:
        """List variables tool implementation."""
        try:
            variables = self.list_handlers.list_all_variables()
            return safe_json_dumps(variables)
        except Exception as e:
            self.logger.error(f"List variables error: {e}")
            return safe_json_dumps({"error": str(e)})
    
    def _tool_list_action_groups(self) -> str:
        """List action groups tool implementation."""
        try:
            actions = self.list_handlers.list_all_action_groups()
            return safe_json_dumps(actions)
        except Exception as e:
            self.logger.error(f"List action groups error: {e}")
            return safe_json_dumps({"error": str(e)})
    
    def _tool_get_devices_by_state(
        self, 
        state_conditions: Dict, 
        device_types: List[str] = None
    ) -> str:
        """Get devices by state tool implementation."""
        try:
            # Validate device types if provided
            if device_types:
                invalid_types = [
                    dt for dt in device_types
                    if not IndigoDeviceType.is_valid_type(dt)
                ]
                if invalid_types:
                    return safe_json_dumps({
                        "error": f"Invalid device types: {invalid_types}"
                    })
            
            devices = self.list_handlers.get_devices_by_state(
                state_conditions, device_types
            )
            return safe_json_dumps(devices)
        except Exception as e:
            self.logger.error(f"Get devices by state error: {e}")
            return safe_json_dumps({"error": str(e)})
    
    def _tool_get_device_by_id(self, device_id: int) -> str:
        """Get device by ID tool implementation."""
        try:
            device = self.data_provider.get_device(device_id)
            if device is None:
                return safe_json_dumps({
                    "error": f"Device {device_id} not found"
                })
            return safe_json_dumps(device)
        except Exception as e:
            self.logger.error(f"Get device by ID error: {e}")
            return safe_json_dumps({"error": str(e)})
    
    def _tool_get_variable_by_id(self, variable_id: int) -> str:
        """Get variable by ID tool implementation."""
        try:
            variable = self.data_provider.get_variable(variable_id)
            if variable is None:
                return safe_json_dumps({
                    "error": f"Variable {variable_id} not found"
                })
            return safe_json_dumps(variable)
        except Exception as e:
            self.logger.error(f"Get variable by ID error: {e}")
            return safe_json_dumps({"error": str(e)})
    
    def _tool_get_action_group_by_id(self, action_group_id: int) -> str:
        """Get action group by ID tool implementation."""
        try:
            action = self.data_provider.get_action_group(action_group_id)
            if action is None:
                return safe_json_dumps({
                    "error": f"Action group {action_group_id} not found"
                })
            return safe_json_dumps(action)
        except Exception as e:
            self.logger.error(f"Get action group by ID error: {e}")
            return safe_json_dumps({"error": str(e)})
    
    # Resource implementation methods
    def _resource_list_devices(self) -> str:
        """List all devices resource."""
        try:
            devices = self.list_handlers.list_all_devices()
            return safe_json_dumps(devices)
        except Exception as e:
            self.logger.error(f"Resource list devices error: {e}")
            return safe_json_dumps({"error": str(e)})
    
    def _resource_get_device(self, device_id: str) -> str:
        """Get specific device resource."""
        try:
            device = self.data_provider.get_device(int(device_id))
            if device is None:
                return safe_json_dumps({
                    "error": f"Device {device_id} not found"
                })
            return safe_json_dumps(device)
        except Exception as e:
            self.logger.error(f"Resource get device error: {e}")
            return safe_json_dumps({"error": str(e)})
    
    def _resource_list_variables(self) -> str:
        """List all variables resource."""
        try:
            variables = self.list_handlers.list_all_variables()
            return safe_json_dumps(variables)
        except Exception as e:
            self.logger.error(f"Resource list variables error: {e}")
            return safe_json_dumps({"error": str(e)})
    
    def _resource_get_variable(self, variable_id: str) -> str:
        """Get specific variable resource."""
        try:
            variable = self.data_provider.get_variable(int(variable_id))
            if variable is None:
                return safe_json_dumps({
                    "error": f"Variable {variable_id} not found"
                })
            return safe_json_dumps(variable)
        except Exception as e:
            self.logger.error(f"Resource get variable error: {e}")
            return safe_json_dumps({"error": str(e)})
    
    def _resource_list_actions(self) -> str:
        """List all action groups resource."""
        try:
            actions = self.list_handlers.list_all_action_groups()
            return safe_json_dumps(actions)
        except Exception as e:
            self.logger.error(f"Resource list actions error: {e}")
            return safe_json_dumps({"error": str(e)})
    
    def _resource_get_action(self, action_id: str) -> str:
        """Get specific action group resource."""
        try:
            action = self.data_provider.get_action_group(int(action_id))
            if action is None:
                return safe_json_dumps({
                    "error": f"Action group {action_id} not found"
                })
            return safe_json_dumps(action)
        except Exception as e:
            self.logger.error(f"Resource get action error: {e}")
            return safe_json_dumps({"error": str(e)})
    
    # Helper methods
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