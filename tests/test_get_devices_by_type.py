"""
Tests for the GetDevicesByTypeHandler.
"""

import pytest
from unittest.mock import Mock, MagicMock
from mcp_server.tools.get_devices_by_type import GetDevicesByTypeHandler
from mcp_server.common.indigo_device_types import IndigoDeviceType


class TestGetDevicesByTypeHandler:
    """Test cases for the GetDevicesByTypeHandler class."""
    
    @pytest.fixture
    def mock_data_provider(self):
        """Create a mock data provider with test devices."""
        mock_provider = Mock()
        
        # Sample devices representing different types found in your system
        test_devices = [
            # Dimmers
            {
                "name": "Kitchen Ceiling Lights",
                "class": "indigo.DimmerDevice",
                "deviceTypeId": "ra2Dimmer",
                "id": 821077573
            },
            {
                "name": "Outdoor Bollard - Left Side 1",
                "class": "indigo.DimmerDevice", 
                "deviceTypeId": "hueBulb",
                "id": 1906147201
            },
            {
                "name": "076 - Nightlight",
                "class": "indigo.DimmerDevice",
                "deviceTypeId": "zwColorDimmerType",
                "id": 1385203939
            },
            
            # Relays
            {
                "name": "Garage Lights",
                "class": "indigo.RelayDevice",
                "deviceTypeId": "ra2Switch",
                "id": 904690844
            },
            {
                "name": "Living Room Lamp",
                "class": "indigo.RelayDevice",
                "deviceTypeId": "zwRelayType",
                "id": 1183208037
            },
            
            # Sensors
            {
                "name": "Kitchen Motion Sensor",
                "class": "indigo.SensorDevice",
                "deviceTypeId": "zwOnOffSensorType",
                "id": 501859105
            },
            {
                "name": "Kitchen Temperature",
                "class": "indigo.SensorDevice",
                "deviceTypeId": "zwValueSensorType",
                "id": 1930099152
            },
            
            # Thermostats
            {
                "name": "Upstairs Nest Thermostat",
                "class": "indigo.ThermostatDevice",
                "deviceTypeId": "nestThermostat",
                "id": 585059899
            },
            
            # Speed control (fans)
            {
                "name": "Master Bedroom Fan",
                "class": "indigo.SpeedControlDevice",
                "deviceTypeId": "ha_fan",
                "id": 432135992
            },
            
            # Sprinkler
            {
                "name": "Sprinklers",
                "class": "indigo.SprinklerDevice", 
                "deviceTypeId": "sprinkler",
                "id": 93916715
            },
            
            # Base device (unknown type)
            {
                "name": "Unknown Device",
                "class": "indigo.Device",
                "deviceTypeId": "unknownType",
                "id": 999999999
            }
        ]
        
        mock_provider.get_all_devices_unfiltered.return_value = test_devices
        return mock_provider
    
    @pytest.fixture
    def handler(self, mock_data_provider):
        """Create a GetDevicesByTypeHandler with mock data provider."""
        mock_logger = Mock()
        return GetDevicesByTypeHandler(
            data_provider=mock_data_provider,
            logger=mock_logger
        )
    
    def test_get_devices_dimmer_type(self, handler):
        """Test retrieving all dimmer devices."""
        result = handler.get_devices("dimmer")
        
        assert result["success"] is True
        assert result["device_type"] == "dimmer"
        assert result["count"] == 3
        
        device_names = [device["name"] for device in result["devices"]]
        assert "Kitchen Ceiling Lights" in device_names
        assert "Outdoor Bollard - Left Side 1" in device_names
        assert "076 - Nightlight" in device_names
        
        # Verify all returned devices are actually dimmers
        for device in result["devices"]:
            assert device["class"] == "indigo.DimmerDevice"
    
    def test_get_devices_relay_type(self, handler):
        """Test retrieving all relay devices."""
        result = handler.get_devices("relay")
        
        assert result["success"] is True
        assert result["device_type"] == "relay"
        assert result["count"] == 2
        
        device_names = [device["name"] for device in result["devices"]]
        assert "Garage Lights" in device_names
        assert "Living Room Lamp" in device_names
        
        # Verify all returned devices are actually relays
        for device in result["devices"]:
            assert device["class"] == "indigo.RelayDevice"
    
    def test_get_devices_sensor_type(self, handler):
        """Test retrieving all sensor devices.""" 
        result = handler.get_devices("sensor")
        
        assert result["success"] is True
        assert result["device_type"] == "sensor"
        assert result["count"] == 2
        
        device_names = [device["name"] for device in result["devices"]]
        assert "Kitchen Motion Sensor" in device_names
        assert "Kitchen Temperature" in device_names
        
        # Verify all returned devices are actually sensors
        for device in result["devices"]:
            assert device["class"] == "indigo.SensorDevice"
    
    def test_get_devices_thermostat_type(self, handler):
        """Test retrieving all thermostat devices."""
        result = handler.get_devices("thermostat")
        
        assert result["success"] is True
        assert result["device_type"] == "thermostat"
        assert result["count"] == 1
        
        device_names = [device["name"] for device in result["devices"]]
        assert "Upstairs Nest Thermostat" in device_names
        
        # Verify all returned devices are actually thermostats
        for device in result["devices"]:
            assert device["class"] == "indigo.ThermostatDevice"
    
    def test_get_devices_speedcontrol_type(self, handler):
        """Test retrieving all speed control devices."""
        result = handler.get_devices("speedcontrol")
        
        assert result["success"] is True
        assert result["device_type"] == "speedcontrol"
        assert result["count"] == 1
        
        device_names = [device["name"] for device in result["devices"]]
        assert "Master Bedroom Fan" in device_names
        
        # Verify all returned devices are actually speed control devices
        for device in result["devices"]:
            assert device["class"] == "indigo.SpeedControlDevice"
    
    def test_get_devices_sprinkler_type(self, handler):
        """Test retrieving all sprinkler devices."""
        result = handler.get_devices("sprinkler")
        
        assert result["success"] is True
        assert result["device_type"] == "sprinkler"
        assert result["count"] == 1
        
        device_names = [device["name"] for device in result["devices"]]
        assert "Sprinklers" in device_names
        
        # Verify all returned devices are actually sprinkler devices
        for device in result["devices"]:
            assert device["class"] == "indigo.SprinklerDevice"
    
    def test_get_devices_device_type(self, handler):
        """Test retrieving all base device type devices."""
        result = handler.get_devices("device")
        
        assert result["success"] is True
        assert result["device_type"] == "device"
        assert result["count"] == 1
        
        device_names = [device["name"] for device in result["devices"]]
        assert "Unknown Device" in device_names
    
    def test_get_devices_invalid_type(self, handler):
        """Test handling of invalid device types."""
        result = handler.get_devices("invalid_type")
        
        assert result["success"] is False
        assert "error" in result
        assert "Invalid device type" in result["error"]
        assert "valid_types" in result
        assert "invalid_type" not in result["valid_types"]
    
    def test_get_devices_empty_string(self, handler):
        """Test handling of empty string device type."""
        result = handler.get_devices("")
        
        assert result["success"] is False
        assert "error" in result
        assert "Invalid device type" in result["error"]
    
    def test_get_devices_case_sensitivity(self, handler):
        """Test that device type is case sensitive."""
        result = handler.get_devices("DIMMER")
        
        assert result["success"] is False
        assert "error" in result
        assert "Invalid device type" in result["error"]
    
    def test_get_devices_sorting(self, handler):
        """Test that devices are sorted by name."""
        result = handler.get_devices("sensor")
        
        assert result["success"] is True
        assert result["count"] == 2
        
        # Verify sorting by name (case insensitive)
        device_names = [device["name"] for device in result["devices"]]
        assert device_names == sorted(device_names, key=str.lower)
    
    def test_get_devices_no_matches(self, mock_data_provider):
        """Test behavior when no devices match the type."""
        # Override the data provider to return only non-multiio devices
        mock_data_provider.get_all_devices_unfiltered.return_value = [
            {
                "name": "Dimmer Only",
                "class": "indigo.DimmerDevice",
                "deviceTypeId": "ra2Dimmer",
                "id": 1
            }
        ]
        
        mock_logger = Mock()
        handler = GetDevicesByTypeHandler(
            data_provider=mock_data_provider,
            logger=mock_logger
        )
        
        result = handler.get_devices("multiio")
        
        assert result["success"] is True
        assert result["device_type"] == "multiio"
        assert result["count"] == 0
        assert result["devices"] == []
    
    def test_data_provider_exception_handling(self, mock_data_provider):
        """Test handling of data provider exceptions."""
        # Make the data provider raise an exception
        mock_data_provider.get_all_devices_unfiltered.side_effect = Exception("Data provider error")
        
        mock_logger = Mock()
        handler = GetDevicesByTypeHandler(
            data_provider=mock_data_provider,
            logger=mock_logger
        )
        
        result = handler.get_devices("dimmer")
        
        assert "error" in result
        assert "Data provider error" in str(result["error"])
    
    def test_device_type_validation_coverage(self, handler):
        """Test that all valid device types work correctly."""
        valid_types = IndigoDeviceType.get_all_types()
        
        for device_type in valid_types:
            result = handler.get_devices(device_type)
            
            # Should not error out (might return 0 results)
            assert result["success"] is True
            assert result["device_type"] == device_type
            assert "count" in result
            assert "devices" in result
    
    def test_real_world_device_classification(self, mock_data_provider):
        """Test with more realistic device examples from your actual system."""
        real_devices = [
            # More realistic examples based on your device list
            {
                "name": "Basement Bar Pendants",
                "class": "indigo.DimmerDevice",
                "id": 973065389,
                "deviceTypeId": "ra2Dimmer"
            },
            {
                "name": "Basement TV Cabinet LED Lights", 
                "class": "indigo.DimmerDevice",
                "id": 343606413,
                "deviceTypeId": "hueLightStrips"
            },
            {
                "name": "Kitchen Counter Lights",
                "class": "indigo.RelayDevice", 
                "id": 132419668,
                "deviceTypeId": "ra2Switch"
            },
            {
                "name": "AV Rack Power Switch",
                "class": "indigo.RelayDevice",
                "id": 32006410,
                "deviceTypeId": "zwRelayType"
            }
        ]
        
        mock_data_provider.get_all_devices_unfiltered.return_value = real_devices
        
        mock_logger = Mock()
        handler = GetDevicesByTypeHandler(
            data_provider=mock_data_provider,
            logger=mock_logger
        )
        
        # Test dimmer classification
        dimmer_result = handler.get_devices("dimmer")
        assert dimmer_result["count"] == 2
        dimmer_names = [d["name"] for d in dimmer_result["devices"]]
        assert "Basement Bar Pendants" in dimmer_names
        assert "Basement TV Cabinet LED Lights" in dimmer_names
        
        # Test relay classification  
        relay_result = handler.get_devices("relay")
        assert relay_result["count"] == 2
        relay_names = [d["name"] for d in relay_result["devices"]]
        assert "Kitchen Counter Lights" in relay_names
        assert "AV Rack Power Switch" in relay_names