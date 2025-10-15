"""
Tests for new list tools (list_devices, list_variables, list_action_groups, get_devices_by_state).

NOTE: These tests are currently disabled as they reference the old MCPServerCore
which was replaced by MCPHandler during the IWS migration. These tests need to be
updated to work with the new MCPHandler architecture or removed if functionality
is covered by other tests.
"""

import json
import pytest
from unittest.mock import Mock, patch

# Mark all tests in this module as skipped
pytestmark = pytest.mark.skip(reason="Needs update for IWS migration: MCPServerCore → MCPHandler")

# Legacy import - needs updating
try:
    from mcp_server.core import MCPServerCore
except ImportError:
    # Module no longer exists after IWS migration
    MCPServerCore = None
from tests.fixtures.real_device_fixtures import RealDeviceFixtures


class TestListTools:
    """Test cases for new list tools."""
    
    @pytest.fixture
    def mock_data_provider(self):
        """Create a mock data provider with realistic data."""
        provider = Mock()
        provider.get_all_devices.return_value = RealDeviceFixtures.get_sample_devices()
        provider.get_all_variables.return_value = RealDeviceFixtures.get_sample_variables()
        provider.get_all_actions.return_value = RealDeviceFixtures.get_sample_action_groups()
        return provider
    
    @pytest.fixture
    def mock_vector_store(self):
        """Create a mock vector store."""
        store = Mock()
        store.search.return_value = ([], {"total_found": 0, "total_returned": 0, "truncated": False})
        return store
    
    @pytest.fixture
    def list_handlers(self, mock_data_provider):
        """Create ListHandlers instance directly for testing."""
        from mcp_server.handlers.list_handlers import ListHandlers
        from unittest.mock import Mock
        
        logger = Mock()
        return ListHandlers(
            data_provider=mock_data_provider,
            logger=logger
        )
    
    def test_list_devices_no_filter(self, list_handlers):
        """Test list_devices tool without filtering."""
        # Get all devices using the list handler
        result_json = list_handlers.list_all_devices()
        result = {
            "devices": result_json,
            "count": len(result_json),
            "state_filter": None
        }
        
        assert len(result["devices"]) == 8
        assert result["count"] == 8
        assert result["state_filter"] is None
        
        # Verify device structure
        device = result["devices"][0]
        required_fields = ["id", "name", "class", "onState"]
        assert all(field in device for field in required_fields)
    
    def test_list_devices_with_state_filter(self, list_handlers):
        """Test list_devices tool with state filtering."""
        state_filter = {"onState": True}
        devices = list_handlers.list_all_devices(state_filter=state_filter)
        result = {
            "devices": devices,
            "count": len(devices),
            "state_filter": state_filter
        }
        
        assert result["count"] == 4  # Devices that are on
        assert result["state_filter"] == {"onState": True}
        
        # All returned devices should be on
        assert all(device.get("onState") is True for device in result["devices"])
    
    def test_list_devices_complex_state_filter(self, list_handlers):
        """Test list_devices with complex state filtering."""
        state_filter = {"brightnessLevel": {"gt": 60}}
        devices = list_handlers.list_all_devices(state_filter=state_filter)
        result = {
            "devices": devices,
            "count": len(devices),
            "state_filter": state_filter
        }
        
        assert result["count"] == 2  # Devices with brightness > 60
        brightness_levels = [
            device.get("brightnessLevel", 0) 
            for device in result["devices"]
        ]
        assert all(b > 60 for b in brightness_levels if b is not None)
    
    def test_list_variables(self, list_handlers):
        """Test list_variables tool."""
        variables = list_handlers.list_all_variables()
        result = {
            "variables": variables,
            "count": len(variables)
        }
        
        assert result["count"] == 4
        assert len(result["variables"]) == 4
        
        # Verify variable structure
        variable = result["variables"][0]
        required_fields = ["id", "name", "value", "readOnly"]
        assert all(field in variable for field in required_fields)
        
        # Check specific variables
        var_names = [var["name"] for var in result["variables"]]
        assert "alarm_enabled" in var_names
        assert "house_mode" in var_names
    
    def test_list_action_groups(self, list_handlers):
        """Test list_action_groups tool."""
        actions = list_handlers.list_all_action_groups()
        result = {
            "action_groups": actions,
            "count": len(actions)
        }
        
        assert result["count"] == 4
        assert len(result["action_groups"]) == 4
        
        # Verify action group structure
        action = result["action_groups"][0]
        required_fields = ["id", "name", "description"]
        assert all(field in action for field in required_fields)
        
        # Check specific action groups
        action_names = [action["name"] for action in result["action_groups"]]
        assert "Good Night Scene" in action_names
        assert "Morning Routine" in action_names
    
    def test_get_devices_by_state_simple(self, list_handlers):
        """Test get_devices_by_state tool with simple conditions."""
        result = list_handlers.get_devices_by_state({"onState": True})
        
        assert "devices" in result
        assert "count" in result
        assert "state_conditions" in result
        assert "summary" in result
        assert "device_types" in result
        
        assert result["count"] == 4
        assert len(result["devices"]) == 4
        assert result["state_conditions"] == {"onState": True}
        assert result["device_types"] is None
        assert "Found 4 devices matching state conditions" in result["summary"]
    
    def test_get_devices_by_state_with_device_types(self, list_handlers):
        """Test get_devices_by_state with device type filtering."""
        result = list_handlers.get_devices_by_state(
            state_conditions={"onState": True},
            device_types=["dimmer"]
        )
        
        assert result["count"] == 3  # Dimmer devices that are on
        assert result["device_types"] == ["dimmer"]
        assert "types: dimmer" in result["summary"]
        
        # All devices should be dimmers
        assert all(device["class"] == "indigo.DimmerDevice" for device in result["devices"])
    
    def test_get_devices_by_state_complex_conditions(self, list_handlers):
        """Test get_devices_by_state with complex conditions."""
        result = list_handlers.get_devices_by_state({
            "brightnessLevel": {"gt": 50, "lte": 90},
            "onState": True
        })
        
        # Should find on devices with brightness 51-90%
        assert result["count"] == 2
        
        for device in result["devices"]:
            assert device.get("onState") is True
            brightness = device.get("brightnessLevel")
            if brightness is not None:
                assert 50 < brightness <= 90
    
    def test_get_devices_by_state_no_matches(self, list_handlers):
        """Test get_devices_by_state with no matching devices."""
        result = list_handlers.get_devices_by_state({
            "brightnessLevel": {"gt": 100}  # No devices > 100%
        })
        
        assert result["count"] == 0
        assert len(result["devices"]) == 0
        assert "Found 0 devices" in result["summary"]
    
    def test_json_serialization(self, list_handlers):
        """Test that all tool results can be JSON serialized."""
        # Test list_devices
        devices = list_handlers.list_all_devices()
        devices_result = {"devices": devices, "count": len(devices), "state_filter": None}
        json_str = json.dumps(devices_result)
        assert json_str is not None
        
        # Test list_variables
        variables = list_handlers.list_all_variables()
        variables_result = {"variables": variables, "count": len(variables)}
        json_str = json.dumps(variables_result)
        assert json_str is not None
        
        # Test list_action_groups
        actions = list_handlers.list_all_action_groups()
        actions_result = {"action_groups": actions, "count": len(actions)}
        json_str = json.dumps(actions_result)
        assert json_str is not None
        
        # Test get_devices_by_state
        state_result = list_handlers.get_devices_by_state({"onState": True})
        json_str = json.dumps(state_result)
        assert json_str is not None
    
    def test_realistic_use_cases(self, list_handlers):
        """Test realistic use cases from fixtures."""
        scenarios = RealDeviceFixtures.get_state_filter_test_scenarios()
        
        # Test "lights that are on" scenario
        lights_on = scenarios["lights_that_are_on"]
        result = list_handlers.get_devices_by_state(
            state_conditions=lights_on["state_filter"],
            device_types=lights_on["device_types"]
        )
        
        assert result["count"] == lights_on["expected_count"]
        device_ids = [d["id"] for d in result["devices"]]
        assert set(device_ids) == set(lights_on["expected_ids"])
        
        # Test "dimmed lights" scenario  
        dimmed = scenarios["dimmed_lights"]
        result = list_handlers.get_devices_by_state(
            state_conditions=dimmed["state_filter"],
            device_types=dimmed["device_types"]
        )
        
        assert result["count"] == dimmed["expected_count"]
        device_ids = [d["id"] for d in result["devices"]]
        assert set(device_ids) == set(dimmed["expected_ids"])
    
    def test_performance_with_large_datasets(self, list_handlers):
        """Test performance characteristics with larger datasets."""
        # Create a larger mock dataset
        large_device_list = RealDeviceFixtures.get_sample_devices() * 100  # 800 devices
        list_handlers.data_provider.get_all_devices.return_value = large_device_list
        
        # Test that operations complete in reasonable time
        import time
        start_time = time.time()
        
        devices = list_handlers.list_all_devices(
            state_filter={"onState": True}
        )
        
        end_time = time.time()
        
        # Should complete in under 1 second
        assert (end_time - start_time) < 1.0
        
        # Should still return correct results
        assert len(devices) == 400  # 4 devices * 100 repetitions
    
    def test_edge_cases(self, list_handlers):
        """Test edge cases and error conditions."""
        # Empty state filter should return all devices
        result = list_handlers.get_devices_by_state({})
        assert result["count"] == 8  # All devices
        
        # Invalid device type should return no devices
        result = list_handlers.get_devices_by_state(
            state_conditions={"onState": True},
            device_types=["nonexistent_type"]
        )
        assert result["count"] == 0
        
        # Complex impossible condition
        result = list_handlers.get_devices_by_state({
            "onState": True,
            "onState": False  # This would be contradictory in real usage
        })
        # Should handle gracefully (last value wins in dict)
        assert result["count"] in [0, 3, 4]  # Depends on implementation