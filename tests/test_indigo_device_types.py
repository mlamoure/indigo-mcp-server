"""
Tests for Indigo device type enums.
"""

import pytest
from mcp_server.common.indigo_device_types import IndigoDeviceType, IndigoEntityType


class TestIndigoDeviceType:
    """Test cases for the IndigoDeviceType enum."""
    
    def test_enum_values(self):
        """Test that all expected device types are defined."""
        expected_types = [
            "dimmer", "relay", "sensor", "multiio", 
            "speedcontrol", "sprinkler", "thermostat", "device"
        ]
        
        for device_type in expected_types:
            assert hasattr(IndigoDeviceType, device_type.upper())
            assert getattr(IndigoDeviceType, device_type.upper()).value == device_type
    
    def test_string_behavior(self):
        """Test that enum values behave as strings."""
        dimmer = IndigoDeviceType.DIMMER
        assert dimmer.value == "dimmer"
        assert dimmer == "dimmer"
        assert "dimmer" == dimmer
    
    def test_get_all_types(self):
        """Test get_all_types class method."""
        all_types = IndigoDeviceType.get_all_types()
        
        expected_types = [
            "dimmer", "relay", "sensor", "multiio", 
            "speedcontrol", "sprinkler", "thermostat", "device"
        ]
        
        assert isinstance(all_types, list)
        assert len(all_types) == len(expected_types)
        
        for device_type in expected_types:
            assert device_type in all_types
    
    def test_is_valid_type(self):
        """Test is_valid_type class method."""
        # Test valid types
        valid_types = [
            "dimmer", "relay", "sensor", "multiio", 
            "speedcontrol", "sprinkler", "thermostat", "device"
        ]
        
        for device_type in valid_types:
            assert IndigoDeviceType.is_valid_type(device_type) is True
        
        # Test invalid types
        invalid_types = [
            "invalid", "light", "switch", "", "DIMMER", "Dimmer", None
        ]
        
        for device_type in invalid_types:
            assert IndigoDeviceType.is_valid_type(device_type) is False
    
    def test_case_sensitivity(self):
        """Test that validation is case sensitive."""
        assert IndigoDeviceType.is_valid_type("dimmer") is True
        assert IndigoDeviceType.is_valid_type("DIMMER") is False
        assert IndigoDeviceType.is_valid_type("Dimmer") is False
        assert IndigoDeviceType.is_valid_type("DiMmEr") is False
    
    def test_enum_iteration(self):
        """Test that we can iterate over the enum."""
        device_types = list(IndigoDeviceType)
        assert len(device_types) == 8  # Expected number of device types
        
        for device_type in device_types:
            assert isinstance(device_type, IndigoDeviceType)
            assert isinstance(device_type.value, str)


class TestIndigoEntityType:
    """Test cases for the IndigoEntityType enum."""
    
    def test_enum_values(self):
        """Test that all expected entity types are defined."""
        expected_types = ["device", "variable", "action"]
        
        for entity_type in expected_types:
            assert hasattr(IndigoEntityType, entity_type.upper())
            assert getattr(IndigoEntityType, entity_type.upper()).value == entity_type
    
    def test_string_behavior(self):
        """Test that enum values behave as strings."""
        device = IndigoEntityType.DEVICE
        assert device.value == "device"
        assert device == "device"
        assert "device" == device
    
    def test_get_all_types(self):
        """Test get_all_types class method."""
        all_types = IndigoEntityType.get_all_types()
        expected_types = ["device", "variable", "action"]
        
        assert isinstance(all_types, list)
        assert len(all_types) == len(expected_types)
        
        for entity_type in expected_types:
            assert entity_type in all_types
    
    def test_is_valid_type(self):
        """Test is_valid_type class method."""
        # Test valid types
        valid_types = ["device", "variable", "action"]
        
        for entity_type in valid_types:
            assert IndigoEntityType.is_valid_type(entity_type) is True
        
        # Test invalid types
        invalid_types = [
            "invalid", "devices", "variables", "actions", 
            "", "DEVICE", "Device", None
        ]
        
        for entity_type in invalid_types:
            assert IndigoEntityType.is_valid_type(entity_type) is False
    
    def test_case_sensitivity(self):
        """Test that validation is case sensitive."""
        assert IndigoEntityType.is_valid_type("device") is True
        assert IndigoEntityType.is_valid_type("DEVICE") is False
        assert IndigoEntityType.is_valid_type("Device") is False
        assert IndigoEntityType.is_valid_type("DeViCe") is False
    
    def test_enum_iteration(self):
        """Test that we can iterate over the enum."""
        entity_types = list(IndigoEntityType)
        assert len(entity_types) == 3  # Expected number of entity types
        
        for entity_type in entity_types:
            assert isinstance(entity_type, IndigoEntityType)
            assert isinstance(entity_type.value, str)
    
    def test_enum_completeness(self):
        """Test that we have all expected entity types."""
        entity_values = [et.value for et in IndigoEntityType]
        expected_values = ["device", "variable", "action"]
        
        assert set(entity_values) == set(expected_values)


class TestEnumUsagePatterns:
    """Test common usage patterns for the enums."""
    
    def test_device_type_in_list_comprehension(self):
        """Test using device type enum in list comprehensions."""
        test_types = ["dimmer", "invalid", "sensor", "fake"]
        
        valid_types = [t for t in test_types if IndigoDeviceType.is_valid_type(t)]
        assert valid_types == ["dimmer", "sensor"]
    
    def test_entity_type_in_list_comprehension(self):
        """Test using entity type enum in list comprehensions."""
        test_types = ["device", "invalid", "variable", "fake"]
        
        valid_types = [t for t in test_types if IndigoEntityType.is_valid_type(t)]
        assert valid_types == ["device", "variable"]
    
    def test_enum_values_as_dict_keys(self):
        """Test using enum values as dictionary keys."""
        device_config = {
            IndigoDeviceType.DIMMER: {"supports_brightness": True},
            IndigoDeviceType.SENSOR: {"supports_brightness": False},
        }
        
        assert device_config["dimmer"]["supports_brightness"] is True
        assert device_config["sensor"]["supports_brightness"] is False
    
    def test_enum_values_in_sets(self):
        """Test using enum values in sets."""
        supported_types = {
            IndigoDeviceType.DIMMER.value,
            IndigoDeviceType.RELAY.value,
            IndigoDeviceType.SENSOR.value
        }
        
        assert "dimmer" in supported_types
        assert "relay" in supported_types  
        assert "sensor" in supported_types
        assert "thermostat" not in supported_types