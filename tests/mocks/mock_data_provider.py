"""
Mock data provider for testing.
"""

import copy
from typing import Dict, List, Any, Optional
from mcp_server.adapters.data_provider import DataProvider


class MockDataProvider(DataProvider):
    """Mock data provider for testing."""
    
    def __init__(self):
        """Initialize with sample test data."""
        self.devices = [
            {
                "id": 1,
                "name": "Living Room Light",
                "description": "Main living room ceiling light",
                "model": "Dimmer Switch",
                "type": "dimmer",
                "address": "A1",
                "enabled": True,
                "states": {"brightness": 75, "onOffState": True},
                "protocol": "X10",
                "deviceTypeId": "dimmer"
            },
            {
                "id": 2,
                "name": "Kitchen Temperature",
                "description": "Kitchen temperature sensor",
                "model": "TempLinc",
                "type": "sensor",
                "address": "B2",
                "enabled": True,
                "states": {"temperature": 72.5, "humidity": 45},
                "protocol": "Insteon",
                "deviceTypeId": "sensor"
            },
            {
                "id": 3,
                "name": "Front Door Lock",
                "description": "Smart lock for front door",
                "model": "Yale Connect",
                "type": "lock",
                "address": "C3",
                "enabled": True,
                "states": {"locked": True, "battery": 85},
                "protocol": "Z-Wave",
                "deviceTypeId": "lock"
            },
            {
                "id": 4,
                "name": "Bedroom Light Switch",
                "description": "On/off switch for bedroom lights",
                "model": "Switch Relay",
                "type": "switch",
                "address": "D4",
                "enabled": True,
                "states": {"onOffState": False},
                "protocol": "Insteon",
                "deviceTypeId": "switch"
            },
            {
                "id": 5,
                "name": "Kitchen Lights",
                "description": "Under cabinet LED lights",
                "model": "LED Controller",
                "type": "dimmer",
                "address": "E5",
                "enabled": True,
                "states": {"brightness": 100, "onOffState": True},
                "protocol": "Z-Wave",
                "deviceTypeId": "dimmer"
            }
        ]
        
        self.variables = [
            {
                "id": 101,
                "name": "House Mode",
                "value": "Home",
                "folderId": 1,
                "readOnly": False
            },
            {
                "id": 102,
                "name": "Security Armed",
                "value": "False",
                "folderId": 1,
                "readOnly": False
            },
            {
                "id": 103,
                "name": "Outside Temperature",
                "value": "68.2",
                "folderId": 2,
                "readOnly": True
            }
        ]
        
        self.actions = [
            {
                "id": 201,
                "name": "Good Night Scene",
                "folderId": 1,
                "description": "Turn off all lights and lock doors"
            },
            {
                "id": 202,
                "name": "Away Mode",
                "folderId": 1,
                "description": "Activate security and adjust thermostats"
            },
            {
                "id": 203,
                "name": "Morning Routine",
                "folderId": 2,
                "description": "Turn on lights and start coffee"
            }
        ]
    
    def get_all_devices(self) -> List[Dict[str, Any]]:
        """Get all mock devices."""
        return [copy.deepcopy(device) for device in self.devices]
    
    def get_device(self, device_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific mock device by ID."""
        for device in self.devices:
            if device["id"] == device_id:
                return copy.deepcopy(device)
        return None
    
    def get_all_variables(self) -> List[Dict[str, Any]]:
        """Get all mock variables."""
        return [copy.deepcopy(variable) for variable in self.variables]
    
    def get_variable(self, variable_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific mock variable by ID."""
        for variable in self.variables:
            if variable["id"] == variable_id:
                return copy.deepcopy(variable)
        return None
    
    def get_all_actions(self) -> List[Dict[str, Any]]:
        """Get all mock action groups."""
        return [copy.deepcopy(action) for action in self.actions]
    
    def get_action(self, action_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific mock action group by ID."""
        for action in self.actions:
            if action["id"] == action_id:
                return copy.deepcopy(action)
        return None
    
    def add_device(self, device: Dict[str, Any]) -> None:
        """Add a device to the mock data."""
        self.devices.append(device)
    
    def add_variable(self, variable: Dict[str, Any]) -> None:
        """Add a variable to the mock data."""
        self.variables.append(variable)
    
    def add_action(self, action: Dict[str, Any]) -> None:
        """Add an action to the mock data."""
        self.actions.append(action)
    
    def get_all_entities_for_vector_store(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all entities formatted for vector store updates.
        
        Returns:
            Dictionary with 'devices', 'variables', 'actions' keys
        """
        return {
            "devices": self.get_all_devices(),
            "variables": self.get_all_variables(),
            "actions": self.get_all_actions()
        }