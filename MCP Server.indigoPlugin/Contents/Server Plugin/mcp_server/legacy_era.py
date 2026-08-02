"""
Legacy MCP era: the session-based protocol revisions (2025-11-25, 2025-06-18).

The 2026-07-28 revision made MCP stateless; everything in this module exists
only to serve older clients that still open with an `initialize` handshake and
per-session `Mcp-Session-Id` headers. When legacy support is retired, delete
this module, remove the LegacyEra wiring from MCPHandler, and drop the legacy
entries from server/discover's supportedVersions. The spec asks that a
modern-only server answer `initialize` with an error naming its supported
versions — that small stub replaces MCPHandler's legacy dispatch when this
module goes away.
"""

import json
import logging
import secrets
import time
from typing import Any, Dict, Optional


def _json_error(msg_id: Any, code: int, message: str, data: Any = None) -> Dict[str, Any]:
    """Create a JSON-RPC error response (local copy; dies with this module)."""
    error: Dict[str, Any] = {
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


class LegacyEra:
    """Session store and initialize-handshake handling for legacy MCP clients."""

    PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18")

    # Session expiry: clients that never send DELETE would otherwise leak sessions
    SESSION_TTL_SECONDS = 2 * 60 * 60   # purge sessions idle longer than 2 hours
    SESSION_SWEEP_INTERVAL = 300        # scan for idle sessions at most every 5 minutes

    def __init__(self, logger: logging.Logger, server_name: str, server_version: str):
        self.logger = logger
        self.server_name = server_name
        self.server_version = server_version
        self.sessions: Dict[str, Dict[str, Any]] = {}  # session_id -> {created, last_seen, client_info}
        self.last_sweep = time.time()

    def sweep(self) -> None:
        """Purge sessions idle longer than SESSION_TTL_SECONDS (rate-limited)."""
        now = time.time()
        if now - self.last_sweep < self.SESSION_SWEEP_INTERVAL:
            return
        self.last_sweep = now

        expired = [
            sid for sid, data in list(self.sessions.items())
            if now - data.get("last_seen", 0) > self.SESSION_TTL_SECONDS
        ]
        for sid in expired:
            self.sessions.pop(sid, None)

        if expired:
            self.logger.debug(
                f"Purged {len(expired)} idle MCP session(s); {len(self.sessions)} active"
            )

    def handle_delete(self, headers: Dict[str, str]) -> Dict[str, Any]:
        """Handle HTTP DELETE: client-initiated session termination."""
        session_id = headers.get("mcp-session-id")
        if not session_id:
            return {
                "status": 400,
                "headers": {"Content-Type": "application/json; charset=utf-8"},
                "content": json.dumps({"error": "Missing Mcp-Session-Id header"})
            }

        session = self.sessions.pop(session_id, None)
        if session:
            client_name = session.get("client_info", {}).get("name", "Unknown")
            self.logger.debug(f"Session terminated by client: {client_name} | session: {session_id[:8]}")
        else:
            # Idempotent: deleting an unknown/expired session is still success
            # (404 would be spec-purist but generates an IWS warning log line).
            self.logger.debug(f"DELETE for unknown session: {session_id[:8]}")

        return {
            "status": 200,
            "headers": {"Content-Type": "application/json; charset=utf-8"},
            "content": "{}"
        }

    def validate(self, msg_id: Any, method: str, headers: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """
        Legacy request gates: protocol-version header and session validation.

        Returns a JSON-RPC error response dict if the request is invalid,
        None if it may proceed. Both gates only apply once at least one
        session exists (bootstrap allowance for pre-initialize traffic).
        """
        if method == "initialize" or method.startswith("notifications/") or not self.sessions:
            return None

        protocol_version_header = headers.get("mcp-protocol-version")
        if protocol_version_header and protocol_version_header not in self.PROTOCOL_VERSIONS:
            self.logger.debug(f"Invalid protocol version: {protocol_version_header}")
            return _json_error(msg_id, -32600, f"Unsupported protocol version: {protocol_version_header}")

        session_id = headers.get("mcp-session-id")
        if not session_id or session_id not in self.sessions:
            self.logger.debug(f"Invalid session ID for {method}")
            return _json_error(msg_id, -32600, "Missing or invalid Mcp-Session-Id")
        self.sessions[session_id]["last_seen"] = time.time()
        return None

    def client_label(self, headers: Dict[str, str], client_ip: str) -> str:
        """Format a client label for logging, using session client info when known."""
        session_id = headers.get("mcp-session-id", "")
        if session_id and session_id in self.sessions:
            client_name = self.sessions[session_id].get("client_info", {}).get("name", "")
            if client_name:
                return f"{client_name}@{client_ip}"
        return client_ip

    def handle_initialize(
        self,
        msg_id: Any,
        params: Dict[str, Any],
        client_ip: str = "unknown"
    ) -> Dict[str, Any]:
        """Handle a legacy initialize request (session minting + version negotiation)."""
        requested_version = str(params.get("protocolVersion") or "")
        client_info = params.get("clientInfo", {})
        client_name = client_info.get("name", "Unknown")

        if requested_version not in self.PROTOCOL_VERSIONS:
            self.logger.debug(f"Unsupported protocol version: {requested_version}")
            return _json_error(
                msg_id, -32602, "Unsupported protocol version",
                data={
                    "supported": list(self.PROTOCOL_VERSIONS),
                    "requested": requested_version
                }
            )

        session_id = secrets.token_urlsafe(24)
        self.sessions[session_id] = {
            "created": time.time(),
            "last_seen": time.time(),
            "client_info": client_info,
            "client_ip": client_ip,
            "protocol_version": requested_version  # Track negotiated version per session
        }

        self.logger.debug(f"New session: {client_name}@{client_ip} | session: {session_id[:8]} | protocol: {requested_version}")
        self.logger.debug(
            f"Client {client_name} connected via legacy MCP revision {requested_version} — "
            "legacy (session-based) support will be removed in a future release"
        )

        result = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": requested_version,  # Echo back client's requested version
                # Honest advertisement: no logging/setLevel handler exists, and
                # this transport is POST-only (no push channel), so no listChanged
                # or subscribe capabilities are claimed.
                "capabilities": {
                    "prompts": {},
                    "resources": {},
                    "tools": {}
                },
                "serverInfo": {
                    "name": self.server_name,
                    "version": self.server_version
                }
            }
        }

        # Session ID is promoted to the Mcp-Session-Id HTTP header by handle_request
        result["_mcp_session_id"] = session_id
        return result
