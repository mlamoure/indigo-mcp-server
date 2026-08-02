"""
Tests for the modern (2026-07-28, stateless) MCP protocol era.

Covers server/discover, envelope validation (per-request _meta + mirrored
headers), cacheable-result fields, modern error/status mapping, statelessness,
and dual-era coexistence with the legacy session-based protocol.
"""

import base64
import json
import os
from unittest.mock import Mock, patch
import sys
from pathlib import Path

# Add plugin to path
plugin_path = Path(__file__).parent.parent / "MCP Server.indigoPlugin/Contents/Server Plugin"
sys.path.insert(0, str(plugin_path))

from mcp_server.mcp_handler import MCPHandler
from mcp_server.modern_era import (
    decode_header_value,
    http_status_for,
    is_modern_request,
)

MODERN = "2026-07-28"
META_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"
META_CLIENT_INFO = "io.modelcontextprotocol/clientInfo"
META_SERVER_INFO = "io.modelcontextprotocol/serverInfo"

_NAME_FIELDS = {"tools/call": "name", "resources/read": "uri", "prompts/get": "name"}


def make_handler(mock_vsm, **kwargs):
    """Create an MCPHandler with a mocked vector store manager."""
    mock_vsm_instance = Mock()
    mock_vsm_instance.get_vector_store = Mock(return_value=Mock())
    mock_vsm_instance.start = Mock()
    mock_vsm.return_value = mock_vsm_instance

    os.environ['DB_FILE'] = '/tmp/test_db'
    return MCPHandler(data_provider=Mock(), logger=Mock(), **kwargs)


def b64_sentinel(value):
    """Encode a header value in the spec's Base64 sentinel format."""
    return "=?base64?" + base64.b64encode(value.encode("utf-8")).decode("ascii") + "?="


def modern_request(method, params=None, *, msg_id=1, meta_version=MODERN,
                   header_version=MODERN, include_capabilities=True,
                   mcp_method="AUTO", mcp_name="AUTO", extra_headers=None):
    """
    Build a fully-valid modern (headers, body) pair, with knobs to knock out
    individual envelope pieces. mcp_method/mcp_name: "AUTO" derives the header
    from the body, None omits it, any other value is sent verbatim.
    """
    params = dict(params or {})
    meta = {META_CLIENT_INFO: {"name": "modern-test-client", "version": "1.0"}}
    if meta_version is not None:
        meta[META_VERSION] = meta_version
    if include_capabilities:
        meta[META_CAPABILITIES] = {}
    params["_meta"] = meta

    body = {"jsonrpc": "2.0", "method": method, "params": params}
    if msg_id is not None:
        body["id"] = msg_id

    headers = {"Accept": "application/json"}
    if header_version is not None:
        headers["MCP-Protocol-Version"] = header_version
    if mcp_method == "AUTO":
        headers["Mcp-Method"] = method
    elif mcp_method is not None:
        headers["Mcp-Method"] = mcp_method
    name_field = _NAME_FIELDS.get(method)
    if mcp_name == "AUTO":
        if name_field and name_field in params:
            headers["Mcp-Name"] = params[name_field]
    elif mcp_name is not None:
        headers["Mcp-Name"] = mcp_name
    if extra_headers:
        headers.update(extra_headers)

    return headers, json.dumps(body)


def post_modern(handler, method, params=None, **kwargs):
    """POST a modern request through handle_request; return the IWS response."""
    headers, body = modern_request(method, params, **kwargs)
    return handler.handle_request("POST", headers, body)


def do_initialize(handler):
    """Run a legacy POST initialize; return (response, session_id)."""
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": MCPHandler.SUPPORTED_PROTOCOL_VERSIONS[0],
            "clientInfo": {"name": "legacy-test-client", "version": "1.0"},
            "capabilities": {}
        }
    })
    response = handler.handle_request("POST", {"Accept": "application/json"}, body)
    return response, response["headers"].get("Mcp-Session-Id")


def rpc(response):
    """Parse the JSON-RPC body out of an IWS response."""
    return json.loads(response["content"])


class TestServerDiscover:
    """server/discover: versions, capabilities, identity, cacheability."""

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_discover_returns_versions_capabilities_and_identity(self, mock_vsm):
        handler = make_handler(mock_vsm)

        response = post_modern(handler, "server/discover")

        assert response["status"] == 200
        result = rpc(response)["result"]
        assert result["resultType"] == "complete"
        assert result["supportedVersions"] == ["2026-07-28", "2025-11-25", "2025-06-18"]
        assert result["capabilities"] == {"prompts": {}, "resources": {}, "tools": {}}
        assert result["_meta"][META_SERVER_INFO]["name"] == "Indigo MCP Server"
        assert result["ttlMs"] == 3600000
        assert result["cacheScope"] == "private"

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_discover_reports_injected_server_version(self, mock_vsm):
        handler = make_handler(mock_vsm, server_version="2099.1.0")

        result = rpc(post_modern(handler, "server/discover"))["result"]

        assert result["_meta"][META_SERVER_INFO]["version"] == "2099.1.0"


class TestEnvelopeValidation:
    """Required _meta fields and mirrored-header validation."""

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_missing_protocol_version_header_is_header_mismatch(self, mock_vsm):
        handler = make_handler(mock_vsm)

        response = post_modern(handler, "tools/list", header_version=None)

        assert response["status"] == 400
        assert rpc(response)["error"]["code"] == -32020

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_header_meta_version_mismatch_is_header_mismatch(self, mock_vsm):
        handler = make_handler(mock_vsm)

        response = post_modern(handler, "tools/list", header_version="2025-11-25")

        assert response["status"] == 400
        assert rpc(response)["error"]["code"] == -32020

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_missing_meta_protocol_version_is_invalid_params(self, mock_vsm):
        handler = make_handler(mock_vsm)

        response = post_modern(handler, "tools/list", meta_version=None)

        assert response["status"] == 400
        assert rpc(response)["error"]["code"] == -32602

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_missing_client_capabilities_is_invalid_params(self, mock_vsm):
        handler = make_handler(mock_vsm)

        response = post_modern(handler, "tools/list", include_capabilities=False)

        assert response["status"] == 400
        assert rpc(response)["error"]["code"] == -32602

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_unknown_version_returns_unsupported_with_supported_list(self, mock_vsm):
        handler = make_handler(mock_vsm)

        response = post_modern(handler, "tools/list",
                               meta_version="2099-01-01", header_version="2099-01-01")

        assert response["status"] == 400
        error = rpc(response)["error"]
        assert error["code"] == -32022
        assert error["data"]["supported"] == ["2026-07-28"]
        assert error["data"]["requested"] == "2099-01-01"

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_missing_mcp_method_header_is_header_mismatch(self, mock_vsm):
        handler = make_handler(mock_vsm)

        response = post_modern(handler, "tools/list", mcp_method=None)

        assert response["status"] == 400
        assert rpc(response)["error"]["code"] == -32020

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_mismatched_mcp_method_header_is_header_mismatch(self, mock_vsm):
        handler = make_handler(mock_vsm)

        response = post_modern(handler, "tools/list", mcp_method="tools/call")

        assert response["status"] == 400
        assert rpc(response)["error"]["code"] == -32020

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_base64_sentinel_mcp_method_is_decoded(self, mock_vsm):
        handler = make_handler(mock_vsm)

        response = post_modern(handler, "tools/list",
                               mcp_method=b64_sentinel("tools/list"))

        assert response["status"] == 200

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_malformed_base64_sentinel_is_header_mismatch(self, mock_vsm):
        handler = make_handler(mock_vsm)

        response = post_modern(handler, "tools/list", mcp_method="=?base64?!!!?=")

        assert response["status"] == 400
        assert rpc(response)["error"]["code"] == -32020

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_tools_call_without_mcp_name_is_header_mismatch(self, mock_vsm):
        handler = make_handler(mock_vsm)

        response = post_modern(handler, "tools/call",
                               {"name": "list_devices", "arguments": {}}, mcp_name=None)

        assert response["status"] == 400
        assert rpc(response)["error"]["code"] == -32020

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_tools_call_with_base64_mcp_name_succeeds(self, mock_vsm):
        handler = make_handler(mock_vsm)
        handler._tools["list_devices"]["function"] = lambda **kwargs: '{"devices": []}'

        response = post_modern(handler, "tools/call",
                               {"name": "list_devices", "arguments": {}},
                               mcp_name=b64_sentinel("list_devices"))

        assert response["status"] == 200
        assert rpc(response)["result"]["resultType"] == "complete"

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_resources_read_mcp_name_must_match_uri(self, mock_vsm):
        handler = make_handler(mock_vsm)

        response = post_modern(handler, "resources/read",
                               {"uri": "indigo://devices"},
                               mcp_name="indigo://variables")

        assert response["status"] == 400
        assert rpc(response)["error"]["code"] == -32020


class TestCacheableResults:
    """resultType, serverInfo _meta, and ttlMs/cacheScope on cacheable methods."""

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_tools_list_carries_cache_fields(self, mock_vsm):
        handler = make_handler(mock_vsm)

        result = rpc(post_modern(handler, "tools/list"))["result"]

        assert len(result["tools"]) == 44
        assert result["resultType"] == "complete"
        assert result["_meta"][META_SERVER_INFO]["name"] == "Indigo MCP Server"
        assert result["ttlMs"] == 3600000
        assert result["cacheScope"] == "private"

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_resources_list_carries_cache_fields(self, mock_vsm):
        handler = make_handler(mock_vsm)

        result = rpc(post_modern(handler, "resources/list"))["result"]

        assert len(result["resources"]) == 10
        assert result["resultType"] == "complete"
        assert result["ttlMs"] == 3600000
        assert result["cacheScope"] == "private"

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_prompts_list_is_empty_with_cache_fields(self, mock_vsm):
        handler = make_handler(mock_vsm)

        result = rpc(post_modern(handler, "prompts/list"))["result"]

        assert result["prompts"] == []
        assert result["resultType"] == "complete"
        assert result["ttlMs"] == 3600000

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_resources_read_is_immediately_stale(self, mock_vsm):
        handler = make_handler(mock_vsm)
        handler._resources["indigo://devices"]["function"] = lambda: '{"devices": []}'

        response = post_modern(handler, "resources/read", {"uri": "indigo://devices"})

        assert response["status"] == 200
        result = rpc(response)["result"]
        assert result["contents"][0]["uri"] == "indigo://devices"
        assert result["resultType"] == "complete"
        assert result["ttlMs"] == 0  # live device state must not be cached
        assert result["cacheScope"] == "private"

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_tools_call_has_no_cache_fields(self, mock_vsm):
        handler = make_handler(mock_vsm)
        handler._tools["list_devices"]["function"] = lambda **kwargs: '{"devices": []}'

        result = rpc(post_modern(handler, "tools/call",
                                 {"name": "list_devices", "arguments": {}}))["result"]

        assert result["resultType"] == "complete"
        assert "ttlMs" not in result
        assert "cacheScope" not in result


class TestModernErrors:
    """Removed methods, unknown entities, and error/status mapping."""

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_ping_is_unknown_method_404(self, mock_vsm):
        handler = make_handler(mock_vsm)

        response = post_modern(handler, "ping")

        assert response["status"] == 404
        assert rpc(response)["error"]["code"] == -32601

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_logging_set_level_is_unknown_method_404(self, mock_vsm):
        handler = make_handler(mock_vsm)

        response = post_modern(handler, "logging/setLevel", {"level": "debug"})

        assert response["status"] == 404
        assert rpc(response)["error"]["code"] == -32601

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_resource_not_found_is_32602(self, mock_vsm):
        handler = make_handler(mock_vsm)

        response = post_modern(handler, "resources/read", {"uri": "indigo://nonsense"})

        assert response["status"] == 400
        assert rpc(response)["error"]["code"] == -32602

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_unknown_tool_is_32602(self, mock_vsm):
        handler = make_handler(mock_vsm)

        response = post_modern(handler, "tools/call",
                               {"name": "no_such_tool", "arguments": {}})

        assert response["status"] == 400
        assert rpc(response)["error"]["code"] == -32602

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_tool_validation_error_is_tool_result_not_protocol_error(self, mock_vsm):
        handler = make_handler(mock_vsm)

        def failing_tool(**kwargs):
            raise ValueError("bad input")
        handler._tools["list_devices"]["function"] = failing_tool

        response = post_modern(handler, "tools/call",
                               {"name": "list_devices", "arguments": {}})

        assert response["status"] == 200
        result = rpc(response)["result"]
        assert result["isError"] is True
        assert result["resultType"] == "complete"

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_modern_notification_is_accepted_leniently(self, mock_vsm):
        handler = make_handler(mock_vsm)

        response = post_modern(handler, "notifications/whatever", msg_id=None,
                               mcp_method=None)

        assert response["status"] == 200
        assert response["content"]  # IWS requires a non-empty body


class TestStatelessness:
    """Modern requests never read, mint, or echo sessions."""

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_session_header_is_ignored_and_never_echoed(self, mock_vsm):
        handler = make_handler(mock_vsm)

        response = post_modern(handler, "tools/list",
                               extra_headers={"Mcp-Session-Id": "bogus-session"})

        assert response["status"] == 200
        assert "Mcp-Session-Id" not in response["headers"]
        assert handler._sessions == {}

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_modern_requests_leave_legacy_sessions_untouched(self, mock_vsm):
        handler = make_handler(mock_vsm)
        _, session_id = do_initialize(handler)
        last_seen = handler._sessions[session_id]["last_seen"]

        response = post_modern(handler, "tools/list",
                               extra_headers={"Mcp-Session-Id": session_id})

        assert response["status"] == 200
        assert handler._sessions[session_id]["last_seen"] == last_seen


class TestDualEraCoexistence:
    """Legacy initialize-based clients and modern clients on one endpoint."""

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_legacy_initialize_advertises_honest_capabilities(self, mock_vsm):
        handler = make_handler(mock_vsm)

        response, session_id = do_initialize(handler)

        assert response["status"] == 200
        assert session_id
        result = rpc(response)["result"]
        # No logging (no setLevel handler) and no listChanged/subscribe
        # (POST-only transport, no push channel).
        assert result["capabilities"] == {"prompts": {}, "resources": {}, "tools": {}}

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_interleaved_legacy_and_modern_requests_both_work(self, mock_vsm):
        handler = make_handler(mock_vsm)
        _, session_id = do_initialize(handler)

        modern_response = post_modern(handler, "tools/list")
        legacy_body = json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
        legacy_response = handler.handle_request(
            "POST",
            {"Accept": "application/json", "Mcp-Session-Id": session_id},
            legacy_body
        )

        assert modern_response["status"] == 200
        assert legacy_response["status"] == 200
        assert len(rpc(legacy_response)["result"]["tools"]) == 44

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_legacy_results_share_the_modern_native_shape(self, mock_vsm):
        handler = make_handler(mock_vsm)
        _, session_id = do_initialize(handler)

        legacy_body = json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
        response = handler.handle_request(
            "POST",
            {"Accept": "application/json", "Mcp-Session-Id": session_id},
            legacy_body
        )

        # Deliberate: both eras serve identical result bodies (extra fields are
        # legal for legacy clients), keeping the business handlers era-free.
        result = rpc(response)["result"]
        assert result["resultType"] == "complete"
        assert result["ttlMs"] == 3600000

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_legacy_resource_not_found_uses_shared_32602(self, mock_vsm):
        handler = make_handler(mock_vsm)
        _, session_id = do_initialize(handler)

        body = json.dumps({"jsonrpc": "2.0", "id": 4, "method": "resources/read",
                           "params": {"uri": "indigo://nonsense"}})
        response = handler.handle_request(
            "POST",
            {"Accept": "application/json", "Mcp-Session-Id": session_id},
            body
        )

        # Legacy responses keep the HTTP-200-always convention, but the error
        # code follows 2026-07-28 (-32602, not the retired -32002).
        assert response["status"] == 200
        assert rpc(response)["error"]["code"] == -32602

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_legacy_ping_still_works(self, mock_vsm):
        handler = make_handler(mock_vsm)
        _, session_id = do_initialize(handler)

        body = json.dumps({"jsonrpc": "2.0", "id": 5, "method": "ping"})
        response = handler.handle_request(
            "POST",
            {"Accept": "application/json", "Mcp-Session-Id": session_id},
            body
        )

        assert response["status"] == 200
        assert rpc(response)["result"] == {}


class TestModernEraPureFunctions:
    """Unit tests for the pure helpers in modern_era.py."""

    def test_decode_header_value_passthrough(self):
        assert decode_header_value("tools/list") == "tools/list"

    def test_decode_header_value_decodes_sentinel(self):
        assert decode_header_value(b64_sentinel("héllo, 世界")) == "héllo, 世界"

    def test_decode_header_value_malformed_sentinel_returned_verbatim(self):
        assert decode_header_value("=?base64?!!!?=") == "=?base64?!!!?="

    def test_initialize_is_never_modern(self):
        payload = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        assert not is_modern_request(payload, {"mcp-protocol-version": MODERN})

    def test_meta_version_makes_request_modern(self):
        payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list",
                   "params": {"_meta": {META_VERSION: MODERN}}}
        assert is_modern_request(payload, {})

    def test_legacy_shaped_request_is_not_modern(self):
        payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        assert not is_modern_request(payload, {"mcp-protocol-version": "2025-11-25"})

    def test_http_status_mapping(self):
        assert http_status_for({"result": {}}) == 200
        assert http_status_for({"error": {"code": -32601}}) == 404
        assert http_status_for({"error": {"code": -32603}}) == 500
        assert http_status_for({"error": {"code": -32020}}) == 400
        assert http_status_for({"error": {"code": -32602}}) == 400
