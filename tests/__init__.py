"""
Test package for MCP Server plugin.
"""

import sys
import os

# Add the plugin's Server Plugin directory to the Python path
plugin_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "MCP Server.indigoPlugin",
    "Contents",
    "Server Plugin"
)
if plugin_path not in sys.path:
    sys.path.insert(0, plugin_path)