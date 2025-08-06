"""
Tests for StateFilter class functionality.
"""

import pytest
from mcp_server.common.state_filter import StateFilter
from tests.fixtures.real_device_fixtures import RealDeviceFixtures


class TestStateFilter:
    """Test cases for StateFilter class."""
    
    def test_filter_by_state_on_devices(self):
        """Test filtering devices that are on."""
        devices = RealDeviceFixtures.get_sample_devices()
        state_filter = {"onState": True}
        
        result = StateFilter.filter_by_state(devices, state_filter)
        
        # Should find devices that are on
        assert len(result) == 4
        device_ids = [d["id"] for d in result]
        expected_ids = [1179790665, 1777183268, 2000000001, 2000000002]
        assert set(device_ids) == set(expected_ids)
    
    def test_filter_by_state_off_devices(self):
        """Test filtering devices that are off."""
        devices = RealDeviceFixtures.get_sample_devices()
        state_filter = {"onState": False}
        
        result = StateFilter.filter_by_state(devices, state_filter)
        
        # Should find devices that are off (including None onState for sensors)
        assert len(result) == 3
        device_ids = [d["id"] for d in result]
        expected_ids = [1385203939, 1234567890, 106946585]
        assert set(device_ids) == set(expected_ids)
    
    def test_filter_by_brightness_greater_than(self):
        """Test filtering by brightness greater than threshold."""
        devices = RealDeviceFixtures.get_sample_devices()
        state_filter = {"brightnessLevel": {"gt": 60}}
        
        result = StateFilter.filter_by_state(devices, state_filter)
        
        # Should find devices with brightness > 60
        assert len(result) == 2
        device_ids = [d["id"] for d in result]
        expected_ids = [1179790665, 2000000002]  # 75% and 90%
        assert set(device_ids) == set(expected_ids)
    
    def test_filter_by_brightness_range(self):
        """Test filtering by brightness range."""
        devices = RealDeviceFixtures.get_sample_devices()
        state_filter = {"brightnessLevel": {"gte": 50, "lte": 80}}
        
        result = StateFilter.filter_by_state(devices, state_filter)
        
        # Should find devices with brightness 50-80%
        assert len(result) == 2
        device_ids = [d["id"] for d in result]
        expected_ids = [1179790665, 2000000001]  # 75% and 50%
        assert set(device_ids) == set(expected_ids)
    
    def test_filter_by_error_state_not_empty(self):
        """Test filtering devices with error states."""
        devices = RealDeviceFixtures.get_sample_devices()
        state_filter = {"errorState": {"ne": ""}}
        
        result = StateFilter.filter_by_state(devices, state_filter)
        
        # Should find only the device with error
        assert len(result) == 1
        assert result[0]["id"] == 106946585
        assert result[0]["errorState"] == "Communication timeout"
    
    def test_filter_by_multiple_conditions(self):
        """Test filtering with multiple state conditions."""
        devices = RealDeviceFixtures.get_sample_devices()
        state_filter = {
            "onState": True,
            "brightnessLevel": {"gt": 40}
        }
        
        result = StateFilter.filter_by_state(devices, state_filter)
        
        # Should find devices that are on AND have brightness > 40
        assert len(result) == 3
        device_ids = [d["id"] for d in result]
        expected_ids = [1179790665, 2000000001, 2000000002]
        assert set(device_ids) == set(expected_ids)
    
    def test_filter_states_dictionary(self):
        """Test filtering using values from states dictionary."""
        devices = RealDeviceFixtures.get_sample_devices()
        # Some devices have onOffState in states dict instead of top level
        state_filter = {"onOffState": True}
        
        result = StateFilter.filter_by_state(devices, state_filter)
        
        # Should find devices where states.onOffState is true
        assert len(result) >= 3  # At least the devices we know have this state
    
    def test_filter_contains_operator(self):
        """Test filtering with contains operator."""
        devices = RealDeviceFixtures.get_sample_devices()
        state_filter = {"name": {"contains": "Light"}}
        
        result = StateFilter.filter_by_state(devices, state_filter)
        
        # Should find devices with "Light" in name
        light_devices = [d for d in result if "Light" in d["name"]]
        assert len(light_devices) >= 2
    
    def test_filter_enabled_devices(self):
        """Test filtering enabled devices."""
        devices = RealDeviceFixtures.get_sample_devices()
        state_filter = {"enabled": True}
        
        result = StateFilter.filter_by_state(devices, state_filter)
        
        # Should find all enabled devices (all except the disabled one)
        assert len(result) == 7
        disabled_device = next(d for d in devices if not d.get("enabled", True))
        disabled_ids = [d["id"] for d in result if d["id"] == disabled_device["id"]]
        assert len(disabled_ids) == 0
    
    def test_parse_state_requirements_on_keywords(self):
        """Test parsing state requirements from natural language."""
        queries_and_expected = [
            ("lights that are on", {"onState": True}),
            ("devices that are off", {"onState": False}),
            ("lights turned on", {"onState": True}),
            ("inactive sensors", {"onState": False}),
            ("enabled devices", None),  # "enabled" not in current keywords
        ]
        
        for query, expected in queries_and_expected:
            result = StateFilter.parse_state_requirements(query)
            if expected:
                assert result == expected, f"Failed for query: {query}"
            else:
                assert result is None or result == {}, f"Expected None/empty for query: {query}"
    
    def test_parse_state_requirements_brightness(self):
        """Test parsing brightness state requirements."""
        queries_and_expected = [
            ("bright lights", {"brightnessLevel": {"gt": 50}}),
            ("dim lights", {"brightnessLevel": {"lte": 50}}),
        ]
        
        for query, expected in queries_and_expected:
            result = StateFilter.parse_state_requirements(query)
            assert result == expected, f"Failed for query: {query}"
    
    def test_parse_state_requirements_error_states(self):
        """Test parsing error state requirements."""
        queries_and_expected = [
            ("devices with errors", {"errorState": {"ne": ""}}),
            ("devices without errors", {"errorState": ""}),
            ("no error devices", {"errorState": ""}),
        ]
        
        for query, expected in queries_and_expected:
            result = StateFilter.parse_state_requirements(query)
            assert result == expected, f"Failed for query: {query}"
    
    def test_has_state_keywords(self):
        """Test detection of state keywords in queries."""
        state_queries = [
            "lights that are on",
            "devices that are off", 
            "bright lights",
            "dim sensors",
            "active devices",
            "inactive switches"
        ]
        
        non_state_queries = [
            "bedroom lights",
            "temperature sensors",
            "find all switches",
            "living room devices"
        ]
        
        for query in state_queries:
            assert StateFilter.has_state_keywords(query), f"Should detect state in: {query}"
        
        for query in non_state_queries:
            assert not StateFilter.has_state_keywords(query), f"Should not detect state in: {query}"
    
    def test_matches_state_edge_cases(self):
        """Test edge cases for state matching."""
        # Device with missing state
        device = {"id": 123, "name": "Test Device"}
        
        # Should not match if state doesn't exist
        assert not StateFilter.matches_state(device, {"onState": True})
        assert not StateFilter.matches_state(device, {"brightness": {"gt": 0}})
        
        # Should match if condition is for missing/empty state
        assert StateFilter.matches_state(device, {"errorState": ""})
    
    def test_complex_condition_operators(self):
        """Test all complex condition operators."""
        device = {
            "id": 123,
            "brightness": 75,
            "temperature": 72.5,
            "name": "Living Room Light",
            "model": "Philips Hue"
        }
        
        test_cases = [
            ({"brightness": {"gt": 70}}, True),
            ({"brightness": {"gte": 75}}, True),
            ({"brightness": {"lt": 80}}, True),
            ({"brightness": {"lte": 75}}, True),
            ({"brightness": {"ne": 50}}, True),
            ({"brightness": {"eq": 75}}, True),
            ({"name": {"contains": "Living"}}, True),
            ({"name": {"contains": "Bedroom"}}, False),
            ({"brightness": {"gt": 80}}, False),
        ]
        
        for condition, expected in test_cases:
            result = StateFilter.matches_state(device, condition)
            assert result == expected, f"Failed for condition: {condition}"
    
    def test_filter_by_state_empty_conditions(self):
        """Test filtering with empty conditions."""
        devices = RealDeviceFixtures.get_sample_devices()
        
        # Empty conditions should return all devices
        result = StateFilter.filter_by_state(devices, {})
        assert len(result) == len(devices)
        
        # None conditions should return all devices
        result = StateFilter.filter_by_state(devices, None)
        assert len(result) == len(devices)