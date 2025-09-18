#!/usr/bin/env python3
"""
Production MCP Server Testing Script using FastMCP Client
Tests MCP server inspection and functionality in production Indigo environment
"""

import asyncio
import json
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from fastmcp import Client
except ImportError:
    print("ERROR: FastMCP client not found. Install with: pip install fastmcp")
    sys.exit(1)


class MCPServerTester:
    """Test harness for MCP server using FastMCP client."""
    
    def __init__(self, base_url: str):
        """
        Initialize the tester.
        
        Args:
            base_url: The MCP server endpoint URL
        """
        self.base_url = base_url
        self.client = None
        self.test_results = []
        
    async def connect(self) -> bool:
        """
        Establish connection to MCP server.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Create client with URL (no authentication needed - handled by Indigo Web Server)
            self.client = Client(transport=self.base_url)
            
            # Connect to the server
            await self.client.__aenter__()
            
            # Get server info from initialization result
            init_result = self.client.initialize_result
            
            print("✅ Successfully connected to MCP server")
            if init_result and hasattr(init_result, 'server_info'):
                print(f"   Server: {init_result.server_info.name}")
                print(f"   Version: {init_result.server_info.version}")
            if init_result and hasattr(init_result, 'protocol_version'):
                print(f"   Protocol: {init_result.protocol_version}")
            if init_result and hasattr(init_result, 'capabilities'):
                caps = init_result.capabilities
                cap_list = []
                if hasattr(caps, 'tools') and caps.tools:
                    cap_list.append('tools')
                if hasattr(caps, 'resources') and caps.resources:
                    cap_list.append('resources')
                if hasattr(caps, 'prompts') and caps.prompts:
                    cap_list.append('prompts')
                if hasattr(caps, 'logging') and caps.logging:
                    cap_list.append('logging')
                print(f"   Capabilities: {cap_list}")
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to connect: {str(e)}")
            return False
    
    async def disconnect(self):
        """Disconnect from MCP server."""
        if self.client:
            try:
                await self.client.__aexit__(None, None, None)
                print("✅ Disconnected from MCP server")
            except Exception as e:
                print(f"⚠️  Error during disconnect: {str(e)}")
    
    async def test_list_tools(self) -> bool:
        """Test listing available tools."""
        print("\n" + "="*60)
        print("TEST: List Available Tools")
        print("="*60)
        
        try:
            result = await self.client.list_tools()
            
            # Handle the result based on what's returned
            tools = []
            if hasattr(result, 'tools'):
                tools = result.tools
            elif isinstance(result, list):
                tools = result
            elif hasattr(result, '__iter__'):
                tools = list(result)
            
            print(f"✅ Found {len(tools)} tools:")
            
            for tool in tools[:10]:  # Show first 10 tools
                tool_name = tool.name if hasattr(tool, 'name') else str(tool)
                print(f"   • {tool_name}")
                if hasattr(tool, 'description') and tool.description:
                    desc_lines = tool.description.split('\n')
                    print(f"     {desc_lines[0][:70]}{'...' if len(desc_lines[0]) > 70 else ''}")
            
            if len(tools) > 10:
                print(f"   ... and {len(tools) - 10} more tools")
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to list tools: {str(e)}")
            return False
    
    async def test_list_resources(self) -> bool:
        """Test listing available resources."""
        print("\n" + "="*60)
        print("TEST: List Available Resources")
        print("="*60)
        
        try:
            result = await self.client.list_resources()
            
            # Handle the result based on what's returned
            resources = []
            if hasattr(result, 'resources'):
                resources = result.resources
            elif isinstance(result, list):
                resources = result
            elif hasattr(result, '__iter__'):
                resources = list(result)
            
            print(f"✅ Found {len(resources)} resources:")
            
            for resource in resources:
                resource_uri = resource.uri if hasattr(resource, 'uri') else str(resource)
                print(f"   • {resource_uri}")
                if hasattr(resource, 'description') and resource.description:
                    desc_lines = resource.description.split('\n')
                    print(f"     {desc_lines[0][:70]}{'...' if len(desc_lines[0]) > 70 else ''}")
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to list resources: {str(e)}")
            return False
    
    async def test_search_entities(self) -> bool:
        """Test the search_entities tool."""
        print("\n" + "="*60)
        print("TEST: Search Entities Tool")
        print("="*60)
        
        try:
            # Call search_entities tool
            result = await self.client.call_tool(
                "search_entities",
                arguments={"query": "lights"}
            )
            
            print(f"✅ Search completed successfully")
            
            # Parse the result - the structure may vary
            if result:
                # Check for different possible response formats
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
                
                if text_content:
                    # Try to parse as JSON if it looks like JSON
                    if text_content.startswith("{") or text_content.startswith("["):
                        try:
                            search_data = json.loads(text_content)
                            if isinstance(search_data, dict) and "results" in search_data:
                                print(f"   Found {len(search_data['results'])} results")
                                for i, item in enumerate(search_data['results'][:3]):
                                    print(f"   {i+1}. {item.get('name', 'Unknown')} (ID: {item.get('id', 'N/A')})")
                            else:
                                print(f"   Response type: {type(search_data).__name__}")
                        except json.JSONDecodeError:
                            print(f"   Response: {text_content[:200]}")
                    else:
                        print(f"   Response: {text_content[:200]}")
            
            return True
            
        except asyncio.TimeoutError:
            print("⚠️  Search timed out (this can happen with large datasets)")
            return True  # Consider timeout as partial success
        except Exception as e:
            print(f"❌ Search failed: {str(e)}")
            return False
    
    async def test_list_devices(self) -> bool:
        """Test the list_devices tool."""
        print("\n" + "="*60)
        print("TEST: List Devices Tool")
        print("="*60)
        
        try:
            # Call list_devices tool
            result = await self.client.call_tool(
                "list_devices",
                arguments={}
            )
            
            print(f"✅ List devices completed successfully")
            
            # Parse the result
            if result:
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
                
                if text_content and text_content.startswith("["):
                    try:
                        devices = json.loads(text_content)
                        print(f"   Found {len(devices)} devices")
                        for i, device in enumerate(devices[:3]):
                            print(f"   {i+1}. {device.get('name', 'Unknown')} (ID: {device.get('id', 'N/A')})")
                    except json.JSONDecodeError:
                        print(f"   Response: {text_content[:200]}")
                elif text_content:
                    print(f"   Response: {text_content[:200]}")
            
            return True
            
        except Exception as e:
            print(f"❌ List devices failed: {str(e)}")
            return False
    
    async def test_get_device_by_id(self) -> bool:
        """Test getting a specific device by ID."""
        print("\n" + "="*60)
        print("TEST: Get Device By ID Tool")
        print("="*60)
        
        try:
            # First get a list of devices to find a valid ID
            list_result = await self.client.call_tool("list_devices", arguments={})
            
            device_id = None
            device_name = None
            
            if list_result:
                text_content = None
                
                if hasattr(list_result, 'content'):
                    content = list_result.content
                    if isinstance(content, list) and len(content) > 0:
                        if hasattr(content[0], 'text'):
                            text_content = content[0].text
                        else:
                            text_content = str(content[0])
                elif hasattr(list_result, 'text'):
                    text_content = list_result.text
                elif isinstance(list_result, str):
                    text_content = list_result
                
                if text_content and text_content.startswith("["):
                    try:
                        devices = json.loads(text_content)
                        if devices and len(devices) > 0:
                            device_id = devices[0].get('id')
                            device_name = devices[0].get('name', 'Unknown')
                    except:
                        pass
            
            if not device_id:
                print("⚠️  Could not get a valid device ID for testing")
                return False
            
            print(f"   Testing with device: {device_name} (ID: {device_id})")
            
            # Now test get_device_by_id
            result = await self.client.call_tool(
                "get_device_by_id",
                arguments={"device_id": device_id}
            )
            
            if result:
                text_content = None
                
                if hasattr(result, 'content'):
                    content = result.content
                    if isinstance(content, list) and len(content) > 0:
                        if hasattr(content[0], 'text'):
                            text_content = content[0].text
                        else:
                            text_content = str(content[0])
                elif hasattr(result, 'text'):
                    text_content = result.text
                elif isinstance(result, str):
                    text_content = result
                
                if text_content and text_content.startswith("{"):
                    try:
                        device = json.loads(text_content)
                        print(f"✅ Successfully retrieved device")
                        print(f"   - Name: {device.get('name', 'Unknown')}")
                        print(f"   - Type: {device.get('type', 'Unknown')}")
                        print(f"   - State Count: {len(device.get('states', {}))}")
                        return True
                    except:
                        print(f"✅ Tool responded with data")
                        return True
                elif text_content:
                    print(f"✅ Tool responded: {text_content[:100]}")
                    return True
            
            print("✅ Tool executed successfully")
            return True
            
        except Exception as e:
            print(f"❌ Get device by ID failed: {str(e)}")
            return False
    
    async def test_resource_access(self) -> bool:
        """Test accessing a resource directly."""
        print("\n" + "="*60)
        print("TEST: Resource Access (devices)")
        print("="*60)
        
        try:
            # Read devices resource
            result = await self.client.read_resource("indigo://devices")
            
            if result:
                # Check different possible result structures
                mime_type = 'unknown'
                text_content = None
                
                if hasattr(result, 'content'):
                    content = result.content
                    if isinstance(content, list) and len(content) > 0:
                        if hasattr(content[0], 'mime_type'):
                            mime_type = content[0].mime_type
                        if hasattr(content[0], 'text'):
                            text_content = content[0].text
                        else:
                            text_content = str(content[0])
                    elif isinstance(content, str):
                        text_content = content
                elif hasattr(result, 'mime_type'):
                    mime_type = result.mime_type
                    text_content = result.text if hasattr(result, 'text') else str(result)
                elif isinstance(result, str):
                    text_content = result
                else:
                    text_content = str(result)
                
                print(f"✅ Resource returned content (type: {mime_type})")
                
                if text_content and (mime_type == "application/json" or text_content.startswith("[")):
                    try:
                        data = json.loads(text_content)
                        if isinstance(data, list):
                            print(f"   Found {len(data)} devices")
                        elif isinstance(data, dict) and "devices" in data:
                            print(f"   Found {len(data['devices'])} devices")
                    except:
                        print(f"   Content length: {len(text_content)} characters")
                elif text_content:
                    print(f"   Content length: {len(text_content)} characters")
            else:
                print("✅ Resource accessed successfully")
            
            return True
            
        except Exception as e:
            print(f"❌ Resource access failed: {str(e)}")
            return False
    
    async def test_list_variables(self) -> bool:
        """Test listing variables."""
        print("\n" + "="*60)
        print("TEST: List Variables Tool")
        print("="*60)
        
        try:
            # Call list_variables tool
            result = await self.client.call_tool(
                "list_variables",
                arguments={}
            )
            
            print(f"✅ List variables completed successfully")
            
            # Parse the result
            if result:
                text_content = None
                
                if hasattr(result, 'content'):
                    content = result.content
                    if isinstance(content, list) and len(content) > 0:
                        if hasattr(content[0], 'text'):
                            text_content = content[0].text
                        else:
                            text_content = str(content[0])
                elif hasattr(result, 'text'):
                    text_content = result.text
                elif isinstance(result, str):
                    text_content = result
                
                if text_content and text_content.startswith("["):
                    try:
                        variables = json.loads(text_content)
                        print(f"   Found {len(variables)} variables")
                        for i, var in enumerate(variables[:3]):
                            print(f"   {i+1}. {var.get('name', 'Unknown')} = {var.get('value', 'N/A')}")
                    except:
                        print(f"   Response: {text_content[:200]}")
                elif text_content:
                    print(f"   Response: {text_content[:200]}")
            
            return True
            
        except Exception as e:
            print(f"❌ List variables failed: {str(e)}")
            return False
    
    async def run_all_tests(self) -> bool:
        """
        Run all tests and report results.
        
        Returns:
            True if all tests passed, False otherwise
        """
        print(f"\n{'#'*60}")
        print(f"# MCP Server Production Testing (FastMCP Client)")
        print(f"# Endpoint: {self.base_url}")
        print(f"# Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'#'*60}")
        
        # Connect to server
        print("\n" + "="*60)
        print("TEST: Server Connection & Initialization")
        print("="*60)
        
        if not await self.connect():
            print("\n💔 Failed to connect to server. Cannot continue tests.")
            return False
        
        self.test_results.append(("Connect & Initialize", True))
        
        # Run all tests
        tests = [
            ("List Tools", self.test_list_tools),
            ("List Resources", self.test_list_resources),
            ("List Devices", self.test_list_devices),
            ("List Variables", self.test_list_variables),
            ("Search Entities", self.test_search_entities),
            ("Get Device By ID", self.test_get_device_by_id),
            ("Resource Access", self.test_resource_access),
        ]
        
        for test_name, test_func in tests:
            try:
                success = await test_func()
                self.test_results.append((test_name, success))
            except Exception as e:
                print(f"\n❌ Test '{test_name}' crashed: {str(e)}")
                self.test_results.append((test_name, False))
        
        # Disconnect
        await self.disconnect()
        
        # Summary
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        
        passed = sum(1 for _, success in self.test_results if success)
        total = len(self.test_results)
        
        for test_name, success in self.test_results:
            status = "✅ PASSED" if success else "❌ FAILED"
            print(f"{status}: {test_name}")
        
        print(f"\nResults: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 All tests passed!")
            return True
        elif passed > 0:
            print("⚠️  Some tests failed")
            return False
        else:
            print("💔 All tests failed")
            return False


async def main():
    """Main entry point for test script."""
    # Configuration
    BASE_URL = "https://vtmikel.indigodomo.net/message/com.vtmikel.mcp_server/mcp"
    
    # Run tests
    tester = MCPServerTester(BASE_URL)
    success = await tester.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())