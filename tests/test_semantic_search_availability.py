"""
Tests for optional semantic search (search_entities).

LanceDB ships macOS wheels for Apple Silicon only, so requirements.txt skips
it on Intel Macs. There the plugin must start, hide search_entities and
serve every other tool; with LanceDB it runs the search index as before.
"""

import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

plugin_path = Path(__file__).parent.parent / "MCP Advanced Tools.indigoPlugin/Contents/Server Plugin"
sys.path.insert(0, str(plugin_path))

# Import everything plugin.py imports BEFORE it is loaded with a fake
# `indigo` module, so these modules keep binding indigo = None
import openai  # noqa: E402,F401
import mcp_server.adapters.indigo_data_provider  # noqa: E402,F401
import mcp_server.common.log_style  # noqa: E402,F401
import mcp_server.common.openai_client.langsmith_config  # noqa: E402,F401
from mcp_server.common.vector_store import availability  # noqa: E402
from mcp_server.common.vector_store.availability import (  # noqa: E402
    INTEL_MAC_REASON,
    SemanticSearchStatus,
    detect_semantic_search,
)
from mcp_server.mcp_handler import MCPHandler  # noqa: E402

# Every built-in tool except search_entities (webhooks off)
OTHER_TOOLS = {
    "list_triggers",
    "list_schedules",
    "get_trigger_details",
    "get_schedule_details",
    "get_action_group_details",
    "find_automation_references",
    "investigate_event",
    "query_event_log",
    "control_trigger",
    "control_schedule",
    "control_action_group",
    "update_trigger",
    "update_schedule",
    "update_action_group",
    "manage_tags",
    "tag_objects",
}

UNAVAILABLE = SemanticSearchStatus(available=False, reason=INTEL_MAC_REASON, expected=True)
AVAILABLE = SemanticSearchStatus(available=True)


def _no_import(name):
    raise AssertionError(f"{name} must not be imported on an Intel Mac")


# ----------------------------------------------------------------------
# Detection


class TestDetection:
    def test_intel_mac_is_unavailable_without_importing(self):
        status = detect_semantic_search("darwin", "x86_64", importer=_no_import)
        assert not status.available
        assert status.expected
        assert status.reason == INTEL_MAC_REASON
        assert "search_entities" in status.reason
        assert "Apple Silicon" in status.reason

    def test_apple_silicon_with_lancedb_is_available(self):
        imported = []
        status = detect_semantic_search("darwin", "arm64", importer=imported.append)
        assert status.available
        assert status.reason == ""
        assert imported == ["lancedb", "pyarrow"]

    def test_apple_silicon_failed_import_is_unexpected(self):
        def broken(name):
            raise ImportError("dlopen failed: liblance.dylib")

        status = detect_semantic_search("darwin", "arm64", importer=broken)
        assert not status.available
        assert not status.expected
        assert "reinstall" in status.reason
        assert "dlopen failed" in status.detail

    def test_native_library_oserror_is_caught(self):
        def broken(name):
            raise OSError("bad CPU type in executable")

        status = detect_semantic_search("darwin", "arm64", importer=broken)
        assert not status.available
        assert "OSError" in status.detail

    def test_linux_tries_the_import(self):
        # Development and CI run on Linux: the answer is whether it imports
        imported = []
        assert detect_semantic_search("linux", "x86_64", importer=imported.append).available
        assert imported == ["lancedb", "pyarrow"]

    def test_status_is_detected_once(self):
        availability.semantic_search_status.cache_clear()
        try:
            with patch.object(availability, "detect_semantic_search", return_value=UNAVAILABLE) as detect:
                first = availability.semantic_search_status()
                second = availability.semantic_search_status()
            assert first is second is UNAVAILABLE
            assert detect.call_count == 1
        finally:
            availability.semantic_search_status.cache_clear()


def test_server_modules_do_not_import_lancedb():
    """Importing the server (and the vector store package) must not need lancedb."""
    code = (
        "import sys\n"
        "import mcp_server.mcp_handler\n"
        "import mcp_server.common.vector_store\n"
        "import mcp_server.common.vector_store.vector_store_manager\n"
        "print(sorted(m for m in ('lancedb', 'pyarrow') if m in sys.modules))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(plugin_path),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"


# ----------------------------------------------------------------------
# MCPHandler


def make_handler(mock_vsm, **kwargs):
    mock_vsm_instance = Mock()
    mock_vsm_instance.get_vector_store = Mock(return_value=Mock())
    mock_vsm.return_value = mock_vsm_instance
    return MCPHandler(data_provider=Mock(), logger=Mock(), **kwargs)


MODERN = "2026-07-28"


def rpc(handler, method, params=None):
    """One stateless (2026-07-28) request through handle_request."""
    params = dict(params or {})
    params["_meta"] = {
        "io.modelcontextprotocol/protocolVersion": MODERN,
        "io.modelcontextprotocol/clientCapabilities": {},
        "io.modelcontextprotocol/clientInfo": {"name": "test", "version": "1"},
    }
    headers = {"Accept": "application/json", "MCP-Protocol-Version": MODERN, "Mcp-Method": method}
    if method == "tools/call":
        headers["Mcp-Name"] = params["name"]
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    return json.loads(handler.handle_request("POST", headers, body)["content"])


def listed_tools(handler):
    return {t["name"]: t for t in rpc(handler, "tools/list")["result"]["tools"]}


class TestHandlerWithoutSemanticSearch:
    @pytest.fixture
    def handler(self, monkeypatch):
        # No DB_FILE either: without a search index it is not needed
        monkeypatch.delenv("DB_FILE", raising=False)
        with patch("mcp_server.mcp_handler.VectorStoreManager") as mock_vsm:
            handler = make_handler(mock_vsm, semantic_search=False)
            handler._mock_vsm = mock_vsm
            yield handler

    def test_no_vector_store_is_created(self, handler):
        handler._mock_vsm.assert_not_called()
        assert handler.vector_store_manager is None
        assert handler.search_handler is None

    def test_search_entities_is_not_listed(self, handler):
        tools = listed_tools(handler)
        assert "search_entities" not in tools
        assert set(tools) == OTHER_TOOLS

    def test_no_listed_tool_mentions_search_entities(self, handler):
        for name, tool in listed_tools(handler).items():
            assert "search_entities" not in json.dumps(tool), name

    def test_webhook_tools_still_register(self, monkeypatch):
        monkeypatch.delenv("DB_FILE", raising=False)
        with patch("mcp_server.mcp_handler.VectorStoreManager") as mock_vsm:
            handler = make_handler(mock_vsm, semantic_search=False, subscription_handler=Mock())
        assert set(listed_tools(handler)) == OTHER_TOOLS | {
            "create_event_subscription",
            "list_event_subscriptions",
            "delete_event_subscription",
        }

    def test_instructions_do_not_advertise_search_entities(self, handler):
        assert "search_entities" not in handler.instructions
        assert "semantic search" not in handler.instructions
        assert handler.instructions == MCPHandler.SERVER_INSTRUCTIONS_NO_SEARCH
        assert "MCP Control" in handler.instructions
        assert "find_automation_references" in handler.instructions
        assert rpc(handler, "server/discover")["result"]["instructions"] == handler.instructions
        assert handler.legacy.instructions == handler.instructions

    def test_calling_search_entities_explains_why(self, handler):
        resp = rpc(handler, "tools/call", {"name": "search_entities", "arguments": {"query": "lamp"}})
        assert resp["error"]["code"] == -32602
        assert "Apple Silicon" in resp["error"]["message"]

    def test_other_tools_still_dispatch(self, handler):
        handler.automation_handler = Mock()
        handler.tool_wrappers.automation_handler = handler.automation_handler
        handler.automation_handler.list_triggers.return_value = {"triggers": [], "total": 0}
        resp = rpc(handler, "tools/call", {"name": "list_triggers", "arguments": {}})
        assert "error" not in resp
        assert not resp["result"].get("isError")

    def test_stop_is_safe(self, handler):
        handler.stop()


class TestHandlerWithSemanticSearch:
    @pytest.fixture
    def handler(self, monkeypatch):
        monkeypatch.setenv("DB_FILE", "/tmp/test_db")
        with patch("mcp_server.mcp_handler.VectorStoreManager") as mock_vsm:
            handler = make_handler(mock_vsm)  # semantic_search defaults to True
            handler._mock_vsm = mock_vsm
            yield handler

    def test_vector_store_starts(self, handler):
        handler._mock_vsm.assert_called_once()
        assert handler._mock_vsm.call_args.kwargs["db_path"] == "/tmp/test_db"
        handler.vector_store_manager.start.assert_called_once()
        assert handler.search_handler is not None

    def test_search_entities_is_listed_first(self, handler):
        tools = listed_tools(handler)
        assert set(tools) == OTHER_TOOLS | {"search_entities"}
        assert next(iter(tools)) == "search_entities"

    def test_instructions_advertise_search_entities(self, handler):
        assert handler.instructions == MCPHandler.SERVER_INSTRUCTIONS
        assert "search_entities" in handler.instructions

    def test_stop_stops_the_vector_store(self, handler):
        vsm = handler.vector_store_manager
        handler.stop()
        vsm.stop.assert_called_once()

    def test_db_file_is_still_required(self, monkeypatch):
        monkeypatch.delenv("DB_FILE", raising=False)
        with patch("mcp_server.mcp_handler.VectorStoreManager") as mock_vsm:
            with pytest.raises(ValueError, match="DB_FILE"):
                make_handler(mock_vsm, semantic_search=True)


# ----------------------------------------------------------------------
# plugin.py (loaded with a fake indigo module)


@pytest.fixture(scope="module")
def plugin_module():
    class FakePluginBase:
        pass

    fake = types.ModuleType("indigo")
    fake.PluginBase = FakePluginBase
    fake.Dict = dict
    fake.server = Mock()
    fake.__getattr__ = lambda name: type(name, (), {})

    spec = importlib.util.spec_from_file_location(
        "mcp_server_plugin_semantic_under_test", plugin_path / "plugin.py"
    )
    module = importlib.util.module_from_spec(spec)
    saved = sys.modules.get("indigo")
    sys.modules["indigo"] = fake
    try:
        spec.loader.exec_module(module)
    finally:
        if saved is None:
            sys.modules.pop("indigo", None)
        else:
            sys.modules["indigo"] = saved
    return module


def make_plugin(plugin_module, api_key=""):
    plugin = plugin_module.Plugin.__new__(plugin_module.Plugin)
    plugin.logger = Mock()
    plugin.openai_api_key = api_key
    return plugin


def test_cpu_check_is_gone(plugin_module):
    assert not hasattr(plugin_module.Plugin, "check_cpu_compatibility")


class TestPluginWithoutSemanticSearch:
    @pytest.fixture(autouse=True)
    def unavailable(self, plugin_module):
        with patch.object(plugin_module, "semantic_search_status", return_value=UNAVAILABLE):
            yield

    def test_openai_key_not_required(self, plugin_module):
        plugin = make_plugin(plugin_module, api_key="")
        with patch.object(plugin_module.openai, "OpenAI") as client:
            assert plugin.test_connections() is True
        client.assert_not_called()
        plugin.logger.error.assert_not_called()

    def test_config_dialog_accepts_an_empty_key(self, plugin_module):
        plugin = make_plugin(plugin_module)
        ok, _, errors = plugin.validatePrefsConfigUi({"openai_api_key": "", "log_level": "20"})
        assert ok, errors

    def test_one_info_line_at_startup(self, plugin_module):
        plugin = make_plugin(plugin_module)
        plugin.log_semantic_search_status()
        assert plugin.logger.info.call_count == 1
        line = plugin.logger.info.call_args.args[0]
        assert "search_entities" in line and "Apple Silicon" in line
        plugin.logger.warning.assert_not_called()

    def test_startup_and_shutdown(self, plugin_module, tmp_path):
        plugin = make_plugin(plugin_module)
        plugin.pluginPrefs = {}
        plugin.small_model = "gpt-6-luna"
        plugin.enable_langsmith = False
        plugin.enable_webhooks = False
        plugin.pluginVersion = "test"
        plugin.confirm_tag = "ask-first"
        plugin.external_tool_policy = None
        plugin.subscription_manager = None
        plugin.webhook_dispatcher = None
        plugin.mcp_handler = None
        indigo = plugin_module.indigo
        indigo.server = Mock()
        indigo.server.getInstallFolderPath.return_value = str(tmp_path)
        indigo.devices = Mock()
        indigo.variables = Mock()
        with patch.object(plugin_module, "IndigoDataProvider"), \
                patch.object(plugin_module, "ExternalToolManager"), \
                patch.object(plugin_module, "MCPHandler") as handler_cls, \
                patch.object(plugin_module.Plugin, "_subscribe_to_provider_broadcasts"), \
                patch.object(plugin_module.Plugin, "_get_mcp_client_urls", return_value=[]):
            plugin.startup()
            handler_cls.assert_called_once()
            assert handler_cls.call_args.kwargs["semantic_search"] is False
            assert plugin.mcp_handler is handler_cls.return_value
            plugin.logger.error.assert_not_called()

            plugin.shutdown()
            handler_cls.return_value.stop.assert_called_once()
            assert plugin.mcp_handler is None


class TestPluginWithSemanticSearch:
    @pytest.fixture(autouse=True)
    def available(self, plugin_module):
        with patch.object(plugin_module, "semantic_search_status", return_value=AVAILABLE):
            yield

    def test_openai_key_required(self, plugin_module):
        plugin = make_plugin(plugin_module, api_key="")
        assert plugin.test_connections() is False
        plugin.logger.error.assert_called_once()

    def test_config_dialog_requires_a_key(self, plugin_module):
        plugin = make_plugin(plugin_module)
        ok, _, errors = plugin.validatePrefsConfigUi({"openai_api_key": "", "log_level": "20"})
        assert not ok
        assert "openai_api_key" in errors

    def test_nothing_logged_at_startup(self, plugin_module):
        plugin = make_plugin(plugin_module)
        plugin.log_semantic_search_status()
        plugin.logger.info.assert_not_called()
        plugin.logger.warning.assert_not_called()


def test_broken_install_on_apple_silicon_warns(plugin_module):
    broken = SemanticSearchStatus(
        available=False, reason="LanceDB could not be loaded", expected=False, detail="ImportError: x"
    )
    plugin = make_plugin(plugin_module)
    with patch.object(plugin_module, "semantic_search_status", return_value=broken):
        plugin.log_semantic_search_status()
    plugin.logger.warning.assert_called_once()
    plugin.logger.info.assert_not_called()
    assert "ImportError" in plugin.logger.debug.call_args.args[0]
