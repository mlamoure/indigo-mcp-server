"""
MCP Handler for Indigo IWS integration.
Implements standards-compliant MCP protocol over Indigo's built-in web server.
"""

import json
import logging
import os
import time
from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .events.subscription_handler import SubscriptionHandler

from .adapters.data_provider import DataProvider
from .adapters.indidb import IndiDbStructureStore
from .common.json_encoder import safe_json_dumps
from .common.vector_store.vector_store_manager import VectorStoreManager
from .external_tools.external_tool_handler import ExternalToolHandler
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
from .tool_registry import get_tool_schemas, removed_tool_hint
from .tool_wrappers import ToolWrappers
from .tools.automation import AutomationHandler
from .tools.log_search import LogSearchHandler
from .tools.search_entities import SearchEntitiesHandler
from .tools.tags import TagHandler


class MCPHandler:
    """Handles MCP protocol requests through Indigo IWS."""

    SERVER_NAME = "MCP Advanced Tools"

    # Natural-language guidance for clients (legacy initialize and modern
    # server/discover both carry an optional `instructions` field).
    SERVER_INSTRUCTIONS = (
        "MCP Advanced Tools: companion to Indigo's built-in MCP Control server (Indigo 2026.1+, "
        "Web Server path /v3/api/mcp). Use MCP Control to control devices, set "
        "variables, run action groups, triggers and schedules, and list or look up "
        "objects. Use this server for what MCP Control does not do: semantic "
        "search across every entity, including ones not published for remote "
        "display (search_entities); automation internals such as action "
        "steps, condition trees and reverse references (get_*_details, "
        "find_automation_references); event investigation and full event-log "
        "history (investigate_event, query_event_log); automation lifecycle "
        "and edits (control_*, update_*); creating, editing and assigning "
        "Indigo tags (manage_tags, tag_objects; MCP Control's list_tags reads "
        "them); event webhooks when enabled; and tools provided by other "
        "Indigo plugins. An element carrying the house's confirmation tag "
        "(default ask-first) answers requires_confirmation: confirm only when "
        "the user asked for that specific change."
    )

    # Legacy (session-based) protocol versions, newest first. Aliased here for
    # existing callers and tests; the authoritative tuple lives in LegacyEra.
    SUPPORTED_PROTOCOL_VERSIONS = LegacyEra.PROTOCOL_VERSIONS
    LATEST_PROTOCOL_VERSION = SUPPORTED_PROTOCOL_VERSIONS[0]

    # Every protocol revision this server speaks (modern first), as advertised
    # by server/discover.
    ALL_PROTOCOL_VERSIONS = MODERN_PROTOCOL_VERSIONS + LegacyEra.PROTOCOL_VERSIONS

    # Minimum seconds between tools/list-triggered checks for newly installed
    # plugins (see _maybe_scan_for_new_providers)
    PROVIDER_SCAN_INTERVAL = 60.0

    def __init__(
        self,
        data_provider: DataProvider,
        logger: Optional[logging.Logger] = None,
        subscription_handler: "Optional[SubscriptionHandler]" = None,
        server_version: str = "unknown",
        automation_delete_supplier=None,
        tag_delete_supplier=None,
        confirm_tag_supplier=None,
        external_tool_manager=None,
        provider_scan_supplier: Optional[Callable[[], bool]] = None,
        clock: Callable[[], float] = time.monotonic,
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
            tag_delete_supplier: Callable returning whether the "allow AI to
                delete tags" preference is on (checked per call)
            confirm_tag_supplier: Callable returning the confirmation tag name
                ('' for none); elements carrying it need confirm=true
            external_tool_manager: Optional ExternalToolManager serving
                plugin-provided tools; without one, behavior is identical to
                a build without the feature
            provider_scan_supplier: Optional callable run from tools/list (at
                most once per PROVIDER_SCAN_INTERVAL) that subscribes to any
                newly installed plugin and returns True when it found one, so
                a provider installed after startup appears without a restart
            clock: Monotonic time source (injectable for tests)
        """
        self.data_provider = data_provider
        self.logger = logger or logging.getLogger("Plugin")
        self.subscription_handler = subscription_handler
        self.server_version = server_version
        self.automation_delete_supplier = automation_delete_supplier or (lambda: False)
        self.tag_delete_supplier = tag_delete_supplier or (lambda: False)
        self.confirm_tag_supplier = confirm_tag_supplier or (lambda: "")
        self.external_tool_manager = external_tool_manager
        self.provider_scan_supplier = provider_scan_supplier
        self._clock = clock
        self._last_provider_scan: Optional[float] = None
        # Last registered plugin-provided tool set, for change-only logging
        self._external_signature = None

        # Legacy (session-based) era support — delete when legacy is retired
        self.legacy = LegacyEra(
            logger=self.logger,
            server_name=self.SERVER_NAME,
            server_version=server_version,
            instructions=self.SERVER_INSTRUCTIONS,
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

        # Register tools. No MCP resources are published: Indigo's built-in
        # MCP Control serves the indigo:// object resources.
        self._tools = {}
        self._register_tools()
        self.refresh_external_tools()

        self.logger.info(f"✅ MCP Advanced Tools ready — {len(self._tools)} tools available to AI clients")
        self.logger.debug("Endpoint: /message/com.vtmikel.mcp_server/mcp/")
        
    def _init_handlers(self):
        """Initialize all handler instances."""
        # Search handler with vector store
        self.search_handler = SearchEntitiesHandler(
            data_provider=self.data_provider,
            vector_store=self.vector_store_manager.get_vector_store(),
            logger=self.logger,
        )

        # Device control, variable writes, plain listings/lookups and plugin
        # management are served by Indigo's built-in MCP Control (2026.1+),
        # so this server has no handlers for them. InfluxDB history is a
        # plugin-provided tool of the Grafana Home Dashboard plugin.

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
            confirm_tag_supplier=self.confirm_tag_supplier,
        )
        self.tag_handler = TagHandler(
            data_provider=self.data_provider,
            logger=self.logger,
            delete_enabled_supplier=self.tag_delete_supplier,
            confirm_tag_supplier=self.confirm_tag_supplier,
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
            automation_handler=self.automation_handler,
            log_search_handler=self.log_search_handler,
            subscription_handler=self.subscription_handler,
            logger=self.logger,
            tag_handler=self.tag_handler,
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
        elif method == "resources/templates/list":
            return self._handle_resource_templates_list(msg_id)
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
        # A client asking for the tool list wants a fresh set: pick up a
        # provider installed since startup (throttled)
        self._maybe_scan_for_new_providers()

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
            blocked_by = self._blocked_tool_provider(tool_name)
            if blocked_by:
                # tools/list carries a 1-hour cache hint, so a client can call
                # a tool the plugin config blocked a minute ago
                return self._json_error(
                    msg_id,
                    -32602,
                    f"Tool '{tool_name}' is provided by {blocked_by}, which is "
                    f"blocked in the MCP Advanced Tools plugin config (\"Plugins that "
                    f"may provide MCP tools\")."
                )
            moved_hint = removed_tool_hint(tool_name)
            if moved_hint:
                # tools/list carries a 1-hour cache hint, and gateways keep
                # their own catalogs, so pre-2026.11 tool names still arrive
                return self._json_error(msg_id, -32602, f"Unknown tool: {tool_name}. {moved_hint}")
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
        """
        Handle resources/list: this server publishes no resources.

        The resources capability is not advertised (Indigo's built-in MCP
        Control serves the indigo:// object resources, and duplicates here
        collided with its URIs in gateways that federate both servers). The
        method still answers, with an empty list, for clients that call it
        regardless of capabilities.
        """
        return self._result(msg_id, {"resources": []}, ttl_ms=3600000)

    def _handle_resource_templates_list(self, msg_id: Any) -> Dict[str, Any]:
        """Handle resources/templates/list (no resources; see _handle_resources_list)."""
        return self._result(msg_id, {"resourceTemplates": []}, ttl_ms=3600000)

    def _handle_resources_read(
        self,
        msg_id: Any,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle resources/read: every URI is unknown (no resources are published)."""
        uri = params.get("uri")

        if not uri:
            return self._json_error(msg_id, -32602, "Missing uri parameter")

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
            # No resources capability: none are published (see
            # _handle_resources_list).
            "capabilities": {
                "prompts": {},
                "tools": {}
            },
            "instructions": self.SERVER_INSTRUCTIONS
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
        elif method == "resources/templates/list":
            resp = self._handle_resource_templates_list(msg_id)
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
            "manage_tags": self.tool_wrappers.tool_manage_tags,
            "tag_objects": self.tool_wrappers.tool_tag_objects,
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

    def _blocked_tool_provider(self, tool_name: Any) -> Optional[str]:
        """Display name of the blocked provider that would serve tool_name, if any."""
        if not self.external_tool_manager or not isinstance(tool_name, str):
            return None
        return getattr(self.external_tool_manager, "blocked_tool_names", {}).get(tool_name)

    def _maybe_scan_for_new_providers(self) -> None:
        """
        From tools/list: at most once per PROVIDER_SCAN_INTERVAL, ask the
        plugin whether a plugin was installed since it last subscribed, and
        rescan when one was. Runs on the plugin's single callback thread, like
        broadcasts and prefs callbacks, so the in-place swap needs no lock.
        """
        if not self.provider_scan_supplier or not self.external_tool_manager:
            return
        now = self._clock()
        if (
            self._last_provider_scan is not None
            and now - self._last_provider_scan < self.PROVIDER_SCAN_INTERVAL
        ):
            return
        self._last_provider_scan = now
        try:
            found_new = self.provider_scan_supplier()
        except Exception as e:
            self.logger.debug(f"Installed-plugin check failed: {e}")
            return
        if found_new:
            self.refresh_external_tools()

    def refresh_external_tools(self, announce: Optional[bool] = None) -> bool:
        """
        Re-discover plugin-provided tools and swap the merged registry in.

        Safe to call at any time: the merged dict is built fully and then
        assigned in one reference swap, which per-request readers
        (_handle_tools_list/_handle_tools_call) pick up on their next access.
        With no manager configured this is a no-op and the registry stays
        exactly the static tool set.

        Args:
            announce: True logs the summary at INFO (explicit rescans), False
                at DEBUG (the caller logs its own line); None (startup,
                broadcasts, tools/list) logs at INFO only when the registered
                set changed, so a chatty provider or a busy client does not
                flood the event log.

        Returns:
            Whether the registered set (tools or blocked providers) changed.
        """
        if not self.external_tool_manager:
            return False

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

        external_names = sorted(n for n in merged if n not in self._static_tools)
        external_count = len(external_names)
        providers = self.external_tool_manager.manifests
        blocked = getattr(self.external_tool_manager, "blocked", [])
        signature = (
            tuple(external_names),
            tuple(sorted(m.plugin_id for m in blocked)),
        )
        first = self._external_signature is None
        changed = signature != self._external_signature
        self._external_signature = signature

        if not (external_count or providers or blocked):
            message = "No plugin-provided MCP tools registered"
            # Nothing worth an INFO line at startup; say so when tools just
            # went away or when explicitly asked
            if announce or (announce is None and changed and not first):
                self.logger.info(f"🔌 {message}")
            else:
                self.logger.debug(message)
            return changed

        provider_names = ", ".join(m.display_name for m in providers) or "none"
        message = (
            f"🔌 {external_count} plugin-provided tool"
            f"{'s' if external_count != 1 else ''} registered "
            f"(providers: {provider_names}"
        )
        if blocked:
            message += f"; blocked by config: {', '.join(m.display_name for m in blocked)}"
        message += ")"
        if announce or (announce is None and changed):
            self.logger.info(message)
        else:
            self.logger.debug(message)
        return changed

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