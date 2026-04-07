"""
Test configuration — import helpers for event system tests.

The plugin has heavy dependencies (lancedb, openai, tiktoken, pydantic, etc.)
that cascade from mcp_server/__init__.py. The events module uses only stdlib,
so we bypass the parent package init by loading modules directly.
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Base path for plugin source
PLUGIN_SRC = Path(__file__).parent.parent / "MCP Server.indigoPlugin/Contents/Server Plugin"


def _load_module_from_file(name: str, file_path: Path):
    """Load a Python module directly from a file path, bypassing package __init__."""
    spec = importlib.util.spec_from_file_location(name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _setup_events_modules():
    """
    Load the events subpackage and its dependencies without triggering
    the full mcp_server package init chain.
    """
    base = PLUGIN_SRC / "mcp_server"

    # 1. Load standalone dependencies first (these only use stdlib)
    _load_module_from_file(
        "mcp_server.common.state_filter",
        base / "common" / "state_filter.py",
    )
    _load_module_from_file(
        "mcp_server.tools.base_handler",
        base / "tools" / "base_handler.py",
    )

    # 2. Create minimal package stubs so relative imports work
    # (the events modules use `from ..common.state_filter import ...`)
    for pkg_name in [
        "mcp_server",
        "mcp_server.common",
        "mcp_server.tools",
        "mcp_server.events",
    ]:
        if pkg_name not in sys.modules:
            mod = MagicMock()
            mod.__path__ = [str(base / pkg_name.replace("mcp_server.", "").replace("mcp_server", ""))]
            mod.__spec__ = None
            mod.__package__ = pkg_name
            sys.modules[pkg_name] = mod

    # Attach the real modules to their parent stubs
    sys.modules["mcp_server.common"].state_filter = sys.modules["mcp_server.common.state_filter"]
    sys.modules["mcp_server.tools"].base_handler = sys.modules["mcp_server.tools.base_handler"]

    # 3. Load events modules in dependency order
    events_dir = base / "events"
    _load_module_from_file("mcp_server.events.event_model", events_dir / "event_model.py")
    _load_module_from_file("mcp_server.events.subscription_model", events_dir / "subscription_model.py")
    _load_module_from_file("mcp_server.events.dwell_timer", events_dir / "dwell_timer.py")
    _load_module_from_file("mcp_server.events.subscription_manager", events_dir / "subscription_manager.py")
    _load_module_from_file("mcp_server.events.webhook_dispatcher", events_dir / "webhook_dispatcher.py")
    _load_module_from_file("mcp_server.events.subscription_handler", events_dir / "subscription_handler.py")

    # 4. Load events __init__
    _load_module_from_file("mcp_server.events", events_dir / "__init__.py")


_setup_events_modules()
