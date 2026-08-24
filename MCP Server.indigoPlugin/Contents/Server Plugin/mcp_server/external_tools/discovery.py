"""
Filesystem discovery of provider manifests.

Scans every installed Indigo plugin bundle (enabled or disabled) for
Contents/Resources/mcp-manifest.json. Discovery is deliberately
filesystem-only — no cross-plugin calls — so it is cheap, produces no log
noise for non-participating plugins, and sees providers that are currently
disabled (their tools then fail at call time with a clean "provider not
running" error, which is more debuggable than silent absence).
"""

import logging
import os
from typing import List, Optional

from .manifest import MANIFEST_FILENAME, ManifestError, ProviderManifest, parse_manifest

try:
    import indigo
except ImportError:
    indigo = None  # unit tests run outside Indigo

# Never serve tools from our own bundle
SELF_PLUGIN_ID = "com.vtmikel.mcp_server"


def manifest_path_for(plugin_folder_path: str) -> str:
    return os.path.join(plugin_folder_path, "Contents", "Resources", MANIFEST_FILENAME)


def discover_manifests(logger: Optional[logging.Logger] = None) -> List[ProviderManifest]:
    """
    Return parsed manifests for every installed plugin that ships one.
    Invalid manifests are skipped with one WARNING naming the file and reason.
    """
    logger = logger or logging.getLogger("Plugin")
    manifests: List[ProviderManifest] = []
    if indigo is None:
        return manifests

    try:
        plugin_list = indigo.server.getPluginList(includeDisabled=True)
    except Exception as e:
        logger.warning(f"⚠️ Could not enumerate installed plugins: {e}")
        return manifests

    for plugin in plugin_list:
        try:
            plugin_id = plugin.pluginId
            folder = plugin.pluginFolderPath
        except Exception:
            continue
        if plugin_id == SELF_PLUGIN_ID or not folder:
            continue

        path = manifest_path_for(folder)
        if not os.path.isfile(path):
            continue

        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            manifests.append(parse_manifest(text, expected_plugin_id=plugin_id))
        except (ManifestError, OSError) as e:
            logger.warning(f"⚠️ Ignoring MCP tool manifest {path}: {e}")

    return manifests
