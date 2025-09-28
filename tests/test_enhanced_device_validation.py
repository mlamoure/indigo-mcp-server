"""
Tests for enhanced device type validation with alias support.
"""

import pytest
from unittest.mock import MagicMock, patch

try:
    from mcp_server.mcp_handler import MCPHandler
    from mcp_server.common.indigo_device_types import (
        DeviceTypeResolver,
        IndigoDeviceType
    )
    from mcp_server.adapters.data_provider import DataProvider
    INDIGO_AVAILABLE = True
except ImportError:
    INDIGO_AVAILABLE = False


@pytest.mark.skipif(not INDIGO_AVAILABLE, reason="Indigo modules not available")
class TestEnhancedDeviceValidation:
    """Test enhanced device validation with alias support."""

    @pytest.fixture
    def mock_handler(self):
        """Create a mock MCP handler for testing."""
        # Mock data provider with additional methods
        mock_data_provider = MagicMock()
        mock_data_provider.get_all_devices.return_value = []
        mock_data_provider.get_all_devices_unfiltered.return_value = []
        mock_data_provider.get_all_variables.return_value = []
        mock_data_provider.get_all_action_groups.return_value = []

        # Mock MCP handler
        with patch('mcp_server.mcp_handler.VectorStoreManager'), \
             patch('mcp_server.mcp_handler.ListHandlers'), \
             patch('mcp_server.mcp_handler.SearchEntitiesHandler'), \
             patch('mcp_server.mcp_handler.GetDevicesByTypeHandler'), \
             patch('mcp_server.mcp_handler.DeviceControlHandler'), \
             patch('mcp_server.mcp_handler.VariableControlHandler'), \
             patch('mcp_server.mcp_handler.ActionControlHandler'), \
             patch('mcp_server.mcp_handler.HistoricalAnalysisHandler'):

            handler = MCPHandler(data_provider=mock_data_provider)
            handler.logger = MagicMock()
            return handler

    def test_search_entities_with_valid_alias(self, mock_handler):
        """Test search_entities tool with valid device type alias."""
        # Mock the search handler to return empty results
        mock_handler.search_handler = MagicMock()
        mock_handler.search_handler.search.return_value = {"results": []}

        # Test with "light" alias (should resolve to "dimmer")
        result = mock_handler._tool_search_entities(
            query="bedroom lights",
            device_types=["light"]
        )

        # Verify search was called with resolved type
        mock_handler.search_handler.search.assert_called_once_with(
            "bedroom lights", ["dimmer"], None, None
        )

        # Verify no error in result
        import json
        result_data = json.loads(result)
        assert "error" not in result_data

    def test_search_entities_with_multiple_aliases(self, mock_handler):
        """Test search_entities tool with multiple device type aliases."""
        # Mock the search handler to return empty results
        mock_handler.search_handler = MagicMock()
        mock_handler.search_handler.search.return_value = {"results": []}

        # Test with multiple aliases
        result = mock_handler._tool_search_entities(
            query="home automation",
            device_types=["light", "switch", "motion"]
        )

        # Verify search was called with resolved types
        mock_handler.search_handler.search.assert_called_once_with(
            "home automation", ["dimmer", "relay", "sensor"], None, None
        )

        # Verify no error in result
        import json
        result_data = json.loads(result)
        assert "error" not in result_data

    def test_search_entities_with_invalid_device_type(self, mock_handler):
        """Test search_entities tool with invalid device type."""
        result = mock_handler._tool_search_entities(
            query="test query",
            device_types=["invalid_type"]
        )

        # Parse result and check error message
        import json
        result_data = json.loads(result)

        assert "error" in result_data
        error_message = result_data["error"]
        assert "Invalid device types: ['invalid_type']" in error_message
        assert "Valid types:" in error_message
        assert str(IndigoDeviceType.get_all_types()) in error_message

    def test_search_entities_with_similar_invalid_type(self, mock_handler):
        """Test search_entities tool with invalid type that has suggestions."""
        result = mock_handler._tool_search_entities(
            query="test query",
            device_types=["lig"]  # Should suggest "light"
        )

        # Parse result and check error message with suggestions
        import json
        result_data = json.loads(result)

        assert "error" in result_data
        error_message = result_data["error"]
        assert "Invalid device types: ['lig']" in error_message
        assert "Valid types:" in error_message
        assert "Did you mean:" in error_message

    def test_get_devices_by_state_with_valid_alias(self, mock_handler):
        """Test get_devices_by_state tool with valid device type alias."""
        # Mock the list handlers
        mock_handler.list_handlers = MagicMock()
        mock_handler.list_handlers.get_devices_by_state.return_value = []

        # Test with "light" alias
        result = mock_handler._tool_get_devices_by_state(
            state_conditions={"onState": True},
            device_types=["light"]
        )

        # Verify handler was called with resolved type
        mock_handler.list_handlers.get_devices_by_state.assert_called_once_with(
            {"onState": True}, ["dimmer"]
        )

        # Verify no error in result
        import json
        result_data = json.loads(result)
        assert "error" not in result_data

    def test_get_devices_by_state_with_invalid_device_type(self, mock_handler):
        """Test get_devices_by_state tool with invalid device type."""
        result = mock_handler._tool_get_devices_by_state(
            state_conditions={"onState": True},
            device_types=["invalid_type"]
        )

        # Parse result and check error message
        import json
        result_data = json.loads(result)

        assert "error" in result_data
        error_message = result_data["error"]
        assert "Invalid device types: ['invalid_type']" in error_message
        assert "Valid types:" in error_message

    def test_get_devices_by_type_with_valid_alias(self, mock_handler):
        """Test get_devices_by_type tool with valid device type alias."""
        # Mock the handler
        mock_handler.get_devices_by_type_handler = MagicMock()
        mock_handler.get_devices_by_type_handler.get_devices.return_value = {
            "devices": [],
            "success": True
        }

        # Test with "light" alias
        result = mock_handler._tool_get_devices_by_type("light")

        # Verify handler was called (the get_devices method handles resolution internally)
        mock_handler.get_devices_by_type_handler.get_devices.assert_called_once_with("light")

        # Verify no error in result
        import json
        result_data = json.loads(result)
        assert "error" not in result_data

    def test_mixed_valid_and_invalid_device_types(self, mock_handler):
        """Test with mix of valid and invalid device types."""
        result = mock_handler._tool_search_entities(
            query="test query",
            device_types=["light", "invalid", "switch"]
        )

        # Parse result and check error message
        import json
        result_data = json.loads(result)

        assert "error" in result_data
        error_message = result_data["error"]
        assert "Invalid device types: ['invalid']" in error_message
        # Should only show the invalid ones, not the resolved ones

    def test_case_insensitive_alias_resolution(self, mock_handler):
        """Test that alias resolution is case-insensitive."""
        # Mock the search handler
        mock_handler.search_handler = MagicMock()
        mock_handler.search_handler.search.return_value = {"results": []}

        # Test with various cases
        for alias in ["LIGHT", "Light", "LiGhT"]:
            result = mock_handler._tool_search_entities(
                query="test query",
                device_types=[alias]
            )

            # Verify no error and alias was resolved
            import json
            result_data = json.loads(result)
            assert "error" not in result_data

        # Verify all calls used "dimmer"
        calls = mock_handler.search_handler.search.call_args_list
        for call in calls:
            args, kwargs = call
            assert args[1] == ["dimmer"]  # device_types parameter

    def test_original_issue_reproduction(self, mock_handler):
        """Test that the original issue is now fixed."""
        # Mock the list handlers
        mock_handler.list_handlers = MagicMock()
        mock_handler.list_handlers.get_devices_by_state.return_value = [
            {"id": 1, "name": "Test Light", "onState": True}
        ]

        # The exact request from the original issue
        result = mock_handler._tool_get_devices_by_state(
            state_conditions={"on": True},
            device_types=["light"]
        )

        # Parse result - should now work instead of error
        import json
        result_data = json.loads(result)

        # Should not have an error
        assert "error" not in result_data

        # Should have called with resolved device type
        mock_handler.list_handlers.get_devices_by_state.assert_called_once_with(
            {"on": True}, ["dimmer"]
        )

    def test_whitespace_handling_in_aliases(self, mock_handler):
        """Test that whitespace in device type aliases is handled correctly."""
        # Mock the search handler
        mock_handler.search_handler = MagicMock()
        mock_handler.search_handler.search.return_value = {"results": []}

        # Test with whitespace
        result = mock_handler._tool_search_entities(
            query="test query",
            device_types=["  light  ", " switch "]
        )

        # Verify search was called with resolved types
        mock_handler.search_handler.search.assert_called_once_with(
            "test query", ["dimmer", "relay"], None, None
        )

        # Verify no error in result
        import json
        result_data = json.loads(result)
        assert "error" not in result_data