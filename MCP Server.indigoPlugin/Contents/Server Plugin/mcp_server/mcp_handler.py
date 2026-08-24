"""
MCP Handler for Indigo IWS integration.
Implements standards-compliant MCP protocol over Indigo's built-in web server.
"""

import json
import logging
import os
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .events.subscription_handler import SubscriptionHandler

from .adapters.data_provider import DataProvider
from .adapters.indidb import IndiDbStructureStore
from .common.json_encoder import safe_json_dumps
from .common.vector_store.vector_store_manager import VectorStoreManager
from .external_tools.external_tool_handler import ExternalToolHandler
from .handlers.list_handlers import ListHandlers
from .legacy_era import LegacyEra
# NOTE: `from .modern_era import ...` (not `from . import modern_era`) — the
# test conftest stubs the mcp_server package with a MagicMock, so the
# attribute-style module import would silently return a mock under pytest.
from .modern_era import (
    META_CLIENT_INFO,
    META_SERVER_INFO,
    MODERN_PROTOCOL_VERSIONS,
    get_meta,
    http_status_for,
    is_modern_request,
    validate_envelope,
)
from .resource_registry import get_resource_schemas
from .tool_registry import get_tool_schemas
from .tool_wrappers import ToolWrappers
from .tools.action_control import ActionControlHandler
from .tools.automation import AutomationHandler
from .tools.device_control import DeviceControlHandler
from .tools.get_devices_by_type import GetDevicesByTypeHandler
from .tools.historical_analysis import HistoricalAnalysisHandler
from .tools.log_search import LogSearchHandler
from .tools.plugin_control import PluginControlHandler
from .tools.rgb_control import RGBControlHandler
from .tools.search_entities import SearchEntitiesHandler
from .tools.thermostat_control import ThermostatControlHandler
from .tools.variable_control import VariableControlHandler


class MCPHandler:
    """Handles MCP protocol requests through Indigo IWS."""

    SERVER_NAME = "Indigo MCP Server"

    # Legacy (session-based) protocol versions, newest first. Aliased here for
    # existing callers and tests; the authoritative tuple lives in LegacyEra.
    SUPPORTED_PROTOCOL_VERSIONS = LegacyEra.PROTOCOL_VERSIONS
    LATEST_PROTOCOL_VERSION = SUPPORTED_PROTOCOL_VERSIONS[0]

    # Every protocol revision this server speaks (modern first), as advertised
    # by server/discover.
    ALL_PROTOCOL_VERSIONS = MODERN_PROTOCOL_VERSIONS + LegacyEra.PROTOCOL_VERSIONS

    def __init__(
        self,
        data_provider: DataProvider,
        logger: Optional[logging.Logger] = None,
        subscription_handler: "Optional[SubscriptionHandler]" = None,
        server_version: str = "unknown",
        automation_delete_supplier=None,
        external_tool_manager=None,
    ):
        """
        Initialize the MCP handler.

        Args:
            data_provider: Data provider for accessing entity data
            logger: Optional logger instance
            subscription_handler: Optional event subscription handler (when webhooks enabled)
            server_version: Plugin version reported in serverInfo
            automation_delete_supplier: Callable returning whether the
                "allow AI to delete automations" preference is on (checked per call)
            external_tool_manager: Optional ExternalToolManager serving
                plugin-provided tools; without one, behavior is identical to
                a build without the feature
        """
        self.data_provider = data_provider
        self.logger = logger or logging.getLogger("Plugin")
        self.subscription_handler = subscription_handler
        self.server_version = server_version
        self.automation_delete_supplier = automation_delete_supplier or (lambda: False)
        self.external_tool_manager = external_tool_manager

        # Legacy (session-based) era support — delete when legacy is retired
        self.legacy = LegacyEra(
            logger=self.logger,
            server_name=self.SERVER_NAME,
            server_version=server_version,
        )

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
        self.refresh_external_tools()

        self.logger.info(f"✅ MCP Server ready — {len(self._tools)} tools available to AI clients")
        self.logger.debug("Endpoint: /message/com.vtmikel.mcp_server/mcp/")
        
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
        self.plugin_control_handler = PluginControlHandler(
            data_provider=self.data_provider,
            logger=self.logger
        )

        # Structure store over Indigo's database file (action steps and
        # condition trees the IOM does not expose), plus the automation
        # introspection handler built on it.
        self.structure_store = IndiDbStructureStore(
            db_path_supplier=self.data_provider.get_db_file_path,
            logger=self.logger,
        )
        self.automation_handler = AutomationHandler(
            data_provider=self.data_provider,
            structure_store=self.structure_store,
            logger=self.logger,
            delete_enabled_supplier=self.automation_delete_supplier,
        )
        self.log_search_handler = LogSearchHandler(
            data_provider=self.data_provider,
            structure_store=self.structure_store,
            logger=self.logger,
        )

        # Dispatcher for plugin-provided tools (used only when an
        # ExternalToolManager was supplied)
        self.external_tool_handler = ExternalToolHandler(logger=self.logger)

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
            plugin_control_handler=self.plugin_control_handler,
            automation_handler=self.automation_handler,
            log_search_handler=self.log_search_handler,
            data_provider=self.data_provider,
            subscription_handler=self.subscription_handler,
            logger=self.logger
        )
    
    def stop(self):
        """Stop the MCP handler and cleanup resources."""
        if self.vector_store_manager:
            self.vector_store_manager.stop()

    @property
    def _sessions(self) -> Dict[str, Any]:
        """Legacy session store (compatibility alias for tests; see LegacyEra)."""
        return self.legacy.sessions

    @property
    def _last_session_sweep(self) -> float:
        return self.legacy.last_sweep

    @_last_session_sweep.setter
    def _last_session_sweep(self, value: float) -> None:
        self.legacy.last_sweep = value

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

        # Opportunistically purge idle legacy sessions (rate-limited)
        self.legacy.sweep()

        # DELETE: explicit session termination (legacy MCP streamable HTTP)
        if method == "DELETE":
            return self.legacy.handle_delete(headers)

        # GET would open a server->client SSE stream, which we don't offer;
        # the MCP spec requires 405 in that case. The body must be non-empty:
        # IWS turns an empty-content plugin response into a 500 "incorrect
        # value returned from plugin" error.
        if method != "POST":
            return {
                "status": 405,
                "headers": {"Allow": "POST, DELETE", "Content-Type": "text/plain; charset=utf-8"},
                "content": "Method Not Allowed"
            }

        # Check Accept header - client must accept json, event-stream, or */* (wildcard)
        if "application/json" not in accept and "text/event-stream" not in accept and "*/*" not in accept:
            self.logger.debug(f"Invalid Accept header: '{accept}'")
            return {
                "status": 406,
                "headers": {"Content-Type": "text/plain"},
                "content": "Not Acceptable"
            }

        # Malformed bodies can't be era-detected from content; use the declared
        # protocol-version header to pick the status convention (modern clients
        # expect real 4xx statuses, legacy responses are always HTTP 200).
        malformed_status = (
            400 if headers.get("mcp-protocol-version") in MODERN_PROTOCOL_VERSIONS
            else 200
        )

        # Parse JSON body
        try:
            payload = json.loads(body) if body else None
        except Exception as e:
            self.logger.debug(f"Failed to parse JSON body: {e}")
            return self._json_response(
                self._json_error(None, -32700, "Parse error"),
                status=malformed_status
            )

        # Handle empty or invalid payload
        if not payload:
            return self._json_response(
                self._json_error(None, -32600, "Invalid Request"),
                status=malformed_status
            )

        # MCP 2025-06-18 spec removes support for JSON-RPC batching
        if isinstance(payload, list):
            self.logger.debug("Batch requests not supported")
            return self._json_response(
                self._json_error(None, -32600, "Batch requests not supported"),
                status=malformed_status
            )

        # Modern era (2026-07-28): stateless, per-request metadata. Origin-header
        # validation is deliberately not enforced in either era: IWS authenticates
        # every request (Bearer) before this callback runs, which defeats DNS
        # rebinding, and the plugin cannot know its legitimate reflector hostnames.
        if is_modern_request(payload, headers):
            try:
                return self._handle_modern_post(payload, headers)
            except Exception:
                self.logger.exception("Unhandled MCP error (modern era)")
                return self._json_response(
                    self._json_error(payload.get("id"), -32603, "Internal error"),
                    status=500
                )

        # --- Legacy era (sessions + initialize handshake); delete when retired ---
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
                
        except Exception:
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
            self.logger.debug("Invalid JSON-RPC message structure")
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

        session_id = headers.get("mcp-session-id", "")
        session_short = session_id[:8] if session_id else "none"
        client_label = self.legacy.client_label(headers, client_ip)

        # Format method for logging
        if method.startswith("notifications/"):
            log_method = method.replace("notifications/", "notify:")
        elif "/" in method:
            log_method = method.replace("/", ":")
        else:
            log_method = method

        # Transport-level detail; user-facing activity is logged by the
        # tool handlers (which know entity names and outcomes).
        self.logger.debug(f"{log_method} | {client_label} | session: {session_short}")
        
        # Legacy gates: protocol-version header + session validation
        validation_error = self.legacy.validate(msg_id, method, headers)
        if validation_error:
            return validation_error

        # Route to appropriate handler. initialize and ping exist only in the
        # legacy era (both were removed in the 2026-07-28 revision).
        if method == "initialize":
            return self.legacy.handle_initialize(msg_id, params, client_ip)
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
            return self._handle_prompts_list(msg_id)
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
        # Convert tool functions to tool descriptions. Registry insertion order
        # is fixed, giving the deterministic ordering the spec asks for.
        tools = []
        for name, info in self._tools.items():
            tools.append({
                "name": name,
                "description": info["description"],
                "inputSchema": info["inputSchema"]
            })

        return self._result(msg_id, {"tools": tools}, ttl_ms=3600000)
    
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

            return self._result(msg_id, {
                "content": [
                    {
                        "type": "text",
                        "text": result
                    }
                ]
            })
        except (TypeError, ValueError) as e:
            # Input validation errors return as Tool Execution Errors
            # This enables model self-correction by returning error as tool result
            self.logger.debug(f"Tool {tool_name} validation error: {e}")
            return self._result(msg_id, {
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
            })
        except Exception as e:
            # Internal errors still return as JSON-RPC errors
            self.logger.error(f"❌ Tool '{tool_name}' failed unexpectedly: {e}")
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

        return self._result(msg_id, {"resources": resources}, ttl_ms=3600000)
    
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
                return self._result(msg_id, {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": "application/json",
                            "text": content
                        }
                    ]
                }, ttl_ms=0)
            except Exception as e:
                self.logger.error(f"❌ Read resource {uri} failed: {e}")
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
                            return self._result(msg_id, {
                                "contents": [
                                    {
                                        "uri": uri,
                                        "mimeType": "application/json",
                                        "text": content
                                    }
                                ]
                            }, ttl_ms=0)
                        except Exception as e:
                            self.logger.error(f"❌ Read resource {uri} failed: {e}")
                            return self._json_error(
                                msg_id, 
                                -32603, 
                                f"Resource read failed: {str(e)}"
                            )
        
        # -32602 per the 2026-07-28 revision (which forbids the old -32002 code);
        # legacy clients treat the code opaquely here, so both eras share it.
        return self._json_error(msg_id, -32602, f"Resource not found: {uri}")

    def _handle_prompts_list(self, msg_id: Any) -> Dict[str, Any]:
        """Handle prompts/list request (no prompts are defined)."""
        return self._result(msg_id, {"prompts": []}, ttl_ms=3600000)

    def _handle_server_discover(self, msg_id: Any) -> Dict[str, Any]:
        """Handle server/discover (modern era): versions, capabilities, identity."""
        return self._result(msg_id, {
            "supportedVersions": list(self.ALL_PROTOCOL_VERSIONS),
            # No push channel exists (IWS responses are one-shot), so no
            # listChanged/subscribe capabilities and no subscriptions/listen.
            "capabilities": {
                "prompts": {},
                "resources": {},
                "tools": {}
            }
        }, ttl_ms=3600000)

    def _handle_modern_post(
        self,
        msg: Dict[str, Any],
        headers: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Serve a modern-era (2026-07-28) request: stateless, per-request metadata.

        Returns the full IWS response dict. Never reads or mints session IDs —
        an Mcp-Session-Id header from a confused client is simply ignored.
        """
        # The modern revision defines no client->server notifications on
        # Streamable HTTP; accept any stray ones leniently. (The spec's
        # 202-with-no-body is unavailable: IWS 500s on empty response bodies.)
        if "id" not in msg:
            return {
                "status": 200,
                "headers": {"Content-Type": "application/json; charset=utf-8"},
                "content": "{}"
            }

        msg_id = msg.get("id")
        envelope_error = validate_envelope(msg, headers)
        if envelope_error:
            code, message, data = envelope_error
            self.logger.debug(f"Modern envelope rejected: {message}")
            return self._json_response(
                self._json_error(msg_id, code, message, data),
                status=400
            )

        method = msg["method"]
        params = msg.get("params") or {}
        client_info = get_meta(msg).get(META_CLIENT_INFO)
        client_name = client_info.get("name") if isinstance(client_info, dict) else None
        self.logger.debug(f"{method.replace('/', ':')} | {client_name or 'unknown'} | era: modern")

        if method == "server/discover":
            resp = self._handle_server_discover(msg_id)
        elif method == "tools/list":
            resp = self._handle_tools_list(msg_id, params)
        elif method == "tools/call":
            resp = self._handle_tools_call(msg_id, params)
        elif method == "resources/list":
            resp = self._handle_resources_list(msg_id, params)
        elif method == "resources/read":
            resp = self._handle_resources_read(msg_id, params)
        elif method == "prompts/list":
            resp = self._handle_prompts_list(msg_id)
        elif method == "prompts/get":
            resp = self._json_error(msg_id, -32602, "Unknown prompt")
        else:
            # No ping, logging/setLevel or initialize here: all three were
            # removed from the protocol in the 2026-07-28 revision.
            resp = self._json_error(msg_id, -32601, "Method not found")

        return {
            "status": http_status_for(resp),
            "headers": {"Content-Type": "application/json; charset=utf-8"},
            "content": json.dumps(resp)
        }

    def _result(
        self,
        msg_id: Any,
        result: Dict[str, Any],
        *,
        ttl_ms: Optional[int] = None,
        cache_scope: str = "private"
    ) -> Dict[str, Any]:
        """
        Build a JSON-RPC result response in the modern (2026-07-28) shape.

        Both eras serve these identical bodies: resultType, the serverInfo _meta
        and cache hints are extra result fields legacy clients must tolerate,
        which keeps the business handlers era-free. ttl_ms is set only on the
        methods the spec designates cacheable; cacheScope defaults to "private"
        because every response is Bearer-authenticated, user-specific home data.
        """
        result["resultType"] = "complete"
        result.setdefault("_meta", {})[META_SERVER_INFO] = {
            "name": self.SERVER_NAME,
            "version": self.server_version
        }
        if ttl_ms is not None:
            result["ttlMs"] = ttl_ms
            result["cacheScope"] = cache_scope
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

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
            "list_triggers": self.tool_wrappers.tool_list_triggers,
            "list_schedules": self.tool_wrappers.tool_list_schedules,
            "get_trigger_details": self.tool_wrappers.tool_get_trigger_details,
            "get_schedule_details": self.tool_wrappers.tool_get_schedule_details,
            "get_action_group_details": self.tool_wrappers.tool_get_action_group_details,
            "find_automation_references": self.tool_wrappers.tool_find_automation_references,
            "investigate_event": self.tool_wrappers.tool_investigate_event,
            "control_trigger": self.tool_wrappers.tool_control_trigger,
            "control_schedule": self.tool_wrappers.tool_control_schedule,
            "control_action_group": self.tool_wrappers.tool_control_action_group,
            "update_trigger": self.tool_wrappers.tool_update_trigger,
            "update_schedule": self.tool_wrappers.tool_update_schedule,
            "update_action_group": self.tool_wrappers.tool_update_action_group,
            "list_plugins": self.tool_wrappers.tool_list_plugins,
            "get_plugin_by_id": self.tool_wrappers.tool_get_plugin_by_id,
            "restart_plugin": self.tool_wrappers.tool_restart_plugin,
            "get_plugin_status": self.tool_wrappers.tool_get_plugin_status,
        }

        # Event subscription tools (only when webhooks are enabled)
        if self.subscription_handler:
            tool_functions["create_event_subscription"] = self.tool_wrappers.tool_create_event_subscription
            tool_functions["list_event_subscriptions"] = self.tool_wrappers.tool_list_event_subscriptions
            tool_functions["delete_event_subscription"] = self.tool_wrappers.tool_delete_event_subscription

        # Get tool schemas from registry. The static registry is kept
        # separately so refresh_external_tools() can rebuild the merged view
        # from a stable base at any time.
        self._static_tools = get_tool_schemas(tool_functions)
        self._tools = self._static_tools

    def refresh_external_tools(self):
        """
        Re-discover plugin-provided tools and swap the merged registry in.

        Safe to call at any time: the merged dict is built fully and then
        assigned in one reference swap, which per-request readers
        (_handle_tools_list/_handle_tools_call) pick up on their next access.
        With no manager configured this is a no-op and the registry stays
        exactly the static tool set.
        """
        if not self.external_tool_manager:
            return

        entries = self.external_tool_manager.rescan_and_build(self.external_tool_handler)
        merged = dict(self._static_tools)
        for name, entry in entries.items():
            if name in merged:
                self.logger.error(
                    f"❌ Plugin-provided tool '{name}' (from "
                    f"{entry.get('external_provider')}) collides with a built-in "
                    f"tool — skipped"
                )
                continue
            merged[name] = entry
        self._tools = merged

        external_count = len(merged) - len(self._static_tools)
        providers = self.external_tool_manager.manifests
        if external_count or providers:
            provider_names = ", ".join(m.display_name for m in providers) or "none"
            self.logger.info(
                f"🔌 {external_count} plugin-provided tool"
                f"{'s' if external_count != 1 else ''} registered "
                f"(providers: {provider_names})"
            )
        else:
            self.logger.debug("No plugin-provided MCP tool manifests found")

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
            "list_triggers": self.tool_wrappers.resource_list_triggers,
            "get_trigger": self.tool_wrappers.resource_get_trigger,
            "list_schedules": self.tool_wrappers.resource_list_schedules,
            "get_schedule": self.tool_wrappers.resource_get_schedule,
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