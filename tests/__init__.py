"""
Test package for MCP Server plugin.
"""

import sys
import os
from pathlib import Path

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    # Look for .env file in project root
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✓ Loaded environment variables from {env_path}")
    else:
        print(f"⚠ No .env file found at {env_path}")
except ImportError:
    print("⚠ python-dotenv not available, skipping .env file loading")

# Add the plugin's Server Plugin directory to the Python path
plugin_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "MCP Server.indigoPlugin",
    "Contents",
    "Server Plugin"
)
if plugin_path not in sys.path:
    sys.path.insert(0, plugin_path)