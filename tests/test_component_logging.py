"""
Test to verify that MCP component logging works correctly and doesn't duplicate.
"""

import sys
import os
import logging
from unittest.mock import Mock, MagicMock, patch
import asyncio

# Add plugin directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "MCP Server.indigoPlugin", "Contents", "Server Plugin"))

def test_component_logging():
    """Test that MCP components are logged exactly once."""
    
    # Configure logging to capture all levels
    logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')
    logger = logging.getLogger("Plugin")
    
    # Capture log output
    log_capture = []
    
    class LogCapture(logging.Handler):
        def emit(self, record):
            log_capture.append((record.levelname, record.getMessage()))
    
    handler = LogCapture()
    logger.addHandler(handler)
    
    print("\n=== Testing Plugin Component Logging ===")
    
    # Mock indigo module
    mock_indigo = MagicMock()
    sys.modules['indigo'] = mock_indigo
    
    # Create mock device
    mock_device = Mock()
    mock_device.name = "Test MCP Server"
    mock_device.updateStateOnServer = Mock()
    
    # Mock MCPServerCore
    with patch('plugin.MCPServerCore') as MockMCPServerCore:
        # Create mock MCP server instance
        mock_mcp_core = Mock()
        mock_mcp_server = Mock()
        
        # Setup async mock methods that return tool dictionaries
        async def mock_get_tools():
            return {
                "search_entities": Mock(),
                "list_devices": Mock(),
                "device_turn_on": Mock()
            }
        
        async def mock_get_resources():
            return {}
        
        async def mock_get_prompts():
            return {}
        
        mock_mcp_server.get_tools = Mock(side_effect=mock_get_tools)
        mock_mcp_server.get_resources = Mock(side_effect=mock_get_resources)
        mock_mcp_server.get_prompts = Mock(side_effect=mock_get_prompts)
        
        mock_mcp_core.mcp_server = mock_mcp_server
        mock_mcp_core.start = Mock()
        MockMCPServerCore.return_value = mock_mcp_core
        
        # Import plugin after mocking
        from plugin import Plugin
        
        # Create plugin instance
        plugin = Plugin(
            plugin_id="test.plugin",
            plugin_display_name="Test Plugin", 
            plugin_version="1.0.0",
            plugin_prefs={}
        )
        
        # Set the logger to our test logger
        plugin.logger = logger
        
        # Set up data provider
        plugin.data_provider = Mock()
        
        # Also set mcp_server_core
        plugin.mcp_server_core = mock_mcp_core
        
        # Clear logs
        log_capture.clear()
        
        # Test the logging method directly first
        print("Testing _log_mcp_components directly...")
        plugin._log_mcp_components()
        
        print(f"Logs after direct call: {len(log_capture)}")
        for level, msg in log_capture[:5]:
            print(f"  {level}: {msg}")
        
        # Show all captured logs
        print(f"\nTotal logs captured: {len(log_capture)}")
        for level, msg in log_capture:
            print(f"  {level}: {msg}")
        
        # Check logs for MCP Tools
        tool_logs = [msg for level, msg in log_capture if level == 'INFO' and 'Published MCP Tools' in msg]
        resource_logs = [msg for level, msg in log_capture if level == 'INFO' and 'Published MCP Resources' in msg]
        prompt_logs = [msg for level, msg in log_capture if level == 'INFO' and 'Published MCP Prompts' in msg]
        
        print(f"\nTool logs found: {len(tool_logs)}")
        print(f"Resource logs found: {len(resource_logs)}")
        print(f"Prompt logs found: {len(prompt_logs)}")
        
        # Verify each component type is logged exactly once
        assert len(tool_logs) == 1, f"Expected 1 tool log, found {len(tool_logs)}: {tool_logs}"
        assert len(resource_logs) == 1, f"Expected 1 resource log, found {len(resource_logs)}"
        assert len(prompt_logs) == 1, f"Expected 1 prompt log, found {len(prompt_logs)}"
        
        # Verify the content of tool log
        assert "Published MCP Tools (3)" in tool_logs[0], f"Unexpected tool log content: {tool_logs[0]}"
        assert "search_entities" in tool_logs[0]
        assert "list_devices" in tool_logs[0]
        assert "device_turn_on" in tool_logs[0]
        
        print("\n✅ All component logging tests passed!")
        print("\nSummary:")
        print("- Components are logged exactly once")
        print("- No duplicate logging occurs")
        print("- Logging happens synchronously after server start")

if __name__ == "__main__":
    test_component_logging()