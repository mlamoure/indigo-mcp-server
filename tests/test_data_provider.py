"""
Tests for data provider implementations.
"""

import pytest
from tests.mocks.mock_data_provider import MockDataProvider


class TestMockDataProvider:
    """Test cases for the MockDataProvider class."""
    
    def test_initialization(self):
        """Test mock data provider initialization."""
        provider = MockDataProvider()
        
        # Check that sample data is loaded
        assert len(provider.devices) == 5
        assert len(provider.variables) == 3
        assert len(provider.actions) == 3
    
    def test_get_all_devices(self, mock_data_provider):
        """Test getting all devices."""
        devices = mock_data_provider.get_all_devices()
        
        assert len(devices) == 5
        assert all("id" in device for device in devices)
        assert all("name" in device for device in devices)
        assert all("type" in device for device in devices)
        
        # Test that we get copies, not references
        devices[0]["name"] = "Modified"
        original_devices = mock_data_provider.get_all_devices()
        assert original_devices[0]["name"] != "Modified"
    
    def test_get_device(self, mock_data_provider):
        """Test getting specific device."""
        device = mock_data_provider.get_device(1)
        
        assert device is not None
        assert device["id"] == 1
        assert device["name"] == "Living Room Light"
        assert device["type"] == "dimmer"
        
        # Test non-existent device
        device = mock_data_provider.get_device(999)
        assert device is None
    
    def test_get_all_variables(self, mock_data_provider):
        """Test getting all variables."""
        variables = mock_data_provider.get_all_variables()
        
        assert len(variables) == 3
        assert all("id" in var for var in variables)
        assert all("name" in var for var in variables)
        assert all("value" in var for var in variables)
    
    def test_get_variable(self, mock_data_provider):
        """Test getting specific variable."""
        variable = mock_data_provider.get_variable(101)
        
        assert variable is not None
        assert variable["id"] == 101
        assert variable["name"] == "House Mode"
        assert variable["value"] == "Home"
        
        # Test non-existent variable
        variable = mock_data_provider.get_variable(999)
        assert variable is None
    
    def test_get_all_actions(self, mock_data_provider):
        """Test getting all actions."""
        actions = mock_data_provider.get_all_actions()
        
        assert len(actions) == 3
        assert all("id" in action for action in actions)
        assert all("name" in action for action in actions)
        assert all("folderId" in action for action in actions)
    
    def test_get_action(self, mock_data_provider):
        """Test getting specific action."""
        action = mock_data_provider.get_action(201)
        
        assert action is not None
        assert action["id"] == 201
        assert action["name"] == "Good Night Scene"
        assert "description" in action
        
        # Test non-existent action
        action = mock_data_provider.get_action(999)
        assert action is None
    
    def test_add_device(self, mock_data_provider):
        """Test adding a device."""
        new_device = {
            "id": 6,
            "name": "Test Device",
            "type": "test",
            "enabled": True
        }
        
        initial_count = len(mock_data_provider.get_all_devices())
        mock_data_provider.add_device(new_device)
        
        devices = mock_data_provider.get_all_devices()
        assert len(devices) == initial_count + 1
        
        added_device = mock_data_provider.get_device(6)
        assert added_device is not None
        assert added_device["name"] == "Test Device"
    
    def test_add_variable(self, mock_data_provider):
        """Test adding a variable."""
        new_variable = {
            "id": 104,
            "name": "Test Variable",
            "value": "test_value",
            "folderId": 1
        }
        
        initial_count = len(mock_data_provider.get_all_variables())
        mock_data_provider.add_variable(new_variable)
        
        variables = mock_data_provider.get_all_variables()
        assert len(variables) == initial_count + 1
        
        added_variable = mock_data_provider.get_variable(104)
        assert added_variable is not None
        assert added_variable["name"] == "Test Variable"
    
    def test_add_action(self, mock_data_provider):
        """Test adding an action."""
        new_action = {
            "id": 204,
            "name": "Test Action",
            "folderId": 1,
            "description": "Test action description"
        }
        
        initial_count = len(mock_data_provider.get_all_actions())
        mock_data_provider.add_action(new_action)
        
        actions = mock_data_provider.get_all_actions()
        assert len(actions) == initial_count + 1
        
        added_action = mock_data_provider.get_action(204)
        assert added_action is not None
        assert added_action["name"] == "Test Action"
    
    def test_device_data_structure(self, mock_data_provider):
        """Test that device data has expected structure."""
        devices = mock_data_provider.get_all_devices()
        
        for device in devices:
            # Required fields
            assert "id" in device
            assert "name" in device
            assert "type" in device
            assert "enabled" in device
            
            # Optional fields that should exist in mock data
            assert "description" in device
            assert "model" in device
            assert "address" in device
            assert "states" in device
            assert "protocol" in device
            assert "deviceTypeId" in device
            
            # Type checks
            assert isinstance(device["id"], int)
            assert isinstance(device["name"], str)
            assert isinstance(device["enabled"], bool)
            assert isinstance(device["states"], dict)
    
    def test_variable_data_structure(self, mock_data_provider):
        """Test that variable data has expected structure."""
        variables = mock_data_provider.get_all_variables()
        
        for variable in variables:
            # Required fields
            assert "id" in variable
            assert "name" in variable
            assert "value" in variable
            assert "folderId" in variable
            assert "readOnly" in variable
            
            # Type checks
            assert isinstance(variable["id"], int)
            assert isinstance(variable["name"], str)
            assert isinstance(variable["folderId"], int)
            assert isinstance(variable["readOnly"], bool)
    
    def test_action_data_structure(self, mock_data_provider):
        """Test that action data has expected structure."""
        actions = mock_data_provider.get_all_actions()
        
        for action in actions:
            # Required fields
            assert "id" in action
            assert "name" in action
            assert "folderId" in action
            assert "description" in action
            
            # Type checks
            assert isinstance(action["id"], int)
            assert isinstance(action["name"], str)
            assert isinstance(action["folderId"], int)
            assert isinstance(action["description"], str)