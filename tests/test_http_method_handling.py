"""
Tests for HTTP method handling and session lifecycle in MCPHandler.handle_request.

Covers issue #29: DELETE-based session termination, idle-session TTL sweep,
and 405 responses for GET/other methods (with corrected Allow header).
"""

import json
import os
import time
import pytest
from unittest.mock import Mock, patch
import sys
from pathlib import Path

# Add plugin to path
plugin_path = Path(__file__).parent.parent / "MCP Server.indigoPlugin/Contents/Server Plugin"
sys.path.insert(0, str(plugin_path))

from mcp_server.mcp_handler import MCPHandler


def make_handler(mock_vsm):
    """Create an MCPHandler with a mocked vector store manager."""
    mock_vsm_instance = Mock()
    mock_vsm_instance.get_vector_store = Mock(return_value=Mock())
    mock_vsm_instance.start = Mock()
    mock_vsm.return_value = mock_vsm_instance

    os.environ['DB_FILE'] = '/tmp/test_db'
    return MCPHandler(data_provider=Mock(), logger=Mock())


def do_initialize(handler):
    """Run a POST initialize through handle_request; return (response, session_id)."""
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": MCPHandler.SUPPORTED_PROTOCOL_VERSIONS[0],
            "clientInfo": {"name": "test-client", "version": "1.0"},
            "capabilities": {}
        }
    })
    response = handler.handle_request("POST", {"Accept": "application/json"}, body)
    session_id = response["headers"].get("Mcp-Session-Id")
    return response, session_id


class TestHTTPMethodHandling:
    """HTTP method dispatch: POST, DELETE, GET, and others."""

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_post_initialize_creates_session_and_returns_session_header(self, mock_vsm):
        handler = make_handler(mock_vsm)
        response, session_id = do_initialize(handler)

        assert response["status"] == 200
        assert session_id
        assert session_id in handler._sessions
        result = json.loads(response["content"])
        assert result["result"]["serverInfo"]["name"] == "Indigo MCP Server"

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_delete_removes_session(self, mock_vsm):
        handler = make_handler(mock_vsm)
        _, session_id = do_initialize(handler)
        assert session_id in handler._sessions

        response = handler.handle_request("DELETE", {"Mcp-Session-Id": session_id}, "")

        assert response["status"] == 200
        assert session_id not in handler._sessions

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_delete_unknown_session_is_idempotent_200(self, mock_vsm):
        handler = make_handler(mock_vsm)

        response = handler.handle_request("DELETE", {"Mcp-Session-Id": "no-such-session"}, "")

        assert response["status"] == 200

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_delete_missing_header_returns_400(self, mock_vsm):
        handler = make_handler(mock_vsm)

        response = handler.handle_request("DELETE", {}, "")

        assert response["status"] == 400
        assert "Mcp-Session-Id" in response["content"]

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_get_returns_405_with_allow_header(self, mock_vsm):
        handler = make_handler(mock_vsm)

        response = handler.handle_request("GET", {"Accept": "text/event-stream"}, "")

        assert response["status"] == 405
        assert "POST" in response["headers"]["Allow"]
        assert "DELETE" in response["headers"]["Allow"]
        # IWS 500s ("incorrect value returned from plugin") on empty content
        assert response["content"]

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_405_has_nonempty_body_for_iws(self, mock_vsm):
        handler = make_handler(mock_vsm)

        response = handler.handle_request("PUT", {}, "")

        assert response["status"] == 405
        assert response["content"]
        assert "Content-Type" in response["headers"]

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_put_returns_405(self, mock_vsm):
        handler = make_handler(mock_vsm)

        response = handler.handle_request("PUT", {}, "")

        assert response["status"] == 405


class TestSessionTTLSweep:
    """Idle-session TTL sweep behavior."""

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_sweep_purges_idle_and_keeps_fresh(self, mock_vsm):
        handler = make_handler(mock_vsm)
        _, stale_id = do_initialize(handler)
        _, fresh_id = do_initialize(handler)

        handler._sessions[stale_id]["last_seen"] = time.time() - 3 * 3600
        handler._last_session_sweep = 0  # force the next request to sweep

        ping = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"})
        handler.handle_request(
            "POST",
            {"Accept": "application/json", "Mcp-Session-Id": fresh_id},
            ping
        )

        assert stale_id not in handler._sessions
        assert fresh_id in handler._sessions

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_sweep_is_rate_limited(self, mock_vsm):
        handler = make_handler(mock_vsm)
        _, stale_id = do_initialize(handler)

        # Session is stale, but a sweep just ran: it must survive this request
        handler._sessions[stale_id]["last_seen"] = time.time() - 3 * 3600
        handler._last_session_sweep = time.time()

        ping = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"})
        handler.handle_request(
            "POST",
            {"Accept": "application/json", "Mcp-Session-Id": stale_id},
            ping
        )

        assert stale_id in handler._sessions


class TestPostFlowUnaffected:
    """Regression: normal POST dispatch still works alongside DELETE."""

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_post_with_session_works_after_delete_of_other_session(self, mock_vsm):
        handler = make_handler(mock_vsm)
        _, doomed_id = do_initialize(handler)
        _, live_id = do_initialize(handler)

        handler.handle_request("DELETE", {"Mcp-Session-Id": doomed_id}, "")

        body = json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
        response = handler.handle_request(
            "POST",
            {"Accept": "application/json", "Mcp-Session-Id": live_id},
            body
        )

        assert response["status"] == 200
        result = json.loads(response["content"])
        assert "tools" in result["result"]
