"""
Real device fixtures based on actual Indigo system data.
Used for creating realistic test scenarios for state filtering functionality.
"""

from typing import Dict, List, Any


class RealDeviceFixtures:
    """Real device data fixtures based on actual Indigo system."""
    
    @staticmethod
    def get_sample_devices() -> List[Dict[str, Any]]:
        """Get sample devices with realistic states and properties."""
        return [
            # Dimmer device - OFF state
            {
                "class": "indigo.DimmerDevice",
                "id": 1385203939,
                "name": "Nightlight",
                "deviceTypeId": "zwColorDimmerType",
                "onState": False,
                "brightness": 0,
                "brightnessLevel": 0,
                "errorState": "",
                "model": "Smart Switch 7 (ZWA023)",
                "enabled": True,
                "states": {
                    "brightnessLevel": 0,
                    "onOffState": False,
                    "redLevel": 0.0,
                    "greenLevel": 0.0,
                    "blueLevel": 0.0
                }
            },
            # Dimmer device - ON state with 75% brightness
            {
                "class": "indigo.DimmerDevice", 
                "id": 1179790665,
                "name": "Bedroom Fan Light",
                "deviceTypeId": "HAdimmerType",
                "onState": True,
                "brightness": 75,
                "brightnessLevel": 75,
                "errorState": "",
                "model": "Home Assistant Light",
                "enabled": True,
                "states": {
                    "brightnessLevel": 75,
                    "onOffState": True,
                    "actual_state": "on"
                }
            },
            # Relay device group - ON state
            {
                "class": "indigo.RelayDevice",
                "id": 1777183268,
                "name": "All Bedroom Motion Sensors",
                "deviceTypeId": "relayGroup",
                "onState": True,
                "errorState": "",
                "model": "Device Group",
                "enabled": True,
                "states": {
                    "onOffState": True
                }
            },
            # Relay device - OFF state
            {
                "class": "indigo.RelayDevice",
                "id": 1234567890,
                "name": "Basement Bathroom Shower Lights",
                "deviceTypeId": "ra2Switch", 
                "onState": False,
                "errorState": "",
                "model": "Lutron Switch",
                "enabled": True,
                "states": {
                    "onOffState": False
                }
            },
            # Sensor device - temperature
            {
                "class": "indigo.SensorDevice",
                "id": 76835202,
                "name": "Car Odometer Sensor",
                "deviceTypeId": "HAsensor",
                "onState": None,
                "sensorValue": 12345.6,
                "errorState": "",
                "model": "Home Assistant Value Sensor",
                "enabled": True,
                "states": {
                    "sensorValue": 12345.6,
                    "device_class": "distance",
                    "unit_of_measurement": "mi",
                    "actual_state": "12345.6"
                }
            },
            # Device with error state
            {
                "class": "indigo.Device",
                "id": 106946585,
                "name": "AC Unit Monitor",
                "deviceTypeId": "sensedevice",
                "onState": False,
                "errorState": "Communication timeout",
                "model": "Sense Device",
                "enabled": False,
                "states": {
                    "power": 0,
                    "id": "4897ac91"
                }
            },
            # Dimmer with medium brightness (50%)
            {
                "class": "indigo.DimmerDevice",
                "id": 2000000001,
                "name": "Living Room Main Light",
                "deviceTypeId": "zwDimmerType",
                "onState": True,
                "brightness": 50,
                "brightnessLevel": 50,
                "errorState": "",
                "model": "Z-Wave Dimmer",
                "enabled": True,
                "states": {
                    "brightnessLevel": 50,
                    "onOffState": True
                }
            },
            # Dimmer with high brightness (90%)
            {
                "class": "indigo.DimmerDevice",
                "id": 2000000002,
                "name": "Kitchen Under Cabinet Lights",
                "deviceTypeId": "HAdimmerType",
                "onState": True,
                "brightness": 90,
                "brightnessLevel": 90,
                "errorState": "",
                "model": "Home Assistant Light",
                "enabled": True,
                "states": {
                    "brightnessLevel": 90,
                    "onOffState": True,
                    "color_temp": 3000
                }
            }
        ]
    
    @staticmethod
    def get_sample_variables() -> List[Dict[str, Any]]:
        """Get sample variables with realistic values."""
        return [
            {
                "class": "indigo.Variable",
                "id": 1396258091,
                "name": "alarm_enabled",
                "value": "true",
                "readOnly": False,
                "description": "",
                "folderId": 1867536050
            },
            {
                "class": "indigo.Variable",
                "id": 25923526,
                "name": "house_mode",
                "value": "home",
                "readOnly": False,
                "description": "Current house occupancy mode",
                "folderId": 0
            },
            {
                "class": "indigo.Variable",
                "id": 1635711954,
                "name": "temperature_setpoint",
                "value": "72",
                "readOnly": False,
                "description": "Target temperature",
                "folderId": 0
            },
            {
                "class": "indigo.Variable",
                "id": 3000000001,
                "name": "security_status",
                "value": "disarmed",
                "readOnly": True,
                "description": "Current security system status",
                "folderId": 1867536050
            }
        ]
    
    @staticmethod
    def get_sample_action_groups() -> List[Dict[str, Any]]:
        """Get sample action groups with realistic names."""
        return [
            {
                "class": "indigo.ActionGroup",
                "id": 352242894,
                "name": "Basement Door Auto Close",
                "description": "Automatically close basement door after timeout",
                "folderId": 0
            },
            {
                "class": "indigo.ActionGroup", 
                "id": 1560591171,
                "name": "Good Night Scene",
                "description": "Turn off all lights and set security",
                "folderId": 1000000001
            },
            {
                "class": "indigo.ActionGroup",
                "id": 1276460561,
                "name": "Morning Routine",
                "description": "Turn on essential lights and adjust thermostat",
                "folderId": 1000000001
            },
            {
                "class": "indigo.ActionGroup",
                "id": 4000000001,
                "name": "Movie Time",
                "description": "Dim lights for movie watching",
                "folderId": 0
            }
        ]
    
    @staticmethod
    def get_state_filter_test_scenarios() -> Dict[str, Dict[str, Any]]:
        """Get realistic state filtering test scenarios."""
        return {
            "lights_that_are_on": {
                "description": "Find all lights that are currently on",
                "state_filter": {"onState": True},
                "device_types": ["dimmer", "relay"],
                "expected_count": 4,  # Based on sample data
                "expected_ids": [1179790665, 1777183268, 2000000001, 2000000002]
            },
            "dimmed_lights": {
                "description": "Find lights with brightness between 1-99%",
                "state_filter": {"brightnessLevel": {"gt": 0, "lt": 100}},
                "device_types": ["dimmer"],
                "expected_count": 3,
                "expected_ids": [1179790665, 2000000001, 2000000002]
            },
            "bright_lights": {
                "description": "Find lights with brightness > 70%",
                "state_filter": {"brightnessLevel": {"gt": 70}},
                "device_types": ["dimmer"],
                "expected_count": 2,
                "expected_ids": [1179790665, 2000000002]
            },
            "devices_with_errors": {
                "description": "Find devices with error states",
                "state_filter": {"errorState": {"ne": ""}},
                "expected_count": 1,
                "expected_ids": [106946585]
            },
            "off_devices": {
                "description": "Find devices that are off",
                "state_filter": {"onState": False},
                "expected_count": 3,
                "expected_ids": [1385203939, 1234567890, 106946585]
            },
            "enabled_devices": {
                "description": "Find enabled devices",
                "state_filter": {"enabled": True},
                "expected_count": 7,
                "expected_ids": [1385203939, 1179790665, 1777183268, 1234567890, 76835202, 2000000001, 2000000002]
            }
        }
    
    @staticmethod
    def get_search_query_scenarios() -> Dict[str, Dict[str, Any]]:
        """Get realistic search query test scenarios."""
        return {
            "bedroom_lights": {
                "query": "bedroom lights",
                "expected_devices": ["All Bedroom Motion Sensors", "Bedroom Fan Light"],
                "min_relevance": 0.6
            },
            "bathroom_lights": {
                "query": "bathroom lights", 
                "expected_devices": ["Basement Bathroom Shower Lights"],
                "min_relevance": 0.7
            },
            "temperature_sensors": {
                "query": "temperature sensors",
                "expected_devices": [],  # No temperature sensors in sample data
                "min_relevance": 0.5
            },
            "lights_that_are_on": {
                "query": "lights that are on",
                "state_keywords_detected": True,
                "suggestion_expected": True,
                "alternative_tools": ["list_devices", "get_devices_by_state"]
            },
            "dim_lights": {
                "query": "dim lights", 
                "state_keywords_detected": True,
                "expected_brightness_filter": {"lte": 50}
            }
        }
    
    @staticmethod
    def get_device_type_distributions() -> Dict[str, int]:
        """Get realistic device type distributions for testing."""
        return {
            "dimmer": 4,      # 4 dimmer devices in sample
            "relay": 2,       # 2 relay devices in sample  
            "sensor": 1,      # 1 sensor device in sample
            "device": 1,      # 1 generic device in sample
            "other": 0        # 0 other devices in sample
        }