"""
Tests for ListHandlers class functionality.
"""

import pytest
from unittest.mock import Mock, MagicMock
from mcp_server.handlers.list_handlers import ListHandlers
from tests.fixtures.real_device_fixtures import RealDeviceFixtures


class TestListHandlers:
    """Test cases for ListHandlers class."""
    
    @pytest.fixture
    def mock_data_provider(self):
        """Create a mock data provider with realistic data."""
        provider = Mock()
        provider.get_all_devices.return_value = RealDeviceFixtures.get_sample_devices()
        provider.get_all_variables.return_value = RealDeviceFixtures.get_sample_variables()
        provider.get_all_actions.return_value = RealDeviceFixtures.get_sample_action_groups()
        return provider
    
    @pytest.fixture
    def list_handlers(self, mock_data_provider):
        """Create ListHandlers instance with mock data provider."""
        return ListHandlers(mock_data_provider)
    
    def test_list_all_devices_no_filter(self, list_handlers):
        """Test listing all devices without filtering."""
        result = list_handlers.list_all_devices()
        
        assert len(result) == 8  # All sample devices
        assert all(isinstance(device, dict) for device in result)
        assert all("id" in device and "name" in device for device in result)
    
    def test_list_all_devices_with_state_filter(self, list_handlers):
        """Test listing devices with state filter."""
        # Test devices that are on
        result = list_handlers.list_all_devices(state_filter={"onState": True})
        
        assert len(result) == 4  # Devices that are on
        assert all(device.get("onState") is True for device in result)
        
        # Test devices with brightness > 60
        result = list_handlers.list_all_devices(
            state_filter={"brightnessLevel": {"gt": 60}}
        )
        
        assert len(result) == 2  # Devices with brightness > 60
        brightness_values = [device.get("brightnessLevel", 0) for device in result]
        assert all(b > 60 for b in brightness_values if b is not None)
    
    def test_list_all_devices_with_device_type_filter(self, list_handlers):
        """Test listing devices with device type filter."""
        # Test dimmer devices only
        result = list_handlers.list_all_devices(device_types=["dimmer"])
        
        assert len(result) == 4  # All dimmer devices
        assert all(device["class"] == "indigo.DimmerDevice" for device in result)
        
        # Test relay devices only
        result = list_handlers.list_all_devices(device_types=["relay"])
        
        assert len(result) == 2  # All relay devices
        assert all(device["class"] == "indigo.RelayDevice" for device in result)
    
    def test_list_all_devices_combined_filters(self, list_handlers):
        """Test listing devices with both state and device type filters."""
        result = list_handlers.list_all_devices(
            state_filter={"onState": True},
            device_types=["dimmer"]
        )
        
        # Should find only dimmer devices that are on
        assert len(result) == 3  # Dimmer devices that are on
        assert all(device["class"] == "indigo.DimmerDevice" for device in result)
        assert all(device.get("onState") is True for device in result)
    
    def test_list_all_variables(self, list_handlers):
        """Test listing all variables."""
        result = list_handlers.list_all_variables()
        
        assert len(result) == 4  # All sample variables
        assert all(isinstance(var, dict) for var in result)
        assert all("id" in var and "name" in var and "value" in var for var in result)
        
        # Check specific variables exist
        var_names = [var["name"] for var in result]
        assert "alarm_enabled" in var_names
        assert "house_mode" in var_names
    
    def test_list_all_action_groups(self, list_handlers):
        """Test listing all action groups."""
        result = list_handlers.list_all_action_groups()
        
        assert len(result) == 4  # All sample action groups
        assert all(isinstance(action, dict) for action in result)
        assert all("id" in action and "name" in action for action in result)
        
        # Check specific action groups exist
        action_names = [action["name"] for action in result]
        assert "Good Night Scene" in action_names
        assert "Morning Routine" in action_names
    
    def test_get_devices_by_state_simple(self, list_handlers):
        """Test get_devices_by_state with simple conditions."""
        result = list_handlers.get_devices_by_state({"onState": True})
        
        assert "devices" in result
        assert "count" in result
        assert "state_conditions" in result
        assert "summary" in result
        
        assert result["count"] == 4
        assert len(result["devices"]) == 4
        assert result["state_conditions"] == {"onState": True}
        assert "Found 4 devices matching state conditions" in result["summary"]
    
    def test_get_devices_by_state_with_device_types(self, list_handlers):
        """Test get_devices_by_state with device type filtering."""
        result = list_handlers.get_devices_by_state(
            state_conditions={"onState": True},
            device_types=["dimmer"]
        )
        
        assert result["count"] == 3  # Dimmer devices that are on
        assert len(result["devices"]) == 3
        assert result["device_types"] == ["dimmer"]
        assert "types: dimmer" in result["summary"]
        
        # All devices should be dimmers
        assert all(device["class"] == "indigo.DimmerDevice" for device in result["devices"])
    
    def test_get_devices_by_state_complex_conditions(self, list_handlers):
        """Test get_devices_by_state with complex conditions."""
        result = list_handlers.get_devices_by_state({
            "brightnessLevel": {"gt": 50, "lte": 90}
        })
        
        assert result["count"] == 2  # Devices with brightness 51-90%
        brightness_levels = [
            device.get("brightnessLevel", 0) 
            for device in result["devices"]
        ]
        assert all(50 < b <= 90 for b in brightness_levels if b is not None)
    
    def test_get_devices_by_state_no_matches(self, list_handlers):
        """Test get_devices_by_state with conditions that match nothing."""
        result = list_handlers.get_devices_by_state({
            "brightnessLevel": {"gt": 100}  # No devices > 100%
        })
        
        assert result["count"] == 0
        assert len(result["devices"]) == 0
        assert "Found 0 devices matching state conditions" in result["summary"]
    
    def test_error_handling_data_provider_failure(self):
        """Test error handling when data provider fails."""
        mock_provider = Mock()
        mock_provider.get_all_devices.side_effect = Exception("Database connection failed")
        
        handlers = ListHandlers(mock_provider)
        
        with pytest.raises(Exception) as exc_info:
            handlers.list_all_devices()
        
        assert "Database connection failed" in str(exc_info.value)
    
    def test_error_handling_variables_failure(self):
        """Test error handling when variable fetching fails."""
        mock_provider = Mock()
        mock_provider.get_all_variables.side_effect = Exception("Variable fetch failed")
        
        handlers = ListHandlers(mock_provider)
        
        with pytest.raises(Exception) as exc_info:
            handlers.list_all_variables()
        
        assert "Variable fetch failed" in str(exc_info.value)
    
    def test_error_handling_actions_failure(self):
        """Test error handling when action group fetching fails."""
        mock_provider = Mock()
        mock_provider.get_all_actions.side_effect = Exception("Action fetch failed")
        
        handlers = ListHandlers(mock_provider)
        
        with pytest.raises(Exception) as exc_info:
            handlers.list_all_action_groups()
        
        assert "Action fetch failed" in str(exc_info.value)
    
    def test_logging_functionality(self, list_handlers, caplog):
        """Test that appropriate logging occurs."""
        # Test device listing with state filter
        list_handlers.list_all_devices(state_filter={"onState": True})
        
        # Should have info log about returning devices
        assert "Returning" in caplog.text
        assert "devices" in caplog.text
    
    def test_device_classification_integration(self, list_handlers):
        """Test that device classification works with real device types."""
        # This tests the integration with DeviceClassifier
        result = list_handlers.list_all_devices(device_types=["dimmer"])
        
        # Should classify all dimmer devices correctly
        assert len(result) == 4
        assert all("Dimmer" in device["class"] for device in result)
    
    def test_state_filter_integration(self, list_handlers):
        """Test integration with StateFilter class."""
        # Test complex state conditions
        result = list_handlers.list_all_devices(state_filter={
            "onState": True,
            "brightnessLevel": {"gte": 50}
        })
        
        # Should find devices that are on AND have brightness >= 50
        assert len(result) == 3
        for device in result:
            assert device.get("onState") is True
            brightness = device.get("brightnessLevel")
            if brightness is not None:
                assert brightness >= 50