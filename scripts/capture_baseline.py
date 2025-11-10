#!/usr/bin/env python3
"""
Interactive baseline data capture script for Indigo MCP Server tests.

This script uses the homelab MCP server (via Claude Code) to call production
Indigo tools, displays results, and captures validated baseline data for tests.

Usage:
    This script is designed to be run BY Claude Code, not directly by users.
    Claude Code has access to the homelab MCP server tools and can make the calls.

    The user reviews the results and confirms if they are expected.
    Once confirmed, the baseline data is updated in baseline_data.py.

Flow:
    1. Claude calls a tool via homelab MCP server
    2. Claude displays the results in a formatted, readable way
    3. User confirms: "Are these results expected?"
    4. If yes: Claude updates baseline_data.py with the confirmed data
    5. If no: Claude investigates and retries

Categories:
    - Search & Discovery (search_entities, get_devices_by_type)
    - Direct Lookup (get_device_by_id, get_variable_by_id, etc.)
    - Listing Tools (list_devices, list_variables, list_action_groups)
    - Device State Queries (get_devices_by_state)
    - Plugin Queries (list_plugins)
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional


# This script is a template/guide for Claude Code
# The actual implementation happens through Claude's tool calls

VALIDATION_CATEGORIES = {
    "search": {
        "name": "Search & Discovery Tools",
        "tools": ["search_entities", "get_devices_by_type"],
        "description": "Test semantic search and device type filtering"
    },
    "lookup": {
        "name": "Direct Lookup Tools",
        "tools": ["get_device_by_id", "get_variable_by_id", "get_action_group_by_id"],
        "description": "Test direct entity retrieval by ID"
    },
    "listing": {
        "name": "Listing Tools",
        "tools": ["list_devices", "list_variables", "list_action_groups", "list_variable_folders"],
        "description": "Test complete entity listings"
    },
    "state": {
        "name": "State Query Tools",
        "tools": ["get_devices_by_state"],
        "description": "Test state-based device filtering"
    },
    "plugins": {
        "name": "Plugin Management Tools",
        "tools": ["list_plugins", "get_plugin_by_id", "get_plugin_status"],
        "description": "Test plugin information and management"
    },
    "system": {
        "name": "System Tools",
        "tools": ["query_event_log"],
        "description": "Test system information retrieval"
    }
}


EXAMPLE_SEARCH_QUERIES = [
    "living room lights",
    "bedroom lights",
    "temperature sensors",
    "motion sensors",
    "thermostats",
    "scenes",
    "garage",
    "front door",
    "security",
]


DEVICE_TYPES_TO_TEST = [
    "dimmer",
    "relay",
    "sensor",
    "thermostat",
    "sprinkler",
    "multiio",
    "speedcontrol",
]


def format_search_results(results: Dict[str, Any]) -> str:
    """Format search results for display."""
    lines = []
    lines.append(f"\nQuery: {results.get('query', 'N/A')}")
    lines.append(f"Total Results: {results.get('total_count', 0)}")
    lines.append("\nResults:")

    for category, items in results.get('results', {}).items():
        if items:
            lines.append(f"\n  {category.upper()} ({len(items)}):")
            for item in items[:5]:  # Show first 5
                name = item.get('name', 'Unknown')
                item_id = item.get('id', 'N/A')
                lines.append(f"    - {name} (ID: {item_id})")
            if len(items) > 5:
                lines.append(f"    ... and {len(items) - 5} more")

    return "\n".join(lines)


def format_device_list(devices: List[Dict[str, Any]], device_type: str) -> str:
    """Format device list for display."""
    lines = []
    lines.append(f"\nDevice Type: {device_type}")
    lines.append(f"Total Count: {len(devices)}")

    if devices:
        lines.append("\nSample Devices (first 10):")
        for device in devices[:10]:
            name = device.get('name', 'Unknown')
            device_id = device.get('id', 'N/A')
            on_state = device.get('onState', 'N/A')
            lines.append(f"  - {name} (ID: {device_id}, On: {on_state})")

        if len(devices) > 10:
            lines.append(f"  ... and {len(devices) - 10} more")

        # Extract sample IDs for baseline
        sample_ids = [d['id'] for d in devices[:5] if 'id' in d]
        lines.append(f"\nSample IDs for baseline: {sample_ids}")

    return "\n".join(lines)


def format_entity_list(entities: List[Dict[str, Any]], entity_type: str) -> str:
    """Format generic entity list for display."""
    lines = []
    lines.append(f"\n{entity_type.title()} Count: {len(entities)}")

    if entities:
        lines.append(f"\nSample {entity_type} (first 10):")
        for entity in entities[:10]:
            name = entity.get('name', 'Unknown')
            entity_id = entity.get('id', 'N/A')
            value = entity.get('value', '')
            if value:
                lines.append(f"  - {name} (ID: {entity_id}, Value: {value})")
            else:
                lines.append(f"  - {name} (ID: {entity_id})")

        if len(entities) > 10:
            lines.append(f"  ... and {len(entities) - 10} more")

    return "\n".join(lines)


def format_plugin_list(plugins: List[Dict[str, Any]]) -> str:
    """Format plugin list for display."""
    lines = []
    lines.append(f"\nInstalled Plugins: {len(plugins)}")

    if plugins:
        lines.append("\nPlugins:")
        for plugin in plugins:
            plugin_id = plugin.get('id', 'Unknown')
            name = plugin.get('name', 'Unknown')
            enabled = plugin.get('enabled', False)
            version = plugin.get('version', 'N/A')
            status = "✓ Enabled" if enabled else "✗ Disabled"
            lines.append(f"  - {name} ({plugin_id}) v{version} - {status}")

    return "\n".join(lines)


# Instruction comments for Claude Code:
#
# SEARCH & DISCOVERY VALIDATION:
# --------------------------------
# For each query in EXAMPLE_SEARCH_QUERIES:
#   1. Call: mcp__homelab__Indigo__search_entities(query=query)
#   2. Parse the JSON response
#   3. Display using format_search_results()
#   4. Ask user: "Are these results expected for '{query}'?"
#   5. If yes: Add to SEARCH_QUERIES in baseline_data.py:
#      - expected_min_count: total_count from results
#      - expected_devices: list of top device names
#      - query_timestamp: current ISO8601 timestamp
#
# For each device_type in DEVICE_TYPES_TO_TEST:
#   1. Call: mcp__homelab__Indigo__get_devices_by_type(device_type=device_type)
#   2. Parse the JSON response
#   3. Display using format_device_list()
#   4. Ask user: "Are these results expected for device type '{device_type}'?"
#   5. If yes: Add to DEVICE_TYPES in baseline_data.py:
#      - expected_min_count: len(devices)
#      - sample_device_ids: first 5 device IDs
#
# DIRECT LOOKUP VALIDATION:
# -------------------------
# After getting device/variable/action_group lists:
#   1. Select 3-5 sample IDs from each category
#   2. Call: mcp__homelab__Indigo__get_device_by_id(device_id=id)
#   3. Display the returned device data
#   4. Ask user: "Is this the correct device for ID {id}?"
#   5. If yes: Add ID to SAMPLE_DEVICE_IDS in baseline_data.py
#   6. Repeat for variables and action groups
#
# Test invalid IDs:
#   1. Call with ID 999999999
#   2. Verify it returns an error
#   3. Confirm with user that error handling is correct
#
# LISTING VALIDATION:
# ------------------
# 1. Call: mcp__homelab__Indigo__list_devices()
#    - Display count using format_entity_list()
#    - Ask: "Is this the expected device count?"
#    - Save to EXPECTED_COUNTS["devices"]
#
# 2. Call: mcp__homelab__Indigo__list_variables()
#    - Display count and sample values
#    - Ask: "Is this the expected variable count?"
#    - Save to EXPECTED_COUNTS["variables"]
#
# 3. Call: mcp__homelab__Indigo__list_action_groups()
#    - Display count and sample names
#    - Ask: "Is this the expected action group count?"
#    - Save to EXPECTED_COUNTS["action_groups"]
#
# 4. Call: mcp__homelab__Indigo__list_variable_folders()
#    - Display folders
#    - Note folder IDs for variable creation tests
#
# STATE QUERY VALIDATION:
# ----------------------
# Test various state conditions:
#   1. {"onState": true} - devices that are on
#   2. {"onState": false} - devices that are off
#   3. {"brightnessLevel": {"gt": 50}} - bright devices
#   4. Call: mcp__homelab__Indigo__get_devices_by_state(state_conditions=condition)
#   5. Display results and ask for confirmation
#
# PLUGIN VALIDATION:
# -----------------
# 1. Call: mcp__homelab__Indigo__list_plugins()
#    - Display using format_plugin_list()
#    - Ask: "Are these the expected installed plugins?"
#    - Save to EXPECTED_PLUGINS in baseline_data.py
#
# 2. Test specific plugin lookup:
#    - Call: mcp__homelab__Indigo__get_plugin_by_id(plugin_id="com.vtmikel.mcp_server")
#    - Verify MCP Server plugin is found
#    - Confirm it's enabled and version matches
#
# SYSTEM TOOLS VALIDATION:
# -----------------------
# 1. Call: mcp__homelab__Indigo__query_event_log(line_count=20)
#    - Display recent log entries
#    - Ask: "Do these log entries look normal?"
#    - Note: This is for validation only, not saved to baseline
#
# METADATA UPDATE:
# ---------------
# After all validation:
#   Update BASELINE_METADATA in baseline_data.py:
#   - last_updated: current ISO8601 timestamp
#   - indigo_version: from user or detected
#   - plugin_version: from plugin info
#   - validation_method: "interactive"
#   - notes: any relevant notes from user


if __name__ == "__main__":
    print(__doc__)
    print("\nThis script is designed to be run BY Claude Code, not directly.")
    print("Claude Code will use this as a guide for the interactive validation process.")
    print("\nTo start validation, ask Claude Code:")
    print('  "Run the interactive baseline validation for Search tools"')
    sys.exit(0)
