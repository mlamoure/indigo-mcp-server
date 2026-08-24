"""Tests for external_tools.manifest parsing and prefix derivation."""

import json
import sys
from pathlib import Path

import pytest

plugin_path = Path(__file__).parent.parent / "MCP Server.indigoPlugin/Contents/Server Plugin"
sys.path.insert(0, str(plugin_path))

from mcp_server.external_tools.manifest import (
    ManifestError,
    derive_prefix,
    parse_manifest,
)

PLUGIN_ID = "com.example.myplugin"


def make_manifest(**overrides):
    manifest = {
        "manifest_version": 1,
        "provider": {"plugin_id": PLUGIN_ID, "display_name": "My Plugin"},
        "tools": [
            {
                "name": "get_status",
                "description": "Return status.",
                "write": False,
                "inputSchema": {"type": "object", "properties": {}},
            }
        ],
    }
    manifest.update(overrides)
    return manifest


def parse(manifest, plugin_id=PLUGIN_ID):
    return parse_manifest(json.dumps(manifest), expected_plugin_id=plugin_id)


def test_happy_path():
    result = parse(make_manifest())
    assert result.plugin_id == PLUGIN_ID
    assert result.display_name == "My Plugin"
    assert result.prefix == "myplugin"  # derived from plugin id
    tool = result.tools[0]
    assert tool.name == "get_status"
    assert tool.write is False
    assert tool.timeout_seconds == 30  # default
    assert tool.action_id == "mcp_tool_invoke"  # default


def test_bad_version_rejected():
    with pytest.raises(ManifestError, match="manifest_version"):
        parse(make_manifest(manifest_version=2))


def test_plugin_id_mismatch_rejected():
    with pytest.raises(ManifestError, match="does not match"):
        parse(make_manifest(), plugin_id="com.other.plugin")


def test_bad_tool_name_rejected():
    manifest = make_manifest()
    manifest["tools"][0]["name"] = "Get-Status"
    with pytest.raises(ManifestError, match="name"):
        parse(manifest)


def test_duplicate_tool_name_rejected():
    manifest = make_manifest()
    manifest["tools"].append(dict(manifest["tools"][0]))
    with pytest.raises(ManifestError, match="duplicate"):
        parse(manifest)


def test_input_schema_must_be_object_schema():
    manifest = make_manifest()
    manifest["tools"][0]["inputSchema"] = {"type": "array"}
    with pytest.raises(ManifestError, match="inputSchema"):
        parse(manifest)


def test_write_defaults_to_true():
    manifest = make_manifest()
    del manifest["tools"][0]["write"]
    assert parse(manifest).tools[0].write is True


def test_timeout_clamped():
    manifest = make_manifest()
    manifest["tools"][0]["timeout_seconds"] = 999
    assert parse(manifest).tools[0].timeout_seconds == 120
    manifest["tools"][0]["timeout_seconds"] = 1
    assert parse(manifest).tools[0].timeout_seconds == 5


def test_invalid_json_rejected():
    with pytest.raises(ManifestError, match="not valid JSON"):
        parse_manifest("{nope", expected_plugin_id=PLUGIN_ID)


def test_empty_tools_rejected():
    with pytest.raises(ManifestError, match="tools"):
        parse(make_manifest(tools=[]))


def test_prefix_derivation():
    assert derive_prefix("com.vtmikel.autolights") == "autolights"
    assert derive_prefix("com.foo.example-http-responder") == "example_http_responder"
    assert derive_prefix("com.foo.99bottles") == "bottles"
    assert derive_prefix("com.foo.___") == "plugin"


def test_prefix_override_validated():
    result = parse(make_manifest(tool_prefix="mytools"))
    assert result.prefix == "mytools"
    with pytest.raises(ManifestError, match="tool_prefix"):
        parse(make_manifest(tool_prefix="My Tools"))
    with pytest.raises(ManifestError, match="tool_prefix"):
        parse(make_manifest(tool_prefix="9lives"))
