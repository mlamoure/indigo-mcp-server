"""
Test suite for device control operations.
"""

import pytest
from unittest.mock import Mock, patch

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'MCP Server.indigoPlugin', 'Contents', 'Server Plugin'))

from mcp_server.tools.device_control import DeviceControlHandler
from tests.mocks.mock_data_provider import MockDataProvider


class TestDeviceControlHandler:
    """Test device control handler functionality."""
    
    @pytest.fixture
    def handler(self):
        """Create a device control handler with mock data provider."""
        data_provider = MockDataProvider()
        logger = Mock()
        return DeviceControlHandler(data_provider, logger)
    
    @pytest.fixture
    def mock_device(self):
        """Create a mock device."""
        return {
            "id": 12345,
            "name": "Test Light",
            "deviceTypeId": "dimmer",
            "onState": False,
            "brightness": 50
        }
    
    def test_turn_on_device_success(self, handler):
        """Test successfully turning on a device."""
        # Arrange
        device_id = 12345
        handler.data_provider.turn_on_device = Mock(return_value={
            "changed": True,
            "previous": False,
            "current": True
        })
        
        # Act
        result = handler.turn_on(device_id)
        
        # Assert
        assert result["changed"] is True
        assert result["previous"] is False
        assert result["current"] is True
        assert "error" not in result
        handler.data_provider.turn_on_device.assert_called_once_with(device_id)
    
    def test_turn_on_device_already_on(self, handler):
        """Test turning on a device that's already on."""
        # Arrange
        device_id = 12345
        handler.data_provider.turn_on_device = Mock(return_value={
            "changed": False,
            "previous": True,
            "current": True
        })
        
        # Act
        result = handler.turn_on(device_id)
        
        # Assert
        assert result["changed"] is False
        assert result["previous"] is True
        assert result["current"] is True
    
    def test_turn_on_device_not_found(self, handler):
        """Test turning on a non-existent device."""
        # Arrange
        device_id = 99999
        handler.data_provider.turn_on_device = Mock(return_value={
            "error": f"Device {device_id} not found"
        })
        
        # Act
        result = handler.turn_on(device_id)
        
        # Assert
        assert "error" in result
        assert f"Device {device_id} not found" in result["error"]
    
    def test_turn_on_invalid_device_id(self, handler):
        """Test turning on with invalid device ID."""
        # Act
        result = handler.turn_on("not_an_int")
        
        # Assert
        assert "error" in result
        assert "device_id must be an integer" in result["error"]
    
    def test_turn_off_device_success(self, handler):
        """Test successfully turning off a device."""
        # Arrange
        device_id = 12345
        handler.data_provider.turn_off_device = Mock(return_value={
            "changed": True,
            "previous": True,
            "current": False
        })
        
        # Act
        result = handler.turn_off(device_id)
        
        # Assert
        assert result["changed"] is True
        assert result["previous"] is True
        assert result["current"] is False
        assert "error" not in result
        handler.data_provider.turn_off_device.assert_called_once_with(device_id)
    
    def test_turn_off_device_already_off(self, handler):
        """Test turning off a device that's already off."""
        # Arrange
        device_id = 12345
        handler.data_provider.turn_off_device = Mock(return_value={
            "changed": False,
            "previous": False,
            "current": False
        })
        
        # Act
        result = handler.turn_off(device_id)
        
        # Assert
        assert result["changed"] is False
        assert result["previous"] is False
        assert result["current"] is False
    
    def test_set_brightness_success(self, handler):
        """Test successfully setting brightness."""
        # Arrange
        device_id = 12345
        brightness = 75
        handler.data_provider.set_device_brightness = Mock(return_value={
            "changed": True,
            "previous": 50,
            "current": 75
        })
        
        # Act
        result = handler.set_brightness(device_id, brightness)
        
        # Assert
        assert result["changed"] is True
        assert result["previous"] == 50
        assert result["current"] == 75
        assert "error" not in result
        handler.data_provider.set_device_brightness.assert_called_once_with(device_id, brightness)
    
    def test_set_brightness_fractional_value(self, handler):
        """Test setting brightness with fractional value (0-1)."""
        # Arrange
        device_id = 12345
        brightness = 0.5
        handler.data_provider.set_device_brightness = Mock(return_value={
            "changed": True,
            "previous": 0,
            "current": 50
        })
        
        # Act
        result = handler.set_brightness(device_id, brightness)
        
        # Assert
        assert result["changed"] is True
        assert result["current"] == 50
    
    def test_set_brightness_no_change(self, handler):
        """Test setting brightness to current value."""
        # Arrange
        device_id = 12345
        brightness = 50
        handler.data_provider.set_device_brightness = Mock(return_value={
            "changed": False,
            "previous": 50,
            "current": 50
        })
        
        # Act
        result = handler.set_brightness(device_id, brightness)
        
        # Assert
        assert result["changed"] is False
        assert result["previous"] == 50
        assert result["current"] == 50
    
    def test_set_brightness_unsupported_device(self, handler):
        """Test setting brightness on non-dimmer device."""
        # Arrange
        device_id = 12345
        brightness = 50
        handler.data_provider.set_device_brightness = Mock(return_value={
            "error": f"Device {device_id} does not support brightness control"
        })
        
        # Act
        result = handler.set_brightness(device_id, brightness)
        
        # Assert
        assert "error" in result
        assert "does not support brightness control" in result["error"]
    
    def test_set_brightness_invalid_value(self, handler):
        """Test setting brightness with invalid value."""
        # Arrange
        device_id = 12345
        handler.data_provider.set_device_brightness = Mock(return_value={
            "error": "Invalid brightness value: 150. Must be 0-1 or 0-100"
        })
        
        # Act
        result = handler.set_brightness(device_id, 150)
        
        # Assert
        assert "error" in result
        assert "Invalid brightness value" in result["error"]
    
    def test_set_brightness_invalid_device_id(self, handler):
        """Test setting brightness with invalid device ID."""
        # Act
        result = handler.set_brightness("not_an_int", 50)
        
        # Assert
        assert "error" in result
        assert "device_id must be an integer" in result["error"]
    
    def test_set_brightness_invalid_brightness_type(self, handler):
        """Test setting brightness with invalid brightness type."""
        # Act
        result = handler.set_brightness(12345, "not_a_number")
        
        # Assert
        assert "error" in result
        assert "brightness must be a number" in result["error"]
    
    def test_exception_handling_turn_on(self, handler):
        """Test exception handling in turn_on."""
        # Arrange
        device_id = 12345
        handler.data_provider.turn_on_device = Mock(side_effect=Exception("Unexpected error"))
        
        # Act
        result = handler.turn_on(device_id)
        
        # Assert
        assert "error" in result
        assert "Unexpected error" in result["error"]
    
    def test_exception_handling_turn_off(self, handler):
        """Test exception handling in turn_off."""
        # Arrange
        device_id = 12345
        handler.data_provider.turn_off_device = Mock(side_effect=Exception("Unexpected error"))
        
        # Act
        result = handler.turn_off(device_id)
        
        # Assert
        assert "error" in result
        assert "Unexpected error" in result["error"]
    
    def test_exception_handling_set_brightness(self, handler):
        """Test exception handling in set_brightness."""
        # Arrange
        device_id = 12345
        brightness = 50
        handler.data_provider.set_device_brightness = Mock(side_effect=Exception("Unexpected error"))
        
        # Act
        result = handler.set_brightness(device_id, brightness)
        
        # Assert
        assert "error" in result
        assert "Unexpected error" in result["error"]