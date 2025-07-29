"""
Tests for Indigo device type enums.
"""

import pytest
from mcp_server.common.indigo_device_types import IndigoDeviceType, IndigoEntityType, DeviceClassifier


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


class TestDeviceClassifier:
    """Test cases for the DeviceClassifier class."""
    
    def test_classify_device_by_class(self):
        """Test device classification based on device class."""
        test_cases = [
            {"class": "indigo.DimmerDevice", "expected": "dimmer"},
            {"class": "indigo.RelayDevice", "expected": "relay"},
            {"class": "indigo.SensorDevice", "expected": "sensor"},
            {"class": "indigo.MultiIODevice", "expected": "multiio"},
            {"class": "indigo.SpeedControlDevice", "expected": "speedcontrol"},
            {"class": "indigo.SprinklerDevice", "expected": "sprinkler"},
            {"class": "indigo.ThermostatDevice", "expected": "thermostat"},
            {"class": "indigo.Device", "expected": "device"},
        ]
        
        for test_case in test_cases:
            device = {"class": test_case["class"], "deviceTypeId": "generic"}
            result = DeviceClassifier.classify_device(device)
            assert result == test_case["expected"], f"Failed for {test_case['class']}"
    
    def test_classify_device_by_devicetype_id_patterns(self):
        """Test device classification based on deviceTypeId patterns."""
        test_cases = [
            # Dimmer patterns
            {"deviceTypeId": "ra2Dimmer", "expected": "dimmer"},
            {"deviceTypeId": "zwColorDimmerType", "expected": "dimmer"},
            {"deviceTypeId": "HAdimmerType", "expected": "dimmer"},
            {"deviceTypeId": "hueBulb", "expected": "dimmer"},
            {"deviceTypeId": "lightStrips", "expected": "dimmer"},
            
            # Relay patterns
            {"deviceTypeId": "zwRelayType", "expected": "relay"},
            {"deviceTypeId": "ra2Switch", "expected": "relay"},
            {"deviceTypeId": "smartPlug", "expected": "relay"},
            {"deviceTypeId": "outletDevice", "expected": "relay"},
            
            # Sensor patterns
            {"deviceTypeId": "motionSensor", "expected": "sensor"},
            {"deviceTypeId": "temperatureDetector", "expected": "sensor"},
            {"deviceTypeId": "humiditySensor", "expected": "sensor"},
            
            # Thermostat patterns
            {"deviceTypeId": "nestThermostat", "expected": "thermostat"},
            {"deviceTypeId": "hvacSystem", "expected": "thermostat"},
            {"deviceTypeId": "climateControl", "expected": "thermostat"},
            
            # Fan patterns
            {"deviceTypeId": "ha_fan", "expected": "speedcontrol"},
            {"deviceTypeId": "speedController", "expected": "speedcontrol"},
            
            # Sprinkler patterns
            {"deviceTypeId": "sprinklerZone", "expected": "sprinkler"},
            {"deviceTypeId": "irrigationSystem", "expected": "sprinkler"},
            {"deviceTypeId": "waterController", "expected": "sprinkler"},
        ]
        
        for test_case in test_cases:
            device = {"class": "unknownClass", "deviceTypeId": test_case["deviceTypeId"]}
            result = DeviceClassifier.classify_device(device)
            assert result == test_case["expected"], f"Failed for {test_case['deviceTypeId']}"
    
    def test_classify_device_real_examples(self):
        """Test classification with real device examples from your system."""
        test_devices = [
            # Real devices from your device list
            {
                "name": "Kitchen Ceiling Lights",
                "class": "indigo.DimmerDevice",
                "deviceTypeId": "ra2Dimmer",
                "expected": "dimmer"
            },
            {
                "name": "Outdoor Bollard - Left Side 1",
                "class": "indigo.DimmerDevice",
                "deviceTypeId": "hueBulb",
                "expected": "dimmer"
            },
            {
                "name": "Garage Lights",
                "class": "indigo.RelayDevice",
                "deviceTypeId": "ra2Switch",
                "expected": "relay"
            },
            {
                "name": "Living Room Lamp",
                "class": "indigo.RelayDevice",
                "deviceTypeId": "zwRelayType",
                "expected": "relay"
            },
            {
                "name": "Kitchen Motion Sensor",
                "class": "indigo.SensorDevice",
                "deviceTypeId": "zwOnOffSensorType",
                "expected": "sensor"
            },
            {
                "name": "Upstairs Nest Thermostat",
                "class": "indigo.ThermostatDevice",
                "deviceTypeId": "nestThermostat",
                "expected": "thermostat"
            },
            {
                "name": "Master Bedroom Fan",
                "class": "indigo.SpeedControlDevice",
                "deviceTypeId": "ha_fan",
                "expected": "speedcontrol"
            },
        ]
        
        for device in test_devices:
            result = DeviceClassifier.classify_device(device)
            assert result == device["expected"], f"Failed for {device['name']}"
    
    def test_classify_device_class_priority(self):
        """Test that device class takes priority over deviceTypeId patterns."""
        # Device class should override deviceTypeId patterns
        device = {
            "class": "indigo.DimmerDevice",
            "deviceTypeId": "sensorType"  # This would normally classify as sensor
        }
        result = DeviceClassifier.classify_device(device)
        assert result == "dimmer"
    
    def test_classify_device_fallback(self):
        """Test fallback to base device type for unknown devices."""
        test_devices = [
            {"class": "unknown.Device", "deviceTypeId": "unknownType"},
            {"class": "", "deviceTypeId": ""},
            {},  # Empty device
            {"deviceTypeId": "randomStuff"},
        ]
        
        for device in test_devices:
            result = DeviceClassifier.classify_device(device)
            assert result == "device"
    
    def test_filter_devices_by_type(self):
        """Test filtering devices by type."""
        test_devices = [
            {"name": "Dimmer 1", "class": "indigo.DimmerDevice", "deviceTypeId": "ra2Dimmer"},
            {"name": "Dimmer 2", "class": "indigo.DimmerDevice", "deviceTypeId": "hueBulb"},
            {"name": "Relay 1", "class": "indigo.RelayDevice", "deviceTypeId": "zwRelayType"},
            {"name": "Sensor 1", "class": "indigo.SensorDevice", "deviceTypeId": "motionSensor"},
            {"name": "Unknown", "class": "unknownClass", "deviceTypeId": "unknownType"},
        ]
        
        # Test filtering dimmers
        dimmers = DeviceClassifier.filter_devices_by_type(test_devices, "dimmer")
        assert len(dimmers) == 2
        assert all(d["name"].startswith("Dimmer") for d in dimmers)
        
        # Test filtering relays
        relays = DeviceClassifier.filter_devices_by_type(test_devices, "relay")
        assert len(relays) == 1
        assert relays[0]["name"] == "Relay 1"
        
        # Test filtering sensors
        sensors = DeviceClassifier.filter_devices_by_type(test_devices, "sensor")
        assert len(sensors) == 1
        assert sensors[0]["name"] == "Sensor 1"
        
        # Test filtering devices (fallback type)
        devices = DeviceClassifier.filter_devices_by_type(test_devices, "device")
        assert len(devices) == 1
        assert devices[0]["name"] == "Unknown"
        
        # Test invalid device type
        invalid = DeviceClassifier.filter_devices_by_type(test_devices, "invalid")
        assert len(invalid) == 0
    
    def test_get_device_type_distribution(self):
        """Test getting device type distribution."""
        test_devices = [
            {"class": "indigo.DimmerDevice", "deviceTypeId": "ra2Dimmer"},
            {"class": "indigo.DimmerDevice", "deviceTypeId": "hueBulb"},
            {"class": "indigo.DimmerDevice", "deviceTypeId": "zwColorDimmerType"},
            {"class": "indigo.RelayDevice", "deviceTypeId": "zwRelayType"},
            {"class": "indigo.RelayDevice", "deviceTypeId": "ra2Switch"},
            {"class": "indigo.SensorDevice", "deviceTypeId": "motionSensor"},
            {"class": "unknownClass", "deviceTypeId": "unknownType"},
        ]
        
        distribution = DeviceClassifier.get_device_type_distribution(test_devices)
        
        assert distribution["dimmer"] == 3
        assert distribution["relay"] == 2
        assert distribution["sensor"] == 1
        assert distribution["device"] == 1
        assert len(distribution) == 4
    
    def test_case_insensitive_patterns(self):
        """Test that deviceTypeId pattern matching is case insensitive."""
        test_cases = [
            {"deviceTypeId": "RA2DIMMER", "expected": "dimmer"},
            {"deviceTypeId": "ZwRelayType", "expected": "relay"},
            {"deviceTypeId": "MOTIONSENSOR", "expected": "sensor"},
            {"deviceTypeId": "HueBulb", "expected": "dimmer"},
        ]
        
        for test_case in test_cases:
            device = {"class": "unknownClass", "deviceTypeId": test_case["deviceTypeId"]}
            result = DeviceClassifier.classify_device(device)
            assert result == test_case["expected"], f"Failed for {test_case['deviceTypeId']}"
    
    def test_complex_devicetype_patterns(self):
        """Test complex deviceTypeId patterns with multiple words."""
        test_cases = [
            {"deviceTypeId": "smartLightDimmerController", "expected": "dimmer"},
            {"deviceTypeId": "outdoorMotionDetectorSensor", "expected": "sensor"},
            {"deviceTypeId": "wallSwitchRelayDevice", "expected": "relay"},
            {"deviceTypeId": "ceilingFanSpeedControl", "expected": "speedcontrol"},
        ]
        
        for test_case in test_cases:
            device = {"class": "unknownClass", "deviceTypeId": test_case["deviceTypeId"]}
            result = DeviceClassifier.classify_device(device)
            assert result == test_case["expected"], f"Failed for {test_case['deviceTypeId']}"