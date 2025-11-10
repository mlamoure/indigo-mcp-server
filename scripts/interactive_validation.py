#!/usr/bin/env python3
"""
Interactive validation script using FastMCP Client.

This script connects to the production Indigo MCP server and runs validation
queries, displaying results for user confirmation.
"""

import asyncio
import json
import sys
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path

try:
    from fastmcp import Client
except ImportError:
    print("ERROR: FastMCP client not found. Install with: pip install fastmcp")
    sys.exit(1)


# Production MCP server endpoint
BASE_URL = "https://vtmikel.indigodomo.net/message/com.vtmikel.mcp_server/mcp"


class ValidationSession:
    """Interactive validation session for capturing baseline data."""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.client = None
        self.baseline_data = {
            "search_queries": {},
            "device_types": {},
            "sample_device_ids": [],
            "sample_variable_ids": [],
            "sample_action_group_ids": [],
            "expected_counts": {},
            "plugins": [],
            "metadata": {
                "last_updated": datetime.now().isoformat(),
                "validation_method": "interactive",
                "notes": ""
            }
        }

    async def connect(self) -> bool:
        """Connect to MCP server."""
        try:
            self.client = Client(transport=self.base_url)
            await self.client.__aenter__()
            print(f"✅ Connected to MCP server at {self.base_url}\n")
            return True
        except Exception as e:
            print(f"❌ Failed to connect: {str(e)}")
            return False

    async def disconnect(self):
        """Disconnect from MCP server."""
        if self.client:
            try:
                await self.client.__aexit__(None, None, None)
                print("\n✅ Disconnected from MCP server")
            except Exception as e:
                print(f"⚠️  Error during disconnect: {str(e)}")

    def parse_tool_response(self, result) -> Optional[str]:
        """Parse tool response into text content."""
        if not result:
            return None

        text_content = None

        if hasattr(result, 'content'):
            content = result.content
            if isinstance(content, list) and len(content) > 0:
                if hasattr(content[0], 'text'):
                    text_content = content[0].text
                else:
                    text_content = str(content[0])
            elif isinstance(content, str):
                text_content = content
        elif hasattr(result, 'text'):
            text_content = result.text
        elif isinstance(result, str):
            text_content = result
        else:
            text_content = str(result)

        return text_content

    async def validate_search_query(self, query: str) -> bool:
        """Validate a search query and capture baseline data."""
        print(f"\n{'='*60}")
        print(f"🔍 Testing search_entities: '{query}'")
        print(f"{'='*60}")

        try:
            result = await self.client.call_tool(
                "search_entities",
                arguments={"query": query}
            )

            text_content = self.parse_tool_response(result)

            if not text_content:
                print("❌ No response received")
                return False

            # Parse JSON response
            try:
                search_data = json.loads(text_content)
            except json.JSONDecodeError:
                print(f"❌ Invalid JSON response: {text_content[:200]}")
                return False

            # Display results
            total_count = search_data.get('total_count', 0)
            results = search_data.get('results', {})

            print(f"\n📊 Results:")
            print(f"   Total Count: {total_count}")

            all_entities = []
            for category, items in results.items():
                if items:
                    print(f"\n   {category.upper()} ({len(items)}):")
                    for i, item in enumerate(items[:5], 1):
                        name = item.get('name', 'Unknown')
                        item_id = item.get('id', 'N/A')
                        print(f"     {i}. {name} (ID: {item_id})")
                        all_entities.append(name)
                    if len(items) > 5:
                        print(f"     ... and {len(items) - 5} more")

            # Ask for confirmation
            print(f"\n❓ Are these results expected for query '{query}'?")
            response = input("   Enter 'y' for yes, 'n' for no: ").strip().lower()

            if response == 'y':
                # Save to baseline
                self.baseline_data['search_queries'][query] = {
                    'expected_min_count': total_count,
                    'expected_entities': all_entities[:10],  # Top 10 entities
                    'query_timestamp': datetime.now().isoformat()
                }
                print("   ✅ Saved to baseline data")
                return True
            else:
                print("   ⏭️  Skipped (not saved)")
                return False

        except Exception as e:
            print(f"❌ Error: {str(e)}")
            return False

    async def validate_device_type(self, device_type: str) -> bool:
        """Validate device type query and capture baseline data."""
        print(f"\n{'='*60}")
        print(f"🔍 Testing get_devices_by_type: '{device_type}'")
        print(f"{'='*60}")

        try:
            result = await self.client.call_tool(
                "get_devices_by_type",
                arguments={"device_type": device_type}
            )

            text_content = self.parse_tool_response(result)

            if not text_content:
                print("❌ No response received")
                return False

            # Parse JSON response
            try:
                response_data = json.loads(text_content)
            except json.JSONDecodeError:
                print(f"❌ Invalid JSON response: {text_content[:200]}")
                return False

            # Check for success
            if not response_data.get('success'):
                print(f"❌ Tool returned error: {response_data.get('error', 'Unknown error')}")
                return False

            # Get devices
            devices = response_data.get('data', [])

            print(f"\n📊 Results:")
            print(f"   Device Type: {device_type}")
            print(f"   Total Count: {len(devices)}")

            if devices:
                print(f"\n   Sample Devices (first 10):")
                sample_ids = []
                for i, device in enumerate(devices[:10], 1):
                    name = device.get('name', 'Unknown')
                    device_id = device.get('id', 'N/A')
                    on_state = device.get('onState', 'N/A')
                    print(f"     {i}. {name} (ID: {device_id}, On: {on_state})")
                    if device_id != 'N/A':
                        sample_ids.append(device_id)

                if len(devices) > 10:
                    print(f"     ... and {len(devices) - 10} more")

                print(f"\n   Sample IDs: {sample_ids[:5]}")

            # Ask for confirmation
            print(f"\n❓ Are these results expected for device type '{device_type}'?")
            response = input("   Enter 'y' for yes, 'n' for no: ").strip().lower()

            if response == 'y':
                # Save to baseline
                self.baseline_data['device_types'][device_type] = {
                    'expected_min_count': len(devices),
                    'sample_device_ids': sample_ids[:5]
                }
                print("   ✅ Saved to baseline data")
                return True
            else:
                print("   ⏭️  Skipped (not saved)")
                return False

        except Exception as e:
            print(f"❌ Error: {str(e)}")
            return False

    async def validate_list_devices(self) -> bool:
        """Validate list_devices and capture count."""
        print(f"\n{'='*60}")
        print(f"📋 Testing list_devices")
        print(f"{'='*60}")

        try:
            result = await self.client.call_tool("list_devices", arguments={})
            text_content = self.parse_tool_response(result)

            if not text_content:
                print("❌ No response received")
                return False

            devices = json.loads(text_content)

            print(f"\n📊 Results:")
            print(f"   Total Devices: {len(devices)}")

            if devices:
                print(f"\n   Sample Devices (first 5):")
                for i, device in enumerate(devices[:5], 1):
                    name = device.get('name', 'Unknown')
                    device_id = device.get('id', 'N/A')
                    print(f"     {i}. {name} (ID: {device_id})")

            print(f"\n❓ Is this device count expected?")
            response = input("   Enter 'y' for yes, 'n' for no: ").strip().lower()

            if response == 'y':
                self.baseline_data['expected_counts']['devices'] = {
                    'total': len(devices),
                    'tolerance': 5,
                    'last_verified': datetime.now().date().isoformat()
                }

                # Save sample device IDs
                self.baseline_data['sample_device_ids'] = [
                    d['id'] for d in devices[:5] if 'id' in d
                ]

                print("   ✅ Saved to baseline data")
                return True
            else:
                print("   ⏭️  Skipped (not saved)")
                return False

        except Exception as e:
            print(f"❌ Error: {str(e)}")
            return False

    async def validate_list_variables(self) -> bool:
        """Validate list_variables and capture count."""
        print(f"\n{'='*60}")
        print(f"📋 Testing list_variables")
        print(f"{'='*60}")

        try:
            result = await self.client.call_tool("list_variables", arguments={})
            text_content = self.parse_tool_response(result)

            if not text_content:
                print("❌ No response received")
                return False

            variables = json.loads(text_content)

            print(f"\n📊 Results:")
            print(f"   Total Variables: {len(variables)}")

            if variables:
                print(f"\n   Sample Variables (first 5):")
                for i, var in enumerate(variables[:5], 1):
                    name = var.get('name', 'Unknown')
                    var_id = var.get('id', 'N/A')
                    value = var.get('value', '')
                    print(f"     {i}. {name} = '{value}' (ID: {var_id})")

            print(f"\n❓ Is this variable count expected?")
            response = input("   Enter 'y' for yes, 'n' for no: ").strip().lower()

            if response == 'y':
                self.baseline_data['expected_counts']['variables'] = {
                    'total': len(variables),
                    'tolerance': 3,
                    'last_verified': datetime.now().date().isoformat()
                }

                # Save sample variable IDs
                self.baseline_data['sample_variable_ids'] = [
                    v['id'] for v in variables[:5] if 'id' in v
                ]

                print("   ✅ Saved to baseline data")
                return True
            else:
                print("   ⏭️  Skipped (not saved)")
                return False

        except Exception as e:
            print(f"❌ Error: {str(e)}")
            return False

    async def validate_list_action_groups(self) -> bool:
        """Validate list_action_groups and capture count."""
        print(f"\n{'='*60}")
        print(f"📋 Testing list_action_groups")
        print(f"{'='*60}")

        try:
            result = await self.client.call_tool("list_action_groups", arguments={})
            text_content = self.parse_tool_response(result)

            if not text_content:
                print("❌ No response received")
                return False

            action_groups = json.loads(text_content)

            print(f"\n📊 Results:")
            print(f"   Total Action Groups: {len(action_groups)}")

            if action_groups:
                print(f"\n   Sample Action Groups (first 5):")
                for i, ag in enumerate(action_groups[:5], 1):
                    name = ag.get('name', 'Unknown')
                    ag_id = ag.get('id', 'N/A')
                    print(f"     {i}. {name} (ID: {ag_id})")

            print(f"\n❓ Is this action group count expected?")
            response = input("   Enter 'y' for yes, 'n' for no: ").strip().lower()

            if response == 'y':
                self.baseline_data['expected_counts']['action_groups'] = {
                    'total': len(action_groups),
                    'tolerance': 2,
                    'last_verified': datetime.now().date().isoformat()
                }

                # Save sample action group IDs
                self.baseline_data['sample_action_group_ids'] = [
                    a['id'] for a in action_groups[:5] if 'id' in a
                ]

                print("   ✅ Saved to baseline data")
                return True
            else:
                print("   ⏭️  Skipped (not saved)")
                return False

        except Exception as e:
            print(f"❌ Error: {str(e)}")
            return False

    async def validate_list_plugins(self) -> bool:
        """Validate list_plugins and capture data."""
        print(f"\n{'='*60}")
        print(f"📋 Testing list_plugins")
        print(f"{'='*60}")

        try:
            result = await self.client.call_tool("list_plugins", arguments={})
            text_content = self.parse_tool_response(result)

            if not text_content:
                print("❌ No response received")
                return False

            plugins = json.loads(text_content)

            print(f"\n📊 Results:")
            print(f"   Total Plugins: {len(plugins)}")

            if plugins:
                print(f"\n   Installed Plugins:")
                for i, plugin in enumerate(plugins, 1):
                    plugin_id = plugin.get('id', 'Unknown')
                    name = plugin.get('name', 'Unknown')
                    enabled = plugin.get('enabled', False)
                    version = plugin.get('version', 'N/A')
                    status = "✓ Enabled" if enabled else "✗ Disabled"
                    print(f"     {i}. {name} ({plugin_id}) v{version} - {status}")

            print(f"\n❓ Are these plugins expected?")
            response = input("   Enter 'y' for yes, 'n' for no: ").strip().lower()

            if response == 'y':
                self.baseline_data['plugins'] = plugins
                print("   ✅ Saved to baseline data")
                return True
            else:
                print("   ⏭️  Skipped (not saved)")
                return False

        except Exception as e:
            print(f"❌ Error: {str(e)}")
            return False

    def save_baseline_data(self):
        """Save baseline data to file."""
        # TODO: Generate Python code to update baseline_data.py
        print(f"\n{'='*60}")
        print("💾 Baseline Data Summary")
        print(f"{'='*60}")

        print(f"\nCaptured Data:")
        print(f"  • Search Queries: {len(self.baseline_data['search_queries'])}")
        print(f"  • Device Types: {len(self.baseline_data['device_types'])}")
        print(f"  • Sample Device IDs: {len(self.baseline_data['sample_device_ids'])}")
        print(f"  • Sample Variable IDs: {len(self.baseline_data['sample_variable_ids'])}")
        print(f"  • Sample Action Group IDs: {len(self.baseline_data['sample_action_group_ids'])}")
        print(f"  • Expected Counts: {len(self.baseline_data['expected_counts'])}")
        print(f"  • Plugins: {len(self.baseline_data['plugins'])}")

        print(f"\n📄 To update baseline_data.py, use this data:")
        print(json.dumps(self.baseline_data, indent=2))

    async def run_search_validation(self):
        """Run search & discovery validation."""
        queries = [
            "living room lights",
            "bedroom lights",
            "temperature sensors",
            "motion sensors",
            "thermostats",
        ]

        for query in queries:
            await self.validate_search_query(query)

    async def run_device_type_validation(self):
        """Run device type validation."""
        device_types = ["dimmer", "relay", "sensor", "thermostat"]

        for device_type in device_types:
            await self.validate_device_type(device_type)

    async def run_listing_validation(self):
        """Run listing tools validation."""
        await self.validate_list_devices()
        await self.validate_list_variables()
        await self.validate_list_action_groups()

    async def run_plugin_validation(self):
        """Run plugin tools validation."""
        await self.validate_list_plugins()

    async def run_all_validations(self):
        """Run all validation tests."""
        print(f"\n{'#'*60}")
        print(f"# Interactive Baseline Validation")
        print(f"# Endpoint: {self.base_url}")
        print(f"# Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'#'*60}")

        if not await self.connect():
            return False

        # Run validations
        print("\n\n🔍 PHASE 1: Search & Discovery Tools")
        await self.run_search_validation()

        print("\n\n📦 PHASE 2: Device Type Queries")
        await self.run_device_type_validation()

        print("\n\n📋 PHASE 3: Listing Tools")
        await self.run_listing_validation()

        print("\n\n🔌 PHASE 4: Plugin Tools")
        await self.run_plugin_validation()

        # Disconnect
        await self.disconnect()

        # Save results
        self.save_baseline_data()

        return True


async def main():
    """Main entry point."""
    session = ValidationSession(BASE_URL)
    await session.run_all_validations()


if __name__ == "__main__":
    asyncio.run(main())
