"""
Which installed plugins may provide MCP tools.

Pure stdlib — no indigo import — so it is directly unit-testable. The plugin
config stores a mode plus two separate plugin-id lists (one per list mode);
ProviderPolicy.from_prefs is the single place that reads those three prefs,
and the helpers below build the config dialog's plugin list and the set of
plugin ids MCP Advanced Tools subscribes to for 'mcp_tools_updated' broadcasts.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

MODE_ALL = "all"
MODE_ALLOWLIST = "allowlist"
MODE_BLOCKLIST = "blocklist"
# Values must not contain one another: ConfigUI's visibleBindingValue
# matches by substring
MODES = (MODE_ALL, MODE_ALLOWLIST, MODE_BLOCKLIST)

PREF_MODE = "external_tool_policy"
PREF_ALLOWLIST = "external_tool_allowlist"
PREF_BLOCKLIST = "external_tool_blocklist"

# Unknown mode values already warned about (log once per value per process)
_warned_modes = set()


def normalize_plugin_ids(value: Any) -> List[str]:
    """
    Turn a stored list pref into a plain list of plugin ids.

    A ConfigUI list field comes back as an indigo.List of strings; a missing
    pref is None. A bare string is split on commas (plugin ids never contain
    one). Blank entries are dropped and order is kept, without duplicates.
    """
    if value is None:
        return []
    if isinstance(value, str):
        items: Iterable[Any] = value.split(",")
    else:
        try:
            items = list(value)
        except TypeError:
            items = [value]
    ids: List[str] = []
    for item in items:
        plugin_id = str(item).strip()
        if plugin_id and plugin_id not in ids:
            ids.append(plugin_id)
    return ids


@dataclass(frozen=True)
class ProviderPolicy:
    """The provider policy in effect: a mode and the list for that mode only."""

    mode: str = MODE_ALL
    plugin_ids: frozenset = frozenset()

    def allows(self, plugin_id: str) -> bool:
        if self.mode == MODE_ALLOWLIST:
            return plugin_id in self.plugin_ids
        if self.mode == MODE_BLOCKLIST:
            return plugin_id not in self.plugin_ids
        return True

    @classmethod
    def from_prefs(
        cls, prefs: Optional[Mapping[str, Any]], logger: Optional[logging.Logger] = None
    ) -> "ProviderPolicy":
        """
        Build the policy from plugin prefs (or a ConfigUI valuesDict).

        Missing prefs (an upgrade from a release without the setting) give
        "all", today's behavior. An unknown mode also falls back to "all",
        with one WARNING per value.
        """
        prefs = prefs or {}
        raw_mode = prefs.get(PREF_MODE)
        mode = str(raw_mode).strip() if raw_mode is not None else ""
        if not mode:
            return cls()
        if mode not in MODES:
            if mode not in _warned_modes:
                _warned_modes.add(mode)
                (logger or logging.getLogger("Plugin")).warning(
                    f"⚠️ Unknown plugin-provided tools setting '{mode}' — "
                    f"allowing all plugins"
                )
            return cls()
        if mode == MODE_ALL:
            return cls()
        list_pref = PREF_ALLOWLIST if mode == MODE_ALLOWLIST else PREF_BLOCKLIST
        return cls(mode=mode, plugin_ids=frozenset(normalize_plugin_ids(prefs.get(list_pref))))


def _join(names: Sequence[str]) -> str:
    return ", ".join(names)


def describe_policy_result(
    policy: ProviderPolicy, allowed_names: Sequence[str], blocked_names: Sequence[str]
) -> str:
    """
    One INFO line describing what a policy does to the tool providers found,
    e.g. "Plugin-provided tools: only Auto Lights allowed (Roomie Remote blocked)".
    """
    prefix = "Plugin-provided tools:"
    if policy.mode == MODE_ALLOWLIST:
        if not policy.plugin_ids:
            return f"{prefix} allowlist is empty — no plugin-provided tools are exposed"
        allowed = _join(allowed_names) or "no plugin that ships tools"
        text = f"{prefix} only {allowed} allowed"
        if blocked_names:
            text += f" ({_join(blocked_names)} blocked)"
        return text
    if policy.mode == MODE_BLOCKLIST:
        if blocked_names:
            text = f"{prefix} {_join(blocked_names)} blocked"
        else:
            text = f"{prefix} the blocklist matches no plugin that ships tools"
        if allowed_names:
            text += f" ({_join(allowed_names)} allowed)"
        return text
    if allowed_names:
        return f"{prefix} all plugins allowed ({_join(allowed_names)})"
    return f"{prefix} all plugins allowed"


# A plugin as the config dialog sees it: (plugin_id, display_name, enabled)
InstalledPlugin = Tuple[str, str, bool]


def build_plugin_list_options(
    installed: Sequence[InstalledPlugin],
    tool_counts: Dict[str, int],
    saved_ids: Iterable[str],
    self_plugin_id: str,
) -> List[Tuple[str, str]]:
    """
    Options for the allowlist/blocklist fields: every installed plugin
    (enabled or disabled) except MCP Advanced Tools itself, sorted by display
    name, then saved ids whose plugin is no longer installed, so a save does
    not silently drop them.

    Labels: "Auto Lights — MCP tools: 18", "Dometic CFX (disabled)",
    "com.example.removed (not installed)".
    """
    rows = []
    seen = set()
    for plugin_id, display_name, enabled in installed:
        if not plugin_id or plugin_id == self_plugin_id or plugin_id in seen:
            continue
        seen.add(plugin_id)
        name = display_name or plugin_id
        label = name
        count = tool_counts.get(plugin_id)
        if count:
            label += f" — MCP tools: {count}"
        if not enabled:
            label += " (disabled)"
        rows.append((name.casefold(), plugin_id, label))
    rows.sort()
    options = [(plugin_id, label) for _, plugin_id, label in rows]

    missing = sorted(
        {pid for pid in saved_ids if pid and pid not in seen and pid != self_plugin_id}
    )
    options.extend((pid, f"{pid} (not installed)") for pid in missing)
    return options


def provider_subscription_ids(
    installed_ids: Iterable[str],
    allowlist_ids: Iterable[str],
    self_plugin_id: str,
) -> set:
    """
    Plugin ids to subscribe to for 'mcp_tools_updated': every installed
    plugin, plus every allowlisted id even when that plugin is not installed
    (subscriptions survive the broadcaster being absent). A broadcast from a
    blocked plugin is harmless — the rescan filters it out again.
    """
    ids = {pid for pid in installed_ids if pid}
    ids.update(pid for pid in allowlist_ids if pid)
    ids.discard(self_plugin_id)
    return ids
