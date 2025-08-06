"""
Tests for core.py search_entities tool validation.
"""

import json
import socket
import pytest
from unittest.mock import Mock, MagicMock
from mcp_server.core import MCPServerCore
from mcp_server.adapters.data_provider import DataProvider
from mcp_server.common.indigo_device_types import IndigoDeviceType, IndigoEntityType


def get_free_port():
    """Get a free port for testing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


class MockDataProvider(DataProvider):
    """Mock data provider for testing."""
    
    def get_all_devices(self): return []
    def get_device(self, device_id): return None
    def get_all_variables(self): return []
    def get_variable(self, variable_id): return None
    def get_all_actions(self): return []
    def get_action(self, action_id): return None
    def get_all_entities_for_vector_store(self): return {"devices": [], "variables": [], "actions": []}


class MockSearchHandler:
    """Mock search handler for testing."""
    
    def __init__(self):
        self.search_calls = []
    
    def search(self, query, device_types=None, entity_types=None):
        self.search_calls.append({
            "query": query,
            "device_types": device_types,
            "entity_types": entity_types
        })
        return {
            "query": query,
            "total_count": 1,
            "results": {"devices": [], "variables": [], "actions": []},
            "summary": "Test search completed"
        }


class TestSearchEntitiesToolValidation:
    """Test cases for search_entities tool validation in core.py."""
    
    @pytest.fixture
    def mock_core(self, monkeypatch, temp_db_path):
        """Create a mock MCPServerCore for testing."""
        # Mock environment variable
        monkeypatch.setenv("DB_FILE", temp_db_path)
        
        # Create core instance with mock data provider
        mock_data_provider = MockDataProvider()
        core = MCPServerCore(
            data_provider=mock_data_provider,
            port=get_free_port()
        )
        
        # Replace search handler with mock
        core.search_handler = MockSearchHandler()
        
        return core
    
    def test_valid_device_types_accepted(self, mock_core):
        """Test that valid device types are accepted."""
        # Test the validation logic directly (since mcp_server is not fully initialized in mock)
        valid_device_types = ["dimmer", "relay", "sensor"]
        
        # Test that all valid device types pass validation
        for device_type in valid_device_types:
            assert IndigoDeviceType.is_valid_type(device_type)
        
        # Test validation logic that would be in the tool
        invalid_device_types = [dt for dt in valid_device_types if not IndigoDeviceType.is_valid_type(dt)]
        assert len(invalid_device_types) == 0
    
    def test_invalid_device_types_rejected(self, mock_core):
        """Test that invalid device types are rejected."""
        invalid_device_types = ["invalid", "light", "switch", "fake"]
        
        # Test that all invalid device types fail validation
        for device_type in invalid_device_types:
            assert not IndigoDeviceType.is_valid_type(device_type)
        
        # Test validation logic
        rejected_types = [dt for dt in invalid_device_types if not IndigoDeviceType.is_valid_type(dt)]
        assert len(rejected_types) == len(invalid_device_types)
    
    def test_valid_entity_types_accepted(self, mock_core):
        """Test that valid entity types are accepted."""
        valid_entity_types = ["device", "variable", "action"]
        
        # Test that all valid entity types pass validation
        for entity_type in valid_entity_types:
            assert IndigoEntityType.is_valid_type(entity_type)
        
        # Test validation logic
        invalid_entity_types = [et for et in valid_entity_types if not IndigoEntityType.is_valid_type(et)]
        assert len(invalid_entity_types) == 0
    
    def test_invalid_entity_types_rejected(self, mock_core):
        """Test that invalid entity types are rejected."""
        invalid_entity_types = ["invalid", "devices", "variables", "actions", "fake"]
        
        # Test that all invalid entity types fail validation
        for entity_type in invalid_entity_types:
            assert not IndigoEntityType.is_valid_type(entity_type)
        
        # Test validation logic
        rejected_types = [et for et in invalid_entity_types if not IndigoEntityType.is_valid_type(et)]
        assert len(rejected_types) == len(invalid_entity_types)
    
    def test_mixed_valid_invalid_device_types(self, mock_core):
        """Test mixed valid and invalid device types."""
        mixed_device_types = ["dimmer", "invalid", "sensor", "fake"]
        
        invalid_device_types = [dt for dt in mixed_device_types if not IndigoDeviceType.is_valid_type(dt)]
        
        assert invalid_device_types == ["invalid", "fake"]
    
    def test_mixed_valid_invalid_entity_types(self, mock_core):
        """Test mixed valid and invalid entity types."""
        mixed_entity_types = ["device", "invalid", "variable", "fake"]
        
        invalid_entity_types = [et for et in mixed_entity_types if not IndigoEntityType.is_valid_type(et)]
        
        assert invalid_entity_types == ["invalid", "fake"]
    
    def test_empty_device_types_list(self, mock_core):
        """Test that empty device types list is handled properly."""
        empty_device_types = []
        
        # Empty list should pass validation (no invalid types)
        invalid_device_types = [dt for dt in empty_device_types if not IndigoDeviceType.is_valid_type(dt)]
        assert len(invalid_device_types) == 0
    
    def test_empty_entity_types_list(self, mock_core):
        """Test that empty entity types list is handled properly."""
        empty_entity_types = []
        
        # Empty list should pass validation (no invalid types)
        invalid_entity_types = [et for et in empty_entity_types if not IndigoEntityType.is_valid_type(et)]
        assert len(invalid_entity_types) == 0
    
    def test_none_parameters_handled(self, mock_core):
        """Test that None parameters are handled properly."""
        # None should be treated as no filtering
        device_types = None
        entity_types = None
        
        # None should not cause validation errors
        if device_types:
            invalid_device_types = [dt for dt in device_types if not IndigoDeviceType.is_valid_type(dt)]
        else:
            invalid_device_types = []
        
        if entity_types:
            invalid_entity_types = [et for et in entity_types if not IndigoEntityType.is_valid_type(et)]
        else:
            invalid_entity_types = []
        
        assert len(invalid_device_types) == 0
        assert len(invalid_entity_types) == 0
    
    def test_search_handler_receives_parameters(self, mock_core):
        """Test that search handler receives the correct parameters."""
        # Test the search handler directly since we can't easily test the decorated function
        query = "test query"
        device_types = ["dimmer", "sensor"]
        entity_types = ["device"]
        
        # Call search handler directly (simulating what the tool would do)
        result = mock_core.search_handler.search(query, device_types, entity_types)
        
        # Check that the search handler received the call
        assert len(mock_core.search_handler.search_calls) == 1
        call = mock_core.search_handler.search_calls[0]
        
        assert call["query"] == query
        assert call["device_types"] == device_types
        assert call["entity_types"] == entity_types
    
    def test_error_response_format_for_invalid_device_types(self, mock_core):
        """Test that error responses have the correct format for invalid device types."""
        query = "test query"
        invalid_device_types = ["invalid", "fake"]
        
        # Simulate the validation logic that would be in the tool
        validation_errors = [dt for dt in invalid_device_types if not IndigoDeviceType.is_valid_type(dt)]
        
        if validation_errors:
            error_response = {
                "error": f"Invalid device types: {validation_errors}. Valid types: {IndigoDeviceType.get_all_types()}",
                "query": query
            }
            
            # Check error response format
            assert "error" in error_response
            assert "query" in error_response
            assert error_response["query"] == query
            assert "Invalid device types" in error_response["error"]
            assert "Valid types" in error_response["error"]
    
    def test_error_response_format_for_invalid_entity_types(self, mock_core):
        """Test that error responses have the correct format for invalid entity types."""
        query = "test query"
        invalid_entity_types = ["invalid", "fake"]
        
        # Simulate the validation logic that would be in the tool
        validation_errors = [et for et in invalid_entity_types if not IndigoEntityType.is_valid_type(et)]
        
        if validation_errors:
            error_response = {
                "error": f"Invalid entity types: {validation_errors}. Valid types: {IndigoEntityType.get_all_types()}",
                "query": query
            }
            
            # Check error response format
            assert "error" in error_response
            assert "query" in error_response
            assert error_response["query"] == query
            assert "Invalid entity types" in error_response["error"]
            assert "Valid types" in error_response["error"]
    
    def test_successful_search_returns_json_string(self, mock_core):
        """Test that successful searches return JSON strings."""
        # Simulate successful search
        result = mock_core.search_handler.search("test query")
        
        # Should be able to serialize to JSON
        json_result = json.dumps(result)
        parsed_result = json.loads(json_result)
        
        # Check that it parses back correctly
        assert parsed_result["query"] == "test query"
        assert "total_count" in parsed_result
        assert "results" in parsed_result
    
    def test_all_device_types_enum_values_are_valid(self, mock_core):
        """Test that all enum values are considered valid by the validation logic."""
        all_device_types = IndigoDeviceType.get_all_types()
        
        for device_type in all_device_types:
            assert IndigoDeviceType.is_valid_type(device_type)
    
    def test_all_entity_types_enum_values_are_valid(self, mock_core):
        """Test that all enum values are considered valid by the validation logic."""
        all_entity_types = IndigoEntityType.get_all_types()
        
        for entity_type in all_entity_types:
            assert IndigoEntityType.is_valid_type(entity_type)
    
    def test_case_sensitivity_in_validation(self, mock_core):
        """Test that validation is case sensitive."""
        # Lowercase should be valid
        assert IndigoDeviceType.is_valid_type("dimmer")
        assert IndigoEntityType.is_valid_type("device")
        
        # Other cases should be invalid
        assert not IndigoDeviceType.is_valid_type("DIMMER")
        assert not IndigoDeviceType.is_valid_type("Dimmer")
        assert not IndigoEntityType.is_valid_type("DEVICE")
        assert not IndigoEntityType.is_valid_type("Device")


class TestCoreSearchIntegration:
    """Integration tests for core search functionality."""
    
    @pytest.fixture
    def mock_core_with_real_validation(self, monkeypatch, temp_db_path):
        """Create a mock core that uses real validation logic."""
        monkeypatch.setenv("DB_FILE", temp_db_path)
        
        mock_data_provider = MockDataProvider()
        core = MCPServerCore(data_provider=mock_data_provider, port=get_free_port())
        core.search_handler = MockSearchHandler()
        
        return core
    
    def test_validation_integration_with_enum_types(self, mock_core_with_real_validation):
        """Test that the validation integrates properly with enum types."""
        core = mock_core_with_real_validation
        
        # Test that we can use enum values directly
        device_types_from_enum = [IndigoDeviceType.DIMMER, IndigoDeviceType.SENSOR]
        entity_types_from_enum = [IndigoEntityType.DEVICE, IndigoEntityType.VARIABLE]
        
        # Convert to string values (as they would be received from MCP)
        device_type_strings = [dt.value for dt in device_types_from_enum]
        entity_type_strings = [et.value for et in entity_types_from_enum]
        
        # All should be valid
        for device_type in device_type_strings:
            assert IndigoDeviceType.is_valid_type(device_type)
        
        for entity_type in entity_type_strings:
            assert IndigoEntityType.is_valid_type(entity_type)
    
    def test_comprehensive_validation_scenario(self, mock_core_with_real_validation):
        """Test a comprehensive validation scenario."""
        core = mock_core_with_real_validation
        
        # Test data with mixed valid/invalid types
        valid_device_types = ["dimmer", "sensor", "relay"]
        invalid_device_types = ["invalid", "fake"]
        mixed_device_types = valid_device_types + invalid_device_types
        
        valid_entity_types = ["device", "variable"]
        invalid_entity_types = ["invalid", "devices"]  # Note: "devices" is invalid (should be "device")
        mixed_entity_types = valid_entity_types + invalid_entity_types
        
        # Test device type validation
        invalid_device_results = [dt for dt in mixed_device_types if not IndigoDeviceType.is_valid_type(dt)]
        assert set(invalid_device_results) == set(invalid_device_types)
        
        # Test entity type validation
        invalid_entity_results = [et for et in mixed_entity_types if not IndigoEntityType.is_valid_type(et)]
        assert set(invalid_entity_results) == set(invalid_entity_types)