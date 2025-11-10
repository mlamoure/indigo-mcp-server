#!/usr/bin/env python3
"""
Capture production MCP server responses as test fixtures.

This script queries the production Indigo MCP server and saves responses
as JSON fixtures that can be used for regression testing.
"""

import json
import os
import sys
from pathlib import Path

# Add plugin to path
plugin_path = Path(__file__).parent.parent / "MCP Server.indigoPlugin/Contents/Server Plugin"
sys.path.insert(0, str(plugin_path))

from mcp_server.adapters.indigo_data_provider import IndigoDataProvider
from mcp_server.handlers.list_handlers import ListHandlers
from mcp_server.tools.search_entities import SearchEntitiesHandler
from mcp_server.common.vector_store.main import VectorStore
from mcp_server.common.json_encoder import safe_json_dumps
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Fixture output directory
FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURES_DIR.mkdir(exist_ok=True)


def capture_fixture(name: str, data: dict):
    """Save a fixture to JSON file."""
    filepath = FIXTURES_DIR / f"{name}.json"
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    logger.info(f"✅ Captured {name}: {filepath}")


def main():
    """Capture production fixtures from Indigo MCP server."""
    logger.info("🔍 Capturing production MCP server responses...")
    logger.info("")

    try:
        # Initialize data provider (connects to real Indigo)
        data_provider = IndigoDataProvider()
        logger.info("✅ Connected to Indigo server")

        # Initialize handlers
        list_handlers = ListHandlers(data_provider=data_provider, logger=logger)

        # Capture list_devices response (first 10 for manageable fixture size)
        logger.info("\n📋 Capturing list_devices response...")
        devices_result = list_handlers.list_all_devices(limit=10, offset=0)
        capture_fixture("list_devices_response", devices_result)

        # Capture list_variables response (first 10)
        logger.info("\n📋 Capturing list_variables response...")
        variables_result = list_handlers.list_all_variables(limit=10, offset=0)
        capture_fixture("list_variables_response", variables_result)

        # Capture list_action_groups response (first 10)
        logger.info("\n📋 Capturing list_action_groups response...")
        actions_result = list_handlers.list_all_action_groups(limit=10, offset=0)
        capture_fixture("list_action_groups_response", actions_result)

        # Capture list_variable_folders response
        logger.info("\n📋 Capturing list_variable_folders response...")
        folders_result = list_handlers.list_variable_folders()
        capture_fixture("list_variable_folders_response", folders_result)

        # Capture get_devices_by_state response (on devices)
        logger.info("\n📋 Capturing get_devices_by_state response...")
        state_result = list_handlers.get_devices_by_state(
            state_conditions={"onState": True},
            limit=5,
            offset=0
        )
        capture_fixture("get_devices_by_state_response", state_result)

        # Capture a specific device if available
        if devices_result.get("devices"):
            device_id = devices_result["devices"][0]["id"]
            logger.info(f"\n📋 Capturing get_device_by_id response (ID: {device_id})...")
            device = data_provider.get_device(device_id)
            if device:
                capture_fixture("get_device_by_id_response", device)

        # Capture a specific variable if available
        if variables_result.get("variables"):
            variable_id = variables_result["variables"][0]["id"]
            logger.info(f"\n📋 Capturing get_variable_by_id response (ID: {variable_id})...")
            variable = data_provider.get_variable(variable_id)
            if variable:
                capture_fixture("get_variable_by_id_response", variable)

        # Capture a specific action group if available
        if actions_result.get("action_groups"):
            action_id = actions_result["action_groups"][0]["id"]
            logger.info(f"\n📋 Capturing get_action_group_by_id response (ID: {action_id})...")
            action = data_provider.get_action_group(action_id)
            if action:
                capture_fixture("get_action_group_by_id_response", action)

        logger.info("\n" + "="*60)
        logger.info("✅ All fixtures captured successfully!")
        logger.info(f"📁 Fixtures saved to: {FIXTURES_DIR}")
        logger.info("="*60)

    except Exception as e:
        logger.error(f"\n❌ Error capturing fixtures: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
