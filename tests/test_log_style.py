"""Tests for the log_style helpers (user-friendly logging conventions)."""

import json
import logging
import pytest
import sys
from pathlib import Path

# Add plugin to path
plugin_path = Path(__file__).parent.parent / "MCP Server.indigoPlugin/Contents/Server Plugin"
sys.path.insert(0, str(plugin_path))

# conftest installs MagicMock package stubs for mcp_server.common, so a
# `from mcp_server.common import log_style` would yield a mock attribute;
# importing by full dotted path loads the real module via the stub's __path__.
import importlib
log_style = importlib.import_module("mcp_server.common.log_style")


@pytest.fixture(autouse=True)
def reset_verbose():
    log_style.set_verbose_activity(False)
    yield
    log_style.set_verbose_activity(False)


@pytest.fixture
def logger():
    lg = logging.getLogger("test_log_style")
    lg.setLevel(logging.DEBUG)
    return lg


class TestFail:
    def test_emits_one_error_and_debug_traceback(self, logger, caplog):
        exc = RuntimeError("boom")
        with caplog.at_level(logging.DEBUG, logger="test_log_style"):
            log_style.fail(logger, "Turn on 'Kitchen Lights'", exc)

        errors = [r for r in caplog.records if r.levelno == logging.ERROR]
        debugs = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert len(errors) == 1
        assert errors[0].message.startswith("❌ Turn on 'Kitchen Lights' failed: boom")
        assert len(debugs) == 1
        assert debugs[0].exc_info is not None

    def test_hint_appended(self, logger, caplog):
        with caplog.at_level(logging.ERROR, logger="test_log_style"):
            log_style.fail(logger, "Connect", RuntimeError("x"), hint="check Plugin Config")

        assert "— check Plugin Config" in caplog.records[0].message


class TestPlainReason:
    def test_timeout(self):
        assert "timed out" in log_style.plain_reason(TimeoutError("deadline"))

    def test_connection(self):
        assert "couldn't connect" in log_style.plain_reason(ConnectionError("refused"))

    def test_json_decode(self):
        try:
            json.loads("{bad")
        except json.JSONDecodeError as e:
            assert "invalid response" in log_style.plain_reason(e)

    def test_key_error(self):
        assert "not found: name" in log_style.plain_reason(KeyError("name"))

    def test_fallback_is_str(self):
        assert log_style.plain_reason(RuntimeError("custom message")) == "custom message"

    def test_empty_message_falls_back_to_type(self):
        assert log_style.plain_reason(RuntimeError()) == "RuntimeError"

    def test_openai_auth_by_type_name(self):
        class AuthenticationError(Exception):
            pass
        assert "API key" in log_style.plain_reason(AuthenticationError("401"))


class TestActivity:
    def test_write_is_info(self, logger, caplog):
        with caplog.at_level(logging.DEBUG, logger="test_log_style"):
            log_style.activity(logger, "Kitchen Lights → on (was off)", write=True)

        assert caplog.records[0].levelno == logging.INFO
        assert caplog.records[0].message == "🔧 Kitchen Lights → on (was off)"

    def test_read_is_debug_by_default(self, logger, caplog):
        with caplog.at_level(logging.DEBUG, logger="test_log_style"):
            log_style.activity(logger, "Search 'kitchen' → 5 results", write=False)

        assert caplog.records[0].levelno == logging.DEBUG

    def test_read_promoted_when_verbose(self, logger, caplog):
        log_style.set_verbose_activity(True)
        with caplog.at_level(logging.DEBUG, logger="test_log_style"):
            log_style.activity(logger, "Search 'kitchen' → 5 results", write=False)

        assert caplog.records[0].levelno == logging.INFO


class TestHostOnly:
    def test_strips_path_and_query(self):
        assert log_style.host_only("https://hooks.example.com/secret/token?key=abc") == "hooks.example.com"

    def test_keeps_port(self):
        assert log_style.host_only("http://10.0.0.5:8123/api/webhook/x") == "10.0.0.5:8123"

    def test_strips_basic_auth_credentials(self):
        assert log_style.host_only("https://user:pass@host.example.com/x") == "host.example.com"

    def test_none_and_empty(self):
        assert log_style.host_only(None) == "unknown"
        assert log_style.host_only("") == "unknown"
