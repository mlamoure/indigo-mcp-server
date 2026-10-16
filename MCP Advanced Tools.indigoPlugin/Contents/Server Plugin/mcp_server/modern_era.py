"""
Modern MCP era: pure helpers for the stateless 2026-07-28 protocol revision.

The modern era carries all connection context per-request: the protocol
version and client capabilities travel in params._meta, mirrored into HTTP
headers (MCP-Protocol-Version, Mcp-Method, Mcp-Name) so intermediaries can
route without parsing bodies. There is no initialize handshake and no
session — see legacy_era.py for the older revisions.

x-mcp-header / Mcp-Param-* tool-parameter mirroring is deliberately not
adopted: no tool schema here designates parameters for header mirroring, so
the server never expects Mcp-Param-* headers and ignores unsolicited ones.
"""

import base64
import binascii
from typing import Any, Dict, Optional, Tuple

MODERN_PROTOCOL_VERSIONS = ("2026-07-28",)

# Reserved _meta keys (spec: basic/index#meta)
META_PROTOCOL_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CLIENT_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"
META_CLIENT_INFO = "io.modelcontextprotocol/clientInfo"
META_SERVER_INFO = "io.modelcontextprotocol/serverInfo"

# MCP-defined JSON-RPC error codes (spec: basic/index#error-codes)
HEADER_MISMATCH = -32020
UNSUPPORTED_PROTOCOL_VERSION = -32022

# Methods whose params value must be mirrored in the Mcp-Name header
_NAME_HEADER_FIELDS = {
    "tools/call": "name",
    "resources/read": "uri",
    "prompts/get": "name",
}

_B64_PREFIX = "=?base64?"
_B64_SUFFIX = "?="


def decode_header_value(value: str) -> str:
    """
    Decode a Base64-sentinel-encoded header value (=?base64?<data>?=).

    Plain values pass through unchanged. A malformed sentinel is returned
    as-is so the caller's equality check against the body fails, producing
    the spec-required HeaderMismatch error.
    """
    if value.startswith(_B64_PREFIX) and value.endswith(_B64_SUFFIX):
        encoded = value[len(_B64_PREFIX):-len(_B64_SUFFIX)]
        try:
            return base64.b64decode(encoded, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            return value
    return value


def get_meta(msg: Dict[str, Any]) -> Dict[str, Any]:
    """Return the request's params._meta dict ({} when absent or malformed)."""
    params = msg.get("params")
    if not isinstance(params, dict):
        return {}
    meta = params.get("_meta")
    return meta if isinstance(meta, dict) else {}


def is_modern_request(payload: Any, headers: Dict[str, str]) -> bool:
    """
    Era detection for a parsed POST body (headers already lowercased).

    A request is modern when it carries the per-request protocol version in
    _meta OR declares a modern version in the MCP-Protocol-Version header —
    either signal routes here so a half-formed modern request receives the
    spec-correct 400 rather than falling through to legacy handling.
    An `initialize` request always selects the legacy era (dual-era rule).
    """
    if not isinstance(payload, dict):
        return False
    if payload.get("method") == "initialize":
        return False
    if get_meta(payload).get(META_PROTOCOL_VERSION):
        return True
    return headers.get("mcp-protocol-version") in MODERN_PROTOCOL_VERSIONS


def validate_envelope(
    msg: Dict[str, Any],
    headers: Dict[str, str]
) -> Optional[Tuple[int, str, Any]]:
    """
    Validate the modern request envelope (body _meta fields + mirrored headers).

    Returns (code, message, data) for the JSON-RPC error to emit (HTTP 400),
    or None when the envelope is valid.
    """
    if msg.get("jsonrpc") != "2.0" or "method" not in msg:
        return (-32600, "Invalid Request", None)

    method = msg["method"]
    meta = get_meta(msg)

    version = meta.get(META_PROTOCOL_VERSION)
    if not version:
        return (-32602, f"Missing required _meta field: {META_PROTOCOL_VERSION}", None)
    if META_CLIENT_CAPABILITIES not in meta:
        return (-32602, f"Missing required _meta field: {META_CLIENT_CAPABILITIES}", None)

    header_version = headers.get("mcp-protocol-version")
    if not header_version:
        return (HEADER_MISMATCH, "Missing required MCP-Protocol-Version header", None)
    if header_version != version:
        return (
            HEADER_MISMATCH,
            f"Header mismatch: MCP-Protocol-Version header '{header_version}' "
            f"does not match _meta value '{version}'",
            None,
        )
    if version not in MODERN_PROTOCOL_VERSIONS:
        return (
            UNSUPPORTED_PROTOCOL_VERSION,
            "Unsupported protocol version",
            {"supported": list(MODERN_PROTOCOL_VERSIONS), "requested": version},
        )

    method_header = headers.get("mcp-method")
    if method_header is None:
        return (HEADER_MISMATCH, "Missing required Mcp-Method header", None)
    if decode_header_value(method_header) != method:
        return (
            HEADER_MISMATCH,
            f"Header mismatch: Mcp-Method header '{method_header}' "
            f"does not match body method '{method}'",
            None,
        )

    name_field = _NAME_HEADER_FIELDS.get(method)
    if name_field:
        params = msg.get("params") or {}
        body_value = params.get(name_field)
        name_header = headers.get("mcp-name")
        if name_header is None:
            return (HEADER_MISMATCH, "Missing required Mcp-Name header", None)
        if decode_header_value(name_header) != body_value:
            return (
                HEADER_MISMATCH,
                f"Header mismatch: Mcp-Name header does not match body '{name_field}' value",
                None,
            )

    return None


def http_status_for(resp: Dict[str, Any]) -> int:
    """
    Map a modern-era JSON-RPC response to its HTTP status.

    Results are 200; unknown method is 404 and internal errors 500 per the
    transport spec; every other error (validation, unsupported version,
    header mismatch) is 400.
    """
    if "error" not in resp:
        return 200
    code = resp["error"].get("code")
    if code == -32601:
        return 404
    if code == -32603:
        return 500
    return 400
