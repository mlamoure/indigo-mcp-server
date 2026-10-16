"""
Tests for the plugin-provided tools policy (all / allowlist / blocklist):
ProviderPolicy, the config dialog's plugin list, broadcast subscriptions,
ExternalToolManager filtering and the MCPHandler integration (blocked-tool
message, throttled installed-plugin check, change-only logging).
"""

import importlib.util
import json
import os
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
from mcp_server.external_tools import manager as manager_module  # noqa: E402
from mcp_server.external_tools.external_tool_handler import ExternalToolHandler  # noqa: E402
from mcp_server.external_tools.manager import ExternalToolManager  # noqa: E402
from mcp_server.external_tools.manifest import ExternalTool, ProviderManifest  # noqa: E402
from mcp_server.external_tools import policy as policy_module  # noqa: E402
from mcp_server.external_tools.policy import (  # noqa: E402
    MODE_ALL,
    MODE_ALLOWLIST,
    MODE_BLOCKLIST,
    ProviderPolicy,
    build_plugin_list_options,
    describe_policy_result,
    normalize_plugin_ids,
    provider_subscription_ids,
)
from mcp_server.mcp_handler import MCPHandler  # noqa: E402

SELF_ID = "com.vtmikel.mcp_server"


def make_tool(name="get_status", write=False):
    return ExternalTool(
        name=name,
        description=f"{name} description",
        input_schema={"type": "object", "properties": {}},
        write=write,
        timeout_seconds=30,
        action_id="mcp_tool_invoke",
    )


def make_provider(plugin_id, prefix, display_name=None, tools=None):
    return ProviderManifest(
        plugin_id=plugin_id,
        display_name=display_name or f"Plugin {prefix}",
        prefix=prefix,
        tools=tools if tools is not None else [make_tool()],
    )


AUTOLIGHTS = make_provider(
    "com.vtmikel.autolights",
    "autolights",
    "Auto Lights",
    [make_tool("list_zones"), make_tool("update_zone", write=True)],
)
ROOMIE = make_provider(
    "com.vtmikel.roomie",
    "roomie",
    "Roomie Remote",
    [make_tool("list_rooms"), make_tool("press_button", write=True)],
)


def make_handler(**kwargs):
    with patch("mcp_server.mcp_handler.VectorStoreManager") as mock_vsm:
        mock_vsm_instance = Mock()
        mock_vsm_instance.get_vector_store = Mock(return_value=Mock())
        mock_vsm_instance.start = Mock()
        mock_vsm.return_value = mock_vsm_instance
        os.environ["DB_FILE"] = "/tmp/test_db"
        kwargs.setdefault("logger", Mock())
        return MCPHandler(data_provider=Mock(), **kwargs)


class FakeIndigoList:
    """Iterable like indigo.List: list() works, but it is not a list."""

    def __init__(self, items):
        self._items = list(items)

    def __iter__(self):
        return iter(self._items)


# ----------------------------------------------------------------------
# ProviderPolicy


def test_policy_default_is_all():
    policy = ProviderPolicy()
    assert policy.mode == MODE_ALL
    assert policy.allows("com.example.anything")


def test_policy_missing_prefs_map_to_all_without_warning():
    logger = Mock()
    assert ProviderPolicy.from_prefs({}, logger=logger) == ProviderPolicy()
    assert ProviderPolicy.from_prefs(None, logger=logger) == ProviderPolicy()
    logger.warning.assert_not_called()


def test_policy_unknown_mode_maps_to_all_and_warns_once():
    logger = Mock()
    policy_module._warned_modes.discard("sometimes")
    prefs = {"external_tool_policy": "sometimes", "external_tool_allowlist": ["a"]}
    assert ProviderPolicy.from_prefs(prefs, logger=logger) == ProviderPolicy()
    assert ProviderPolicy.from_prefs(prefs, logger=logger) == ProviderPolicy()
    assert logger.warning.call_count == 1


def test_policy_allowlist_semantics():
    policy = ProviderPolicy.from_prefs(
        {
            "external_tool_policy": "allowlist",
            "external_tool_allowlist": ["com.vtmikel.autolights"],
            "external_tool_blocklist": ["com.vtmikel.autolights", "com.vtmikel.roomie"],
        }
    )
    assert policy.mode == MODE_ALLOWLIST
    assert policy.allows("com.vtmikel.autolights")
    assert not policy.allows("com.vtmikel.roomie")


def test_policy_blocklist_semantics_uses_its_own_list():
    policy = ProviderPolicy.from_prefs(
        {
            "external_tool_policy": "blocklist",
            "external_tool_allowlist": ["com.vtmikel.roomie"],
            "external_tool_blocklist": ["com.vtmikel.autolights"],
        }
    )
    assert policy.mode == MODE_BLOCKLIST
    assert not policy.allows("com.vtmikel.autolights")
    assert policy.allows("com.vtmikel.roomie")


def test_policy_empty_allowlist_allows_nothing():
    policy = ProviderPolicy.from_prefs({"external_tool_policy": "allowlist"})
    assert policy.mode == MODE_ALLOWLIST
    assert not policy.allows("com.vtmikel.autolights")


def test_policy_normalizes_indigo_list_input():
    prefs = {
        "external_tool_policy": "blocklist",
        "external_tool_blocklist": FakeIndigoList(["com.a", " com.b ", "", "com.a"]),
    }
    policy = ProviderPolicy.from_prefs(prefs)
    assert policy.plugin_ids == frozenset({"com.a", "com.b"})


def test_normalize_plugin_ids_shapes():
    assert normalize_plugin_ids(None) == []
    assert normalize_plugin_ids("") == []
    assert normalize_plugin_ids("com.a,com.b") == ["com.a", "com.b"]
    assert normalize_plugin_ids(FakeIndigoList(["com.b", "com.a", "com.b"])) == [
        "com.b",
        "com.a",
    ]


def test_describe_policy_result_lines():
    allow = ProviderPolicy(MODE_ALLOWLIST, frozenset({"com.vtmikel.autolights"}))
    assert (
        describe_policy_result(allow, ["Auto Lights"], ["Roomie Remote"])
        == "Plugin-provided tools: only Auto Lights allowed (Roomie Remote blocked)"
    )
    empty = ProviderPolicy(MODE_ALLOWLIST, frozenset())
    assert describe_policy_result(empty, [], ["Auto Lights"]) == (
        "Plugin-provided tools: allowlist is empty — no plugin-provided tools are exposed"
    )
    block = ProviderPolicy(MODE_BLOCKLIST, frozenset({"com.vtmikel.roomie"}))
    assert (
        describe_policy_result(block, ["Auto Lights"], ["Roomie Remote"])
        == "Plugin-provided tools: Roomie Remote blocked (Auto Lights allowed)"
    )
    assert describe_policy_result(ProviderPolicy(), ["Auto Lights"], []) == (
        "Plugin-provided tools: all plugins allowed (Auto Lights)"
    )


# ----------------------------------------------------------------------
# Config dialog list and subscription set (pure helpers)


def test_plugin_list_options_labels_sorting_and_self_excluded():
    installed = [
        ("com.vtmikel.roomie", "Roomie Remote", True),
        (SELF_ID, "MCP Advanced Tools", True),
        ("com.vtmikel.autofan", "Auto Fan", True),
        ("com.vtmikel.dometic", "Dometic CFX", False),
        ("com.vtmikel.autolights", "Auto Lights", True),
        ("com.sonos", "sonos", True),
    ]
    counts = {"com.vtmikel.autolights": 18, "com.vtmikel.roomie": 20}
    options = build_plugin_list_options(
        installed, counts, ["com.example.removed", "com.vtmikel.roomie"], SELF_ID
    )
    assert options == [
        ("com.vtmikel.autofan", "Auto Fan"),
        ("com.vtmikel.autolights", "Auto Lights — MCP tools: 18"),
        ("com.vtmikel.dometic", "Dometic CFX (disabled)"),
        ("com.vtmikel.roomie", "Roomie Remote — MCP tools: 20"),
        ("com.sonos", "sonos"),
        ("com.example.removed", "com.example.removed (not installed)"),
    ]


def test_plugin_list_options_disabled_provider_shows_both_labels():
    options = build_plugin_list_options(
        [("com.vtmikel.autolights", "Auto Lights", False)],
        {"com.vtmikel.autolights": 3},
        [],
        SELF_ID,
    )
    assert options == [("com.vtmikel.autolights", "Auto Lights — MCP tools: 3 (disabled)")]


def test_subscription_ids_are_installed_union_allowlist():
    ids = provider_subscription_ids(
        ["com.a", "com.b", SELF_ID], ["com.b", "com.not.installed"], SELF_ID
    )
    assert ids == {"com.a", "com.b", "com.not.installed"}


# ----------------------------------------------------------------------
# ExternalToolManager


def _build(manager, manifests):
    with patch.object(manager_module, "discover_manifests", return_value=manifests):
        return manager.rescan_and_build(ExternalToolHandler(logger=Mock()))


def test_all_mode_registry_matches_default_manager():
    default_entries = _build(ExternalToolManager(logger=Mock()), [AUTOLIGHTS, ROOMIE])
    all_entries = _build(
        ExternalToolManager(logger=Mock(), policy_supplier=lambda: ProviderPolicy()),
        [AUTOLIGHTS, ROOMIE],
    )
    assert set(all_entries) == set(default_entries)
    assert set(all_entries) == {
        "autolights_list_zones",
        "autolights_update_zone",
        "roomie_list_rooms",
        "roomie_press_button",
    }


def test_blocklisted_provider_registers_no_tools():
    policy = ProviderPolicy(MODE_BLOCKLIST, frozenset({"com.vtmikel.roomie"}))
    manager = ExternalToolManager(logger=Mock(), policy_supplier=lambda: policy)
    entries = _build(manager, [AUTOLIGHTS, ROOMIE])
    assert set(entries) == {"autolights_list_zones", "autolights_update_zone"}
    assert manager.provider_ids() == ["com.vtmikel.autolights"]
    assert manager.blocked_provider_ids() == ["com.vtmikel.roomie"]
    assert manager.blocked_tool_names == {
        "roomie_list_rooms": "Roomie Remote",
        "roomie_press_button": "Roomie Remote",
    }


def test_allowlisted_provider_registers_alone():
    policy = ProviderPolicy(MODE_ALLOWLIST, frozenset({"com.vtmikel.autolights"}))
    manager = ExternalToolManager(logger=Mock(), policy_supplier=lambda: policy)
    entries = _build(manager, [AUTOLIGHTS, ROOMIE])
    assert set(entries) == {"autolights_list_zones", "autolights_update_zone"}
    assert [m.display_name for m in manager.blocked] == ["Roomie Remote"]
    assert manager.policy_summary() == (
        "Plugin-provided tools: only Auto Lights allowed (Roomie Remote blocked)"
    )


def test_empty_allowlist_exposes_nothing():
    policy = ProviderPolicy(MODE_ALLOWLIST, frozenset())
    manager = ExternalToolManager(logger=Mock(), policy_supplier=lambda: policy)
    assert _build(manager, [AUTOLIGHTS, ROOMIE]) == {}
    assert len(manager.blocked) == 2


def test_blocked_provider_does_not_claim_prefix():
    # first in discovery order, so it would win the prefix if not filtered first
    blocked_first = make_provider("com.example.blocked", "shared", tools=[make_tool("one")])
    allowed_second = make_provider("com.example.allowed", "shared", tools=[make_tool("two")])
    policy = ProviderPolicy(MODE_BLOCKLIST, frozenset({"com.example.blocked"}))
    logger = Mock()
    manager = ExternalToolManager(logger=logger, policy_supplier=lambda: policy)
    entries = _build(manager, [blocked_first, allowed_second])
    assert set(entries) == {"shared_two"}
    assert manager.provider_ids() == ["com.example.allowed"]
    logger.error.assert_not_called()


def test_policy_supplier_failure_falls_back_to_all():
    def broken():
        raise RuntimeError("boom")

    logger = Mock()
    manager = ExternalToolManager(logger=logger, policy_supplier=broken)
    entries = _build(manager, [AUTOLIGHTS])
    assert "autolights_list_zones" in entries
    assert logger.error.called


# ----------------------------------------------------------------------
# MCPHandler integration


def test_policy_change_and_refresh_adds_and_removes_tools():
    state = {"policy": ProviderPolicy()}
    manager = ExternalToolManager(logger=Mock(), policy_supplier=lambda: state["policy"])
    with patch.object(manager_module, "discover_manifests", return_value=[AUTOLIGHTS, ROOMIE]):
        handler = make_handler(external_tool_manager=manager)
        assert "roomie_press_button" in handler._tools

        state["policy"] = ProviderPolicy(MODE_BLOCKLIST, frozenset({"com.vtmikel.roomie"}))
        assert handler.refresh_external_tools() is True
        assert "roomie_press_button" not in handler._tools
        assert "roomie_list_rooms" not in handler._tools
        assert "autolights_update_zone" in handler._tools

        state["policy"] = ProviderPolicy()
        handler.refresh_external_tools()
        assert "roomie_press_button" in handler._tools


def test_tools_call_on_blocked_tool_returns_config_message():
    policy = ProviderPolicy(MODE_BLOCKLIST, frozenset({"com.vtmikel.roomie"}))
    manager = ExternalToolManager(logger=Mock(), policy_supplier=lambda: policy)
    with patch.object(manager_module, "discover_manifests", return_value=[AUTOLIGHTS, ROOMIE]):
        handler = make_handler(external_tool_manager=manager)

    reply = handler._handle_tools_call(7, {"name": "roomie_press_button", "arguments": {}})
    assert reply["error"]["code"] == -32602
    assert reply["error"]["message"] == (
        "Tool 'roomie_press_button' is provided by Roomie Remote, which is blocked "
        "in the MCP Advanced Tools plugin config (\"Plugins that may provide MCP tools\")."
    )

    unknown = handler._handle_tools_call(8, {"name": "nope_tool", "arguments": {}})
    assert unknown["error"]["message"] == "Unknown tool: nope_tool"


def test_tools_list_installed_plugin_check_is_throttled():
    clock = {"now": 1000.0}
    state = {"new_plugin": False, "manifests": []}
    checks = []

    def scan():
        checks.append(clock["now"])
        return state["new_plugin"]

    manager = ExternalToolManager(logger=Mock())
    with patch.object(
        manager_module, "discover_manifests", side_effect=lambda logger=None: state["manifests"]
    ) as discover:
        handler = make_handler(
            external_tool_manager=manager,
            provider_scan_supplier=scan,
            clock=lambda: clock["now"],
        )
        startup_scans = discover.call_count

        handler._handle_tools_list(1, {})
        assert len(checks) == 1
        assert discover.call_count == startup_scans  # nothing new -> no rescan

        clock["now"] += 30
        handler._handle_tools_list(2, {})
        assert len(checks) == 1  # throttled

        clock["now"] += 31
        state["new_plugin"] = True
        state["manifests"] = [AUTOLIGHTS]
        listed = handler._handle_tools_list(3, {})
        assert len(checks) == 2
        assert discover.call_count == startup_scans + 1
        names = [t["name"] for t in listed["result"]["tools"]]
        assert "autolights_list_zones" in names


def test_tools_list_scan_failure_is_contained():
    def scan():
        raise RuntimeError("indigo unavailable")

    manager = ExternalToolManager(logger=Mock())
    with patch.object(manager_module, "discover_manifests", return_value=[]):
        handler = make_handler(external_tool_manager=manager, provider_scan_supplier=scan)
        listed = handler._handle_tools_list(1, {})
    assert "result" in listed


def _registered_info_lines(logger):
    return [
        c.args[0]
        for c in logger.info.call_args_list
        if "plugin-provided tool" in c.args[0]
    ]


def test_refresh_logs_summary_only_when_set_changes():
    logger = Mock()
    state = {"policy": ProviderPolicy()}
    manager = ExternalToolManager(logger=logger, policy_supplier=lambda: state["policy"])
    with patch.object(manager_module, "discover_manifests", return_value=[AUTOLIGHTS, ROOMIE]):
        handler = make_handler(external_tool_manager=manager, logger=logger)
        assert len(_registered_info_lines(logger)) == 1  # startup

        handler.refresh_external_tools()  # broadcast, unchanged
        assert len(_registered_info_lines(logger)) == 1

        handler.refresh_external_tools(announce=True)  # menu rescan
        assert len(_registered_info_lines(logger)) == 2

        state["policy"] = ProviderPolicy(MODE_BLOCKLIST, frozenset({"com.vtmikel.roomie"}))
        handler.refresh_external_tools()  # changed
        lines = _registered_info_lines(logger)
        assert len(lines) == 3
        assert lines[-1] == (
            "🔌 2 plugin-provided tools registered "
            "(providers: Auto Lights; blocked by config: Roomie Remote)"
        )

        handler.refresh_external_tools(announce=False)  # prefs path logs its own line
        assert len(_registered_info_lines(logger)) == 3


# ----------------------------------------------------------------------
# plugin.py wiring (loaded with a fake indigo module)


@pytest.fixture(scope="module")
def plugin_module():
    class FakePluginBase:
        pass

    fake = types.ModuleType("indigo")
    fake.PluginBase = FakePluginBase
    fake.server = Mock()
    # Annotations such as indigo.Dict / indigo.Device are evaluated at def time
    fake.__getattr__ = lambda name: type(name, (), {})

    spec = importlib.util.spec_from_file_location(
        "mcp_server_plugin_under_test", plugin_path / "plugin.py"
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


class FakePlugin:
    def __init__(self, plugin_id, name, enabled=True):
        self.pluginId = plugin_id
        self.pluginDisplayName = name
        self._enabled = enabled

    def isEnabled(self):
        return self._enabled


def make_plugin(plugin_module, installed, allowlist=(), mcp_handler=None):
    plugin_module.indigo.server = Mock()
    plugin_module.indigo.server.getPluginList.side_effect = lambda includeDisabled=True: list(
        installed
    )
    plugin = plugin_module.Plugin.__new__(plugin_module.Plugin)
    plugin.logger = Mock()
    plugin.mcp_handler = mcp_handler
    plugin.external_tool_policy = ProviderPolicy()
    plugin.external_tool_allowlist_ids = list(allowlist)
    plugin._subscribed_provider_ids = set()
    return plugin


def test_allowlist_constant_is_gone(plugin_module):
    assert not hasattr(plugin_module.Plugin, "EXTERNAL_TOOL_PROVIDER_ALLOWLIST")


def test_subscriptions_cover_installed_and_allowlist_without_duplicates(plugin_module):
    installed = [
        FakePlugin("com.vtmikel.autolights", "Auto Lights"),
        FakePlugin("com.vtmikel.roomie", "Roomie Remote", enabled=False),
        FakePlugin(SELF_ID, "MCP Advanced Tools"),
    ]
    plugin = make_plugin(plugin_module, installed, allowlist=["com.example.future"])
    server = plugin_module.indigo.server

    first = plugin._subscribe_to_provider_broadcasts()
    assert first == {"com.vtmikel.autolights", "com.vtmikel.roomie", "com.example.future"}
    subscribed = sorted(c.args[0] for c in server.subscribeToBroadcast.call_args_list)
    assert subscribed == sorted(first)
    for call in server.subscribeToBroadcast.call_args_list:
        assert call.args[1:] == ("mcp_tools_updated", "external_tools_updated_broadcast")

    # a rescan subscribes nothing again
    assert plugin._subscribe_to_provider_broadcasts() == set()
    assert plugin._check_for_new_provider_plugins() is False
    assert server.subscribeToBroadcast.call_count == 3

    # a plugin installed after startup is picked up once
    installed.append(FakePlugin("com.example.new", "New Plugin"))
    assert plugin._check_for_new_provider_plugins() is True
    assert server.subscribeToBroadcast.call_count == 4
    assert plugin._check_for_new_provider_plugins() is False


def test_failed_subscription_is_retried(plugin_module):
    plugin = make_plugin(plugin_module, [FakePlugin("com.a", "A")])
    server = plugin_module.indigo.server
    server.subscribeToBroadcast.side_effect = RuntimeError("busy")
    assert plugin._subscribe_to_provider_broadcasts() == set()
    assert plugin.logger.warning.called
    server.subscribeToBroadcast.side_effect = None
    assert plugin._subscribe_to_provider_broadcasts() == {"com.a"}


def test_external_tool_plugin_list_method(plugin_module):
    installed = [
        FakePlugin("com.vtmikel.roomie", "Roomie Remote"),
        FakePlugin(SELF_ID, "MCP Advanced Tools"),
        FakePlugin("com.vtmikel.dometic", "Dometic CFX", enabled=False),
        FakePlugin("com.vtmikel.autolights", "Auto Lights"),
    ]
    plugin = make_plugin(plugin_module, installed)
    values = {
        "external_tool_allowlist": FakeIndigoList(["com.example.removed"]),
        "external_tool_blocklist": FakeIndigoList(["com.vtmikel.roomie"]),
    }
    with patch.object(plugin_module, "discover_manifests", return_value=[AUTOLIGHTS, ROOMIE]):
        options = plugin.external_tool_plugin_list("", values, "", 0)
    assert options == [
        ("com.vtmikel.autolights", "Auto Lights — MCP tools: 2"),
        ("com.vtmikel.dometic", "Dometic CFX (disabled)"),
        ("com.vtmikel.roomie", "Roomie Remote — MCP tools: 2"),
        ("com.example.removed", "com.example.removed (not installed)"),
    ]


def test_apply_policy_swaps_registry_and_logs_result(plugin_module):
    holder = {}
    manager = ExternalToolManager(
        logger=Mock(), policy_supplier=lambda: holder["plugin"].external_tool_policy
    )
    plugin = make_plugin(
        plugin_module,
        [FakePlugin("com.vtmikel.autolights", "Auto Lights"), FakePlugin("com.vtmikel.roomie", "Roomie Remote")],
    )
    holder["plugin"] = plugin
    with patch.object(manager_module, "discover_manifests", return_value=[AUTOLIGHTS, ROOMIE]):
        plugin.mcp_handler = make_handler(external_tool_manager=manager)
        assert "roomie_list_rooms" in plugin.mcp_handler._tools

        plugin.external_tool_policy = ProviderPolicy(
            MODE_ALLOWLIST, frozenset({"com.vtmikel.autolights"})
        )
        plugin._apply_external_tool_policy()

    assert "roomie_list_rooms" not in plugin.mcp_handler._tools
    assert "autolights_list_zones" in plugin.mcp_handler._tools
    plugin.logger.info.assert_called_with(
        "Plugin-provided tools: only Auto Lights allowed (Roomie Remote blocked)"
    )
    reply = plugin.mcp_handler._handle_tools_call(
        1, {"name": "roomie_list_rooms", "arguments": {}}
    )
    assert "blocked in the MCP Advanced Tools plugin config" in reply["error"]["message"]
    assert json.dumps(reply)  # serializable


def test_retired_influxdb_prefs_are_removed(plugin_module):
    plugin = make_plugin(plugin_module, [])
    plugin.pluginPrefs = {
        "openai_api_key": "k",
        "enable_influxdb": True,
        "influx_url": "https://influx.example.com",
        "influx_password": "secret-token",
        "influx_database": "indigo",
    }

    plugin._drop_retired_prefs()

    assert plugin.pluginPrefs == {"openai_api_key": "k"}
    plugin_module.indigo.server.savePluginPrefs.assert_called_once()
    assert plugin.logger.info.called


def test_no_retired_prefs_means_no_save(plugin_module):
    plugin = make_plugin(plugin_module, [])
    plugin.pluginPrefs = {"openai_api_key": "k"}

    plugin._drop_retired_prefs()

    assert plugin.pluginPrefs == {"openai_api_key": "k"}
    plugin_module.indigo.server.savePluginPrefs.assert_not_called()
