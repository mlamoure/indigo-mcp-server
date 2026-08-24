"""
Manifest parsing and validation for plugin-provided MCP tools.

Pure stdlib — no indigo import — so it is directly unit-testable. The
manifest travels as a JSON file on disk (never through indigo.Dict, whose
key/None restrictions would corrupt JSON Schema), and this module is the
single authority on what a valid manifest v1 looks like.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

MANIFEST_VERSION = 1
MANIFEST_FILENAME = "mcp-manifest.json"
DEFAULT_INVOKE_ACTION_ID = "mcp_tool_invoke"

TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
PREFIX_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")

DEFAULT_TIMEOUT_SECONDS = 30
MIN_TIMEOUT_SECONDS = 5
MAX_TIMEOUT_SECONDS = 120


class ManifestError(Exception):
    """A manifest is malformed or violates the provider contract."""


@dataclass
class ExternalTool:
    name: str
    description: str
    input_schema: Dict[str, Any]
    write: bool
    timeout_seconds: int
    action_id: str


@dataclass
class ProviderManifest:
    plugin_id: str
    display_name: str
    prefix: str
    tools: List[ExternalTool] = field(default_factory=list)


def derive_prefix(plugin_id: str) -> str:
    """
    Default tool prefix from a plugin id: last dot-segment, snake-cased.
    e.g. com.vtmikel.autolights -> autolights,
         com.foo.example-http-responder -> example_http_responder
    """
    segment = plugin_id.rsplit(".", 1)[-1].lower()
    segment = re.sub(r"[^a-z0-9_]", "_", segment)
    segment = re.sub(r"^[^a-z]+", "", segment)  # must start with a letter
    segment = re.sub(r"_+", "_", segment).strip("_") or "plugin"
    return segment[:32]  # keep within the PREFIX_RE length bound


def parse_manifest(text: str, expected_plugin_id: str) -> ProviderManifest:
    """
    Parse and validate a manifest file's contents.

    Args:
        text: Raw file contents.
        expected_plugin_id: The pluginId of the bundle the file was found in;
            the manifest's declared provider id must match (spoof guard).

    Raises:
        ManifestError: on any spec violation.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ManifestError(f"not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ManifestError("manifest root must be a JSON object")

    version = data.get("manifest_version")
    if version != MANIFEST_VERSION:
        raise ManifestError(
            f"unsupported manifest_version {version!r} (this server speaks v{MANIFEST_VERSION})"
        )

    provider = data.get("provider")
    if not isinstance(provider, dict) or not provider.get("plugin_id"):
        raise ManifestError("provider.plugin_id is required")
    plugin_id = provider["plugin_id"]
    if plugin_id != expected_plugin_id:
        raise ManifestError(
            f"provider.plugin_id {plugin_id!r} does not match the bundle it was "
            f"found in ({expected_plugin_id!r})"
        )
    display_name = provider.get("display_name") or plugin_id

    # The exposed prefix is always enforced here, never trusted verbatim:
    # a declared tool_prefix must pass the charset check, otherwise the
    # manifest is rejected (a silently substituted prefix would surprise
    # the provider author).
    declared_prefix = data.get("tool_prefix")
    if declared_prefix is not None:
        if not isinstance(declared_prefix, str) or not PREFIX_RE.match(declared_prefix):
            raise ManifestError(
                f"tool_prefix {declared_prefix!r} is invalid (must match {PREFIX_RE.pattern})"
            )
        prefix = declared_prefix
    else:
        prefix = derive_prefix(plugin_id)

    default_action_id = data.get("invoke_action_id", DEFAULT_INVOKE_ACTION_ID)
    if not isinstance(default_action_id, str) or not default_action_id:
        raise ManifestError("invoke_action_id must be a non-empty string")

    raw_tools = data.get("tools")
    if not isinstance(raw_tools, list) or not raw_tools:
        raise ManifestError("tools must be a non-empty array")

    tools: List[ExternalTool] = []
    seen_names = set()
    for i, raw in enumerate(raw_tools):
        if not isinstance(raw, dict):
            raise ManifestError(f"tools[{i}] must be an object")
        name = raw.get("name")
        if not isinstance(name, str) or not TOOL_NAME_RE.match(name):
            raise ManifestError(
                f"tools[{i}].name {name!r} is invalid (must match {TOOL_NAME_RE.pattern})"
            )
        if name in seen_names:
            raise ManifestError(f"duplicate tool name {name!r}")
        seen_names.add(name)

        description = raw.get("description")
        if not isinstance(description, str) or not description.strip():
            raise ManifestError(f"tools[{i}].description is required")

        input_schema = raw.get("inputSchema")
        if not isinstance(input_schema, dict) or input_schema.get("type") != "object":
            raise ManifestError(
                f"tools[{i}].inputSchema must be a JSON Schema object with type 'object'"
            )

        # write defaults to True: an undeclared tool is treated as a write so
        # the write gate fails safe
        write = raw.get("write", True)
        if not isinstance(write, bool):
            raise ManifestError(f"tools[{i}].write must be a boolean")

        timeout = raw.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
        if not isinstance(timeout, int) or isinstance(timeout, bool):
            raise ManifestError(f"tools[{i}].timeout_seconds must be an integer")
        timeout = max(MIN_TIMEOUT_SECONDS, min(MAX_TIMEOUT_SECONDS, timeout))

        action_id = raw.get("action_id", default_action_id)
        if not isinstance(action_id, str) or not action_id:
            raise ManifestError(f"tools[{i}].action_id must be a non-empty string")

        tools.append(
            ExternalTool(
                name=name,
                description=description.strip(),
                input_schema=input_schema,
                write=write,
                timeout_seconds=timeout,
                action_id=action_id,
            )
        )

    return ProviderManifest(
        plugin_id=plugin_id,
        display_name=display_name,
        prefix=prefix,
        tools=tools,
    )
