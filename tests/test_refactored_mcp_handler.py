"""
Comprehensive tests for refactored MCP handler.

Tests that the refactored mcp_handler.py with extracted modules (tool_registry,
resource_registry, tool_wrappers) produces the same functionality as the original.
"""

import json
import pytest
from unittest.mock import Mock, MagicMock, patch
import sys
from pathlib import Path

# Add plugin to path
plugin_path = Path(__file__).parent.parent / "MCP Server.indigoPlugin/Contents/Server Plugin"
sys.path.insert(0, str(plugin_path))

from mcp_server.mcp_handler import MCPHandler
from mcp_server.tool_registry import get_tool_schemas
from mcp_server.resource_registry import get_resource_schemas
from mcp_server.tool_wrappers import ToolWrappers


class TestRefactoredMCPHandler:
    """Test suite for refactored MCP handler architecture."""

    @pytest.fixture
    def mock_data_provider(self):
        """Create a mock data provider."""
        provider = Mock()
        provider.get_all_devices = Mock(return_value=[
            {
                "id": 12345,
                "name": "Test Device",
                "deviceTypeId": "relay",
                "enabled": True,
                "onState": True
            }
        ])
        provider.get_all_variables = Mock(return_value=[
            {
                "id": 67890,
                "name": "test_variable",
                "value": "test_value"
            }
        ])
        provider.get_all_action_groups = Mock(return_value=[
            {
                "id": 11111,
                "name": "Test Action"
            }
        ])
        provider.get_device = Mock(return_value={
            "id": 12345,
            "name": "Test Device",
            "deviceTypeId": "relay"
        })
        provider.get_variable = Mock(return_value={
            "id": 67890,
            "name": "test_variable"
        })
        provider.get_action_group = Mock(return_value={
            "id": 11111,
            "name": "Test Action"
        })
        return provider

    @pytest.fixture
    def mock_logger(self):
        """Create a mock logger."""
        return Mock()

    @pytest.fixture
    def mock_vector_store(self):
        """Create a mock vector store."""
        store = Mock()
        store.search = Mock(return_value=([], {
            "total_found": 0,
            "total_returned": 0,
            "truncated": False
        }))
        return store

    def test_tool_registry_returns_all_31_tools(self):
        """Test that tool_registry.get_tool_schemas() returns all 31 tools."""
        tool_functions = {name: Mock() for name in [
            "search_entities", "get_devices_by_type", "device_turn_on",
            "device_turn_off", "device_set_brightness", "device_set_rgb_color",
            "device_set_rgb_percent", "device_set_hex_color",
            "device_set_named_color", "device_set_white_levels",
            "thermostat_set_heat_setpoint", "thermostat_set_cool_setpoint",
            "thermostat_set_hvac_mode", "thermostat_set_fan_mode",
            "variable_update", "variable_create", "action_execute_group",
            "analyze_historical_data", "list_devices", "list_variables",
            "list_action_groups", "list_variable_folders",
            "get_devices_by_state", "get_device_by_id",
            "get_variable_by_id", "get_action_group_by_id",
            "query_event_log", "list_plugins", "get_plugin_by_id",
            "restart_plugin", "get_plugin_status"
        ]}

        tools = get_tool_schemas(tool_functions)

        assert len(tools) == 31, f"Expected 31 tools, got {len(tools)}"
        assert "search_entities" in tools
        assert "list_devices" in tools
        assert "device_turn_on" in tools
        # Verify structure
        for tool_name, tool_def in tools.items():
            assert "description" in tool_def
            assert "inputSchema" in tool_def
            assert "function" in tool_def
            assert tool_def["function"] is not None

    def test_resource_registry_returns_all_6_resources(self):
        """Test that resource_registry.get_resource_schemas() returns all 6 resources."""
        resource_functions = {name: Mock() for name in [
            "list_devices", "get_device", "list_variables",
            "get_variable", "list_actions", "get_action"
        ]}

        resources = get_resource_schemas(resource_functions)

        assert len(resources) == 6, f"Expected 6 resources, got {len(resources)}"
        assert "indigo://devices" in resources
        assert "indigo://devices/{device_id}" in resources
        assert "indigo://variables" in resources
        assert "indigo://variables/{variable_id}" in resources
        assert "indigo://actions" in resources
        assert "indigo://actions/{action_id}" in resources
        # Verify structure
        for uri, resource_def in resources.items():
            assert "name" in resource_def
            assert "description" in resource_def
            assert "function" in resource_def

    def test_tool_wrappers_initializes_with_all_handlers(self, mock_data_provider, mock_logger):
        """Test that ToolWrappers initializes with all required handlers."""
        # Create mock handlers
        search_handler = Mock()
        get_devices_by_type_handler = Mock()
        device_control_handler = Mock()
        rgb_control_handler = Mock()
        thermostat_control_handler = Mock()
        variable_control_handler = Mock()
        action_control_handler = Mock()
        historical_analysis_handler = Mock()
        list_handlers = Mock()
        log_query_handler = Mock()
        plugin_control_handler = Mock()

        # Initialize ToolWrappers
        wrappers = ToolWrappers(
            search_handler=search_handler,
            get_devices_by_type_handler=get_devices_by_type_handler,
            device_control_handler=device_control_handler,
            rgb_control_handler=rgb_control_handler,
            thermostat_control_handler=thermostat_control_handler,
            variable_control_handler=variable_control_handler,
            action_control_handler=action_control_handler,
            historical_analysis_handler=historical_analysis_handler,
            list_handlers=list_handlers,
            log_query_handler=log_query_handler,
            plugin_control_handler=plugin_control_handler,
            data_provider=mock_data_provider,
            logger=mock_logger
        )

        # Verify all wrapper methods exist
        assert hasattr(wrappers, 'tool_search_entities')
        assert hasattr(wrappers, 'tool_list_devices')
        assert hasattr(wrappers, 'tool_device_turn_on')
        assert hasattr(wrappers, 'resource_list_devices')
        assert hasattr(wrappers, 'resource_get_device')

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_mcp_handler_registers_tools_and_resources(self, mock_vsm, mock_data_provider, mock_logger):
        """Test that MCPHandler properly registers tools and resources using extracted modules."""
        # Mock vector store manager
        mock_vsm_instance = Mock()
        mock_vsm_instance.get_vector_store = Mock(return_value=Mock())
        mock_vsm_instance.start = Mock()
        mock_vsm.return_value = mock_vsm_instance

        # Set DB_FILE environment variable
        import os
        os.environ['DB_FILE'] = '/tmp/test_db'

        # Initialize handler
        handler = MCPHandler(data_provider=mock_data_provider, logger=mock_logger)

        # Verify tools registered
        assert len(handler._tools) == 31
        assert "search_entities" in handler._tools
        assert "list_devices" in handler._tools

        # Verify resources registered
        assert len(handler._resources) == 6
        assert "indigo://devices" in handler._resources

        # Verify tool structure
        for tool_name, tool_def in handler._tools.items():
            assert "description" in tool_def
            assert "inputSchema" in tool_def
            assert "function" in tool_def
            assert callable(tool_def["function"])

        # Verify resource structure
        for uri, resource_def in handler._resources.items():
            assert "name" in resource_def
            assert "description" in resource_def
            assert "function" in resource_def
            assert callable(resource_def["function"])

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_mcp_handler_tools_list_request(self, mock_vsm, mock_data_provider, mock_logger):
        """Test that MCPHandler properly handles tools/list request."""
        # Mock vector store manager
        mock_vsm_instance = Mock()
        mock_vsm_instance.get_vector_store = Mock(return_value=Mock())
        mock_vsm_instance.start = Mock()
        mock_vsm.return_value = mock_vsm_instance

        import os
        os.environ['DB_FILE'] = '/tmp/test_db'

        handler = MCPHandler(data_provider=mock_data_provider, logger=mock_logger)

        # Simulate tools/list request
        response = handler._handle_tools_list(msg_id=1, params={})

        # Verify response structure
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert "result" in response
        assert "tools" in response["result"]
        assert len(response["result"]["tools"]) == 31

        # Verify tool entries have correct structure
        for tool in response["result"]["tools"]:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool

    @patch('mcp_server.mcp_handler.VectorStoreManager')
    def test_mcp_handler_resources_list_request(self, mock_vsm, mock_data_provider, mock_logger):
        """Test that MCPHandler properly handles resources/list request."""
        # Mock vector store manager
        mock_vsm_instance = Mock()
        mock_vsm_instance.get_vector_store = Mock(return_value=Mock())
        mock_vsm_instance.start = Mock()
        mock_vsm.return_value = mock_vsm_instance

        import os
        os.environ['DB_FILE'] = '/tmp/test_db'

        handler = MCPHandler(data_provider=mock_data_provider, logger=mock_logger)

        # Simulate resources/list request
        response = handler._handle_resources_list(msg_id=1, params={})

        # Verify response structure
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert "result" in response
        assert "resources" in response["result"]
        assert len(response["result"]["resources"]) == 6

        # Verify resource entries have correct structure
        for resource in response["result"]["resources"]:
            assert "uri" in resource
            assert "name" in resource
            assert "description" in resource
            assert "mimeType" in resource

    def test_tool_wrappers_error_handling(self, mock_data_provider, mock_logger):
        """Test that tool wrappers properly handle errors."""
        # Create mock handlers that raise exceptions
        device_control_handler = Mock()
        device_control_handler.turn_on = Mock(side_effect=Exception("Test error"))

        wrappers = ToolWrappers(
            search_handler=Mock(),
            get_devices_by_type_handler=Mock(),
            device_control_handler=device_control_handler,
            rgb_control_handler=Mock(),
            thermostat_control_handler=Mock(),
            variable_control_handler=Mock(),
            action_control_handler=Mock(),
            historical_analysis_handler=Mock(),
            list_handlers=Mock(),
            log_query_handler=Mock(),
            plugin_control_handler=Mock(),
            data_provider=mock_data_provider,
            logger=mock_logger
        )

        # Call wrapper that should fail
        result_str = wrappers.tool_device_turn_on(device_id=12345)
        result = json.loads(result_str)

        # Verify error response
        assert "error" in result
        assert "Test error" in result["error"]

    def test_tool_schemas_have_required_pagination_parameters(self):
        """Test that paginated tools have limit and offset parameters."""
        # Create all required tool functions
        all_tool_names = [
            "search_entities", "get_devices_by_type", "device_turn_on",
            "device_turn_off", "device_set_brightness", "device_set_rgb_color",
            "device_set_rgb_percent", "device_set_hex_color",
            "device_set_named_color", "device_set_white_levels",
            "thermostat_set_heat_setpoint", "thermostat_set_cool_setpoint",
            "thermostat_set_hvac_mode", "thermostat_set_fan_mode",
            "variable_update", "variable_create", "action_execute_group",
            "analyze_historical_data", "list_devices", "list_variables",
            "list_action_groups", "list_variable_folders",
            "get_devices_by_state", "get_device_by_id",
            "get_variable_by_id", "get_action_group_by_id",
            "query_event_log", "list_plugins", "get_plugin_by_id",
            "restart_plugin", "get_plugin_status"
        ]
        tool_functions = {name: Mock() for name in all_tool_names}

        tools = get_tool_schemas(tool_functions)

        paginated_tools = [
            "search_entities", "list_devices", "list_variables",
            "list_action_groups", "get_devices_by_state", "get_devices_by_type"
        ]

        for tool_name in paginated_tools:
            tool = tools[tool_name]
            properties = tool["inputSchema"]["properties"]

            if tool_name in ["search_entities", "list_devices", "list_variables",
                            "list_action_groups", "get_devices_by_state", "get_devices_by_type"]:
                assert "limit" in properties, f"{tool_name} missing limit parameter"
                assert "offset" in properties, f"{tool_name} missing offset parameter"

                # Verify parameter constraints
                assert properties["limit"]["type"] == "integer"
                assert properties["offset"]["type"] == "integer"
                assert properties["limit"]["minimum"] == 1
                assert properties["limit"]["maximum"] == 500
                assert properties["offset"]["minimum"] == 0


class TestBackwardCompatibility:
    """Tests to ensure refactored code maintains backward compatibility."""

    def test_tool_names_unchanged(self):
        """Verify all tool names remain unchanged after refactoring."""
        expected_tools = {
            "search_entities", "get_devices_by_type", "device_turn_on",
            "device_turn_off", "device_set_brightness", "device_set_rgb_color",
            "device_set_rgb_percent", "device_set_hex_color",
            "device_set_named_color", "device_set_white_levels",
            "thermostat_set_heat_setpoint", "thermostat_set_cool_setpoint",
            "thermostat_set_hvac_mode", "thermostat_set_fan_mode",
            "variable_update", "variable_create", "action_execute_group",
            "analyze_historical_data", "list_devices", "list_variables",
            "list_action_groups", "list_variable_folders",
            "get_devices_by_state", "get_device_by_id",
            "get_variable_by_id", "get_action_group_by_id",
            "query_event_log", "list_plugins", "get_plugin_by_id",
            "restart_plugin", "get_plugin_status"
        }

        tool_functions = {name: Mock() for name in expected_tools}
        tools = get_tool_schemas(tool_functions)

        assert set(tools.keys()) == expected_tools

    def test_resource_uris_unchanged(self):
        """Verify all resource URIs remain unchanged after refactoring."""
        expected_resources = {
            "indigo://devices",
            "indigo://devices/{device_id}",
            "indigo://variables",
            "indigo://variables/{variable_id}",
            "indigo://actions",
            "indigo://actions/{action_id}"
        }

        resource_functions = {name: Mock() for name in [
            "list_devices", "get_device", "list_variables",
            "get_variable", "list_actions", "get_action"
        ]}
        resources = get_resource_schemas(resource_functions)

        assert set(resources.keys()) == expected_resources


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
