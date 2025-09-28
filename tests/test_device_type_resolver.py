"""
Tests for DeviceTypeResolver class.
"""

import pytest
from unittest.mock import MagicMock

try:
    from mcp_server.common.indigo_device_types import (
        DeviceTypeResolver,
        IndigoDeviceType
    )
    INDIGO_AVAILABLE = True
except ImportError:
    INDIGO_AVAILABLE = False


@pytest.mark.skipif(not INDIGO_AVAILABLE, reason="Indigo modules not available")
class TestDeviceTypeResolver:
    """Test DeviceTypeResolver functionality."""

    def test_resolve_valid_device_type(self):
        """Test resolving already valid device types."""
        # Valid types should pass through unchanged
        assert DeviceTypeResolver.resolve_device_type("dimmer") == "dimmer"
        assert DeviceTypeResolver.resolve_device_type("relay") == "relay"
        assert DeviceTypeResolver.resolve_device_type("sensor") == "sensor"
        assert DeviceTypeResolver.resolve_device_type("multiio") == "multiio"
        assert DeviceTypeResolver.resolve_device_type("speedcontrol") == "speedcontrol"
        assert DeviceTypeResolver.resolve_device_type("sprinkler") == "sprinkler"
        assert DeviceTypeResolver.resolve_device_type("thermostat") == "thermostat"
        assert DeviceTypeResolver.resolve_device_type("device") == "device"

    def test_resolve_light_aliases(self):
        """Test resolving light-related aliases."""
        # Test the original issue case
        assert DeviceTypeResolver.resolve_device_type("light") == "dimmer"
        assert DeviceTypeResolver.resolve_device_type("lights") == "dimmer"
        assert DeviceTypeResolver.resolve_device_type("lamp") == "dimmer"
        assert DeviceTypeResolver.resolve_device_type("lamps") == "dimmer"
        assert DeviceTypeResolver.resolve_device_type("bulb") == "dimmer"
        assert DeviceTypeResolver.resolve_device_type("bulbs") == "dimmer"

    def test_resolve_switch_aliases(self):
        """Test resolving switch/relay aliases."""
        assert DeviceTypeResolver.resolve_device_type("switch") == "relay"
        assert DeviceTypeResolver.resolve_device_type("switches") == "relay"
        assert DeviceTypeResolver.resolve_device_type("outlet") == "relay"
        assert DeviceTypeResolver.resolve_device_type("outlets") == "relay"
        assert DeviceTypeResolver.resolve_device_type("plug") == "relay"
        assert DeviceTypeResolver.resolve_device_type("plugs") == "relay"

    def test_resolve_sensor_aliases(self):
        """Test resolving sensor aliases."""
        assert DeviceTypeResolver.resolve_device_type("motion") == "sensor"
        assert DeviceTypeResolver.resolve_device_type("temperature") == "sensor"
        assert DeviceTypeResolver.resolve_device_type("humidity") == "sensor"
        assert DeviceTypeResolver.resolve_device_type("contact") == "sensor"
        assert DeviceTypeResolver.resolve_device_type("door") == "sensor"
        assert DeviceTypeResolver.resolve_device_type("window") == "sensor"
        assert DeviceTypeResolver.resolve_device_type("detector") == "sensor"

    def test_resolve_other_aliases(self):
        """Test resolving other device type aliases."""
        # Fan/Speed control
        assert DeviceTypeResolver.resolve_device_type("fan") == "speedcontrol"
        assert DeviceTypeResolver.resolve_device_type("fans") == "speedcontrol"

        # I/O
        assert DeviceTypeResolver.resolve_device_type("io") == "multiio"
        assert DeviceTypeResolver.resolve_device_type("input") == "multiio"
        assert DeviceTypeResolver.resolve_device_type("output") == "multiio"

        # HVAC
        assert DeviceTypeResolver.resolve_device_type("hvac") == "thermostat"
        assert DeviceTypeResolver.resolve_device_type("climate") == "thermostat"
        assert DeviceTypeResolver.resolve_device_type("temp") == "thermostat"

        # Irrigation
        assert DeviceTypeResolver.resolve_device_type("irrigation") == "sprinkler"
        assert DeviceTypeResolver.resolve_device_type("water") == "sprinkler"
        assert DeviceTypeResolver.resolve_device_type("watering") == "sprinkler"

    def test_resolve_case_insensitive(self):
        """Test that alias resolution is case-insensitive."""
        assert DeviceTypeResolver.resolve_device_type("LIGHT") == "dimmer"
        assert DeviceTypeResolver.resolve_device_type("Light") == "dimmer"
        assert DeviceTypeResolver.resolve_device_type("LiGhT") == "dimmer"
        assert DeviceTypeResolver.resolve_device_type("SWITCH") == "relay"
        assert DeviceTypeResolver.resolve_device_type("Switch") == "relay"
        assert DeviceTypeResolver.resolve_device_type("MOTION") == "sensor"

    def test_resolve_invalid_device_type(self):
        """Test resolving invalid device types."""
        assert DeviceTypeResolver.resolve_device_type("invalid") is None
        assert DeviceTypeResolver.resolve_device_type("unknown") is None
        assert DeviceTypeResolver.resolve_device_type("xyz123") is None
        assert DeviceTypeResolver.resolve_device_type("") is None
        assert DeviceTypeResolver.resolve_device_type(None) is None

    def test_resolve_device_types_list(self):
        """Test resolving a list of device types."""
        # All valid
        valid_types, invalid_types = DeviceTypeResolver.resolve_device_types(["dimmer", "relay"])
        assert valid_types == ["dimmer", "relay"]
        assert invalid_types == []

        # Mix of aliases and valid types
        valid_types, invalid_types = DeviceTypeResolver.resolve_device_types(["light", "relay", "motion"])
        assert valid_types == ["dimmer", "relay", "sensor"]
        assert invalid_types == []

        # Mix with invalid types
        valid_types, invalid_types = DeviceTypeResolver.resolve_device_types(["light", "invalid", "switch"])
        assert valid_types == ["dimmer", "relay"]
        assert invalid_types == ["invalid"]

        # All invalid
        valid_types, invalid_types = DeviceTypeResolver.resolve_device_types(["invalid1", "invalid2"])
        assert valid_types == []
        assert invalid_types == ["invalid1", "invalid2"]

        # Empty list
        valid_types, invalid_types = DeviceTypeResolver.resolve_device_types([])
        assert valid_types == []
        assert invalid_types == []

        # None input
        valid_types, invalid_types = DeviceTypeResolver.resolve_device_types(None)
        assert valid_types == []
        assert invalid_types == []

    def test_get_suggestions_for_invalid_type(self):
        """Test getting suggestions for invalid device types."""
        # Test partial matches
        suggestions = DeviceTypeResolver.get_suggestions_for_invalid_type("lig")
        assert any("light" in suggestion for suggestion in suggestions)

        suggestions = DeviceTypeResolver.get_suggestions_for_invalid_type("swit")
        assert any("switch" in suggestion for suggestion in suggestions)

        suggestions = DeviceTypeResolver.get_suggestions_for_invalid_type("mot")
        assert any("motion" in suggestion for suggestion in suggestions)

        # Test exact match of valid types
        suggestions = DeviceTypeResolver.get_suggestions_for_invalid_type("dim")
        assert any("dimmer" in suggestion for suggestion in suggestions)

        # Test invalid with no suggestions
        suggestions = DeviceTypeResolver.get_suggestions_for_invalid_type("xyz123")
        assert suggestions == []

        # Test empty/None
        suggestions = DeviceTypeResolver.get_suggestions_for_invalid_type("")
        assert suggestions == []

        suggestions = DeviceTypeResolver.get_suggestions_for_invalid_type(None)
        assert suggestions == []

    def test_get_all_aliases(self):
        """Test getting all available aliases."""
        aliases = DeviceTypeResolver.get_all_aliases()

        # Check that aliases exist
        assert isinstance(aliases, dict)
        assert len(aliases) > 0

        # Check specific mappings
        assert aliases["light"] == "dimmer"
        assert aliases["switch"] == "relay"
        assert aliases["motion"] == "sensor"
        assert aliases["fan"] == "speedcontrol"
        assert aliases["io"] == "multiio"
        assert aliases["hvac"] == "thermostat"
        assert aliases["irrigation"] == "sprinkler"

    def test_whitespace_handling(self):
        """Test that whitespace is properly handled."""
        assert DeviceTypeResolver.resolve_device_type("  light  ") == "dimmer"
        assert DeviceTypeResolver.resolve_device_type(" switch ") == "relay"
        assert DeviceTypeResolver.resolve_device_type("\tmotion\t") == "sensor"

    def test_suggestions_limit(self):
        """Test that suggestions are limited to avoid overwhelming output."""
        # This test is more about ensuring we don't return too many suggestions
        suggestions = DeviceTypeResolver.get_suggestions_for_invalid_type("e")  # Matches many
        assert len(suggestions) <= 3  # Should be limited to 3