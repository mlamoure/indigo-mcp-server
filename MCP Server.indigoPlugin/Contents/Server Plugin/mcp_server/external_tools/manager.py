"""
Registry management for plugin-provided MCP tools.

Turns discovered manifests into tool-registry entries shaped exactly like
the static ones ({description, inputSchema, function}), with the exposed
name ALWAYS "{prefix}_{name}" — a bare provider tool name never reaches an
AI client. Prefixes are enforced first-come across providers so two plugins
can never fight over a namespace.
"""

import logging
from typing import Callable, Dict, List, Optional

from ..common.json_encoder import safe_json_dumps
from .discovery import discover_manifests
from .external_tool_handler import ExternalToolHandler
from .manifest import ExternalTool, ProviderManifest


class ExternalToolManager:
    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        write_gate_supplier: Optional[Callable[[], bool]] = None,
    ):
        self.logger = logger or logging.getLogger("Plugin")
        # Checked per call so a prefs change applies without a restart
        self.write_gate_supplier = write_gate_supplier or (lambda: True)
        self.manifests: List[ProviderManifest] = []

    def provider_ids(self) -> List[str]:
        return [m.plugin_id for m in self.manifests]

    def rescan_and_build(self, handler: ExternalToolHandler) -> Dict[str, dict]:
        """
        Re-discover manifests and build registry entries for every tool.
        Returns {exposed_name: {description, inputSchema, function, write, provider}}.
        """
        manifests = discover_manifests(self.logger)

        # First-come prefix uniqueness: a later manifest claiming a taken
        # prefix is rejected whole, loudly
        accepted: List[ProviderManifest] = []
        prefix_owner: Dict[str, str] = {}
        for manifest in manifests:
            owner = prefix_owner.get(manifest.prefix)
            if owner is not None and owner != manifest.plugin_id:
                self.logger.error(
                    f"❌ MCP tool prefix '{manifest.prefix}' is already claimed by "
                    f"{owner}; rejecting the manifest from {manifest.plugin_id}"
                )
                continue
            prefix_owner[manifest.prefix] = manifest.plugin_id
            accepted.append(manifest)
        self.manifests = accepted

        entries: Dict[str, dict] = {}
        for manifest in accepted:
            for tool in manifest.tools:
                exposed = f"{manifest.prefix}_{tool.name}"
                entries[exposed] = {
                    "description": (
                        f"{tool.description} [provided by {manifest.display_name} plugin]"
                    ),
                    "inputSchema": tool.input_schema,
                    "function": self._make_function(handler, manifest, tool),
                    "external_provider": manifest.plugin_id,
                    "write": tool.write,
                }
        return entries

    def _make_function(
        self,
        handler: ExternalToolHandler,
        manifest: ProviderManifest,
        tool: ExternalTool,
    ) -> Callable[..., str]:
        def fn(**kwargs) -> str:
            # Unlike static wrappers, **kwargs cannot raise TypeError on an
            # unknown argument — the provider's own validation is the
            # authority, and its error comes back in-band for the model to
            # self-correct on
            if tool.write and not self.write_gate_supplier():
                return safe_json_dumps(
                    {
                        "success": False,
                        "error": (
                            "Plugin-provided write tools are disabled — enable "
                            "'Allow plugin-provided tools to make changes' in the "
                            "MCP Server plugin config"
                        ),
                    }
                )
            return safe_json_dumps(
                handler.invoke(
                    provider_id=manifest.plugin_id,
                    action_id=tool.action_id,
                    bare_name=tool.name,
                    display_name=manifest.display_name,
                    arguments=kwargs,
                    timeout_seconds=tool.timeout_seconds,
                    write=tool.write,
                )
            )

        return fn
