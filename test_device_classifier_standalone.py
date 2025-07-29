#!/usr/bin/env python3
"""
Standalone test for DeviceClassifier to verify the fix works with real device data.
"""

import sys
import os

# Add the MCP server module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'MCP Server.indigoPlugin/Contents/Server Plugin'))

# Import just the specific module we need
from mcp_server.common.indigo_device_types import DeviceClassifier, IndigoDeviceType

def test_device_classifier():
    """Test DeviceClassifier with real device examples from your system."""
    
    print("=== Testing DeviceClassifier with Real Device Data ===\n")
    
    # Real device examples from your actual system
    test_devices = [
        # Dimmers - these should all be classified as "dimmer"
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
            "name": "076 - Nightlight",
            "class": "indigo.DimmerDevice",
            "deviceTypeId": "zwColorDimmerType",
            "expected": "dimmer"
        },
        {
            "name": "Basement TV Cabinet LED Lights",
            "class": "indigo.DimmerDevice",
            "deviceTypeId": "hueLightStrips",
            "expected": "dimmer"
        },
        {
            "name": "AV Rack Front LED Lights", 
            "class": "indigo.DimmerDevice",
            "deviceTypeId": "HAdimmerType",
            "expected": "dimmer"
        },
        
        # Relays - these should all be classified as "relay"
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
            "name": "Kitchen Counter Lights",
            "class": "indigo.RelayDevice",
            "deviceTypeId": "ra2Switch",
            "expected": "relay"
        },
        {
            "name": "AV Rack Power Switch",
            "class": "indigo.RelayDevice",
            "deviceTypeId": "zwRelayType", 
            "expected": "relay"
        },
        
        # Sensors
        {
            "name": "Kitchen Motion Sensor",
            "class": "indigo.SensorDevice",
            "deviceTypeId": "zwOnOffSensorType",
            "expected": "sensor"
        },
        {
            "name": "Kitchen Temperature",
            "class": "indigo.SensorDevice",
            "deviceTypeId": "zwValueSensorType",
            "expected": "sensor"
        },
        
        # Thermostats
        {
            "name": "Upstairs Nest Thermostat",
            "class": "indigo.ThermostatDevice",
            "deviceTypeId": "nestThermostat",
            "expected": "thermostat"
        },
        
        # Speed control (fans)
        {
            "name": "Master Bedroom Fan",
            "class": "indigo.SpeedControlDevice",
            "deviceTypeId": "ha_fan",
            "expected": "speedcontrol"
        },
        
        # Sprinkler
        {
            "name": "Sprinklers",
            "class": "indigo.SprinklerDevice",
            "deviceTypeId": "sprinkler", 
            "expected": "sprinkler"
        }
    ]
    
    # Test classification
    print("1. Testing individual device classification:")
    all_passed = True
    
    for device in test_devices:
        classified_type = DeviceClassifier.classify_device(device)
        status = "✓" if classified_type == device["expected"] else "✗"
        
        if classified_type != device["expected"]:
            all_passed = False
            
        print(f"   {status} {device['name']}: {classified_type} (expected: {device['expected']})")
    
    print(f"\n   Individual classification: {'PASSED' if all_passed else 'FAILED'}")
    
    # Test filtering by type
    print("\n2. Testing filter_devices_by_type:")
    
    # Test filtering dimmers
    dimmers = DeviceClassifier.filter_devices_by_type(test_devices, "dimmer")
    expected_dimmer_count = len([d for d in test_devices if d["expected"] == "dimmer"])
    dimmer_names = [d["name"] for d in dimmers]
    
    print(f"   Dimmers: Found {len(dimmers)}/{expected_dimmer_count}")
    print(f"   -> {', '.join(dimmer_names)}")
    
    # Test filtering relays  
    relays = DeviceClassifier.filter_devices_by_type(test_devices, "relay")
    expected_relay_count = len([d for d in test_devices if d["expected"] == "relay"])
    relay_names = [d["name"] for d in relays]
    
    print(f"   Relays: Found {len(relays)}/{expected_relay_count}")
    print(f"   -> {', '.join(relay_names)}")
    
    # Test filtering sensors
    sensors = DeviceClassifier.filter_devices_by_type(test_devices, "sensor")
    expected_sensor_count = len([d for d in test_devices if d["expected"] == "sensor"])
    sensor_names = [d["name"] for d in sensors]
    
    print(f"   Sensors: Found {len(sensors)}/{expected_sensor_count}")
    print(f"   -> {', '.join(sensor_names)}")
    
    filter_passed = (
        len(dimmers) == expected_dimmer_count and
        len(relays) == expected_relay_count and 
        len(sensors) == expected_sensor_count
    )
    
    print(f"\n   Filtering: {'PASSED' if filter_passed else 'FAILED'}")
    
    # Test device type distribution
    print("\n3. Testing get_device_type_distribution:")
    distribution = DeviceClassifier.get_device_type_distribution(test_devices)
    
    for device_type, count in sorted(distribution.items()):
        expected_count = len([d for d in test_devices if d["expected"] == device_type])
        status = "✓" if count == expected_count else "✗"
        print(f"   {status} {device_type}: {count} (expected: {expected_count})")
    
    distribution_passed = all(
        distribution.get(device_type, 0) == len([d for d in test_devices if d["expected"] == device_type])
        for device_type in ["dimmer", "relay", "sensor", "thermostat", "speedcontrol", "sprinkler"]
    )
    
    print(f"\n   Distribution: {'PASSED' if distribution_passed else 'FAILED'}")
    
    # Test with some edge cases  
    print("\n4. Testing edge cases:")
    edge_cases = [
        {"case": "Empty device", "device": {}, "expected": "device"},
        {"case": "Unknown class", "device": {"class": "unknown.Device", "deviceTypeId": "unknown"}, "expected": "device"},
        {"case": "Case insensitive", "device": {"class": "unknown", "deviceTypeId": "RA2DIMMER"}, "expected": "dimmer"},
        {"case": "Complex pattern", "device": {"class": "unknown", "deviceTypeId": "smartLightDimmerController"}, "expected": "dimmer"},
    ]
    
    edge_passed = True
    for test_case in edge_cases:
        result = DeviceClassifier.classify_device(test_case["device"])
        status = "✓" if result == test_case["expected"] else "✗"
        
        if result != test_case["expected"]:
            edge_passed = False
            
        print(f"   {status} {test_case['case']}: {result} (expected: {test_case['expected']})")
    
    print(f"\n   Edge cases: {'PASSED' if edge_passed else 'FAILED'}")
    
    # Overall result
    overall_passed = all_passed and filter_passed and distribution_passed and edge_passed
    
    print(f"\n=== Overall Result: {'✓ ALL TESTS PASSED' if overall_passed else '✗ SOME TESTS FAILED'} ===")
    
    if overall_passed:
        print("\nThe DeviceClassifier fix will correctly identify your lighting devices!")
        print("- get_devices_by_type('dimmer') will now return all your dimmer devices")
        print("- get_devices_by_type('relay') will now return all your relay/switch devices") 
        print("- search_entities('lights') with device type filtering will work correctly")
    
    return overall_passed

if __name__ == "__main__":
    test_device_classifier()