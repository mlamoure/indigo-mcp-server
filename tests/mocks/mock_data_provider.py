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
        self.variable_folders = [
            {
                "id": 1,
                "name": "System",
                "description": "System variables"
            },
            {
                "id": 2,
                "name": "Weather",
                "description": "Weather-related variables"
            },
            {
                "id": 3,
                "name": "Home Automation",
                "description": "Home automation control variables"
            }
        ]

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
        """Get all mock variables with minimal fields for listing."""
        # Build folder lookup map
        folder_map = {folder["id"]: folder["name"] for folder in self.variable_folders}

        # Return filtered variables
        filtered_variables = []
        for variable in self.variables:
            # Build minimal variable dict
            minimal_var = {
                "id": variable["id"],
                "name": variable["name"]
            }

            # Add folder name if variable is not in root (folderId != 0)
            folder_id = variable.get("folderId", 0)
            if folder_id != 0:
                folder_name = folder_map.get(folder_id, f"Unknown Folder ({folder_id})")
                minimal_var["folderName"] = folder_name

            filtered_variables.append(minimal_var)

        return filtered_variables

    def get_variable(self, variable_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific mock variable by ID."""
        for variable in self.variables:
            if variable["id"] == variable_id:
                return copy.deepcopy(variable)
        return None

    def get_all_variables_unfiltered(self) -> List[Dict[str, Any]]:
        """Get all mock variables with complete data (unfiltered for vector store)."""
        return [copy.deepcopy(variable) for variable in self.variables]
    
    def get_all_actions(self) -> List[Dict[str, Any]]:
        """Get all mock action groups."""
        return [copy.deepcopy(action) for action in self.actions]
    
    def get_action(self, action_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific mock action group by ID."""
        for action in self.actions:
            if action["id"] == action_id:
                return copy.deepcopy(action)
        return None
    
    def get_action_group(self, action_group_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific action group by ID. In Indigo, actions and action groups are the same."""
        return self.get_action(action_group_id)
    
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
            "variables": self.get_all_variables_unfiltered(),
            "actions": self.get_all_actions()
        }
    
    def turn_on_device(self, device_id: int) -> Dict[str, Any]:
        """Mock turning on a device."""
        device = self.get_device(device_id)
        if not device:
            return {"error": f"Device {device_id} not found"}
        
        previous_state = device.get("states", {}).get("onOffState", False)
        
        # Update device state in mock data
        for dev in self.devices:
            if dev["id"] == device_id:
                dev["states"]["onOffState"] = True
                break
        
        return {
            "changed": not previous_state,
            "previous": previous_state,
            "current": True
        }
    
    def turn_off_device(self, device_id: int) -> Dict[str, Any]:
        """Mock turning off a device."""
        device = self.get_device(device_id)
        if not device:
            return {"error": f"Device {device_id} not found"}
        
        previous_state = device.get("states", {}).get("onOffState", True)
        
        # Update device state in mock data
        for dev in self.devices:
            if dev["id"] == device_id:
                dev["states"]["onOffState"] = False
                break
        
        return {
            "changed": previous_state,
            "previous": previous_state,
            "current": False
        }
    
    def set_device_brightness(self, device_id: int, brightness: float) -> Dict[str, Any]:
        """Mock setting device brightness."""
        device = self.get_device(device_id)
        if not device:
            return {"error": f"Device {device_id} not found"}
        
        # Check if device supports brightness
        if device.get("deviceTypeId") != "dimmer":
            return {"error": f"Device {device_id} does not support brightness control"}
        
        # Normalize brightness value
        if 0 <= brightness <= 1:
            brightness_value = int(brightness * 100)
        elif 0 <= brightness <= 100:
            brightness_value = int(brightness)
        else:
            return {"error": f"Invalid brightness value: {brightness}. Must be 0-1 or 0-100"}
        
        previous_brightness = device.get("states", {}).get("brightness", 0)
        
        # Update device brightness in mock data
        for dev in self.devices:
            if dev["id"] == device_id:
                dev["states"]["brightness"] = brightness_value
                break
        
        return {
            "changed": previous_brightness != brightness_value,
            "previous": previous_brightness,
            "current": brightness_value
        }
    
    def update_variable(self, variable_id: int, value: Any) -> Dict[str, Any]:
        """Mock updating a variable."""
        variable = self.get_variable(variable_id)
        if not variable:
            return {"error": f"Variable {variable_id} not found"}
        
        # Check if variable is read-only
        if variable.get("readOnly", False):
            return {"error": f"Variable {variable_id} is read-only"}
        
        previous_value = variable.get("value", "")
        
        # Update variable value in mock data
        for var in self.variables:
            if var["id"] == variable_id:
                var["value"] = str(value)
                break
        
        return {
            "previous": previous_value,
            "current": str(value)
        }
    
    def execute_action_group(self, action_group_id: int, delay: Optional[int] = None) -> Dict[str, Any]:
        """Mock executing an action group."""
        action = self.get_action(action_group_id)
        if not action:
            return {"error": f"Action group {action_group_id} not found", "success": False}

        return {
            "success": True,
            "job_id": None
        }

    def get_event_log_list(
        self,
        line_count: Optional[int] = None,
        show_timestamp: bool = True
    ) -> List[str]:
        """
        Mock getting event log entries.

        Args:
            line_count: Number of log entries to return (default: all entries)
            show_timestamp: Include timestamps in log entries (default: True)

        Returns:
            List of mock log entry strings
        """
        # Generate mock log entries
        if show_timestamp:
            mock_entries = [
                "2025-01-15 10:30:45  Device 'Living Room Light' on",
                "2025-01-15 10:30:50  Device 'Kitchen Lights' off",
                "2025-01-15 10:31:00  Variable 'House Mode' set to 'Away'",
                "2025-01-15 10:31:15  Action group 'Good Night Scene' executed",
                "2025-01-15 10:31:30  Device 'Front Door Lock' locked",
                "2025-01-15 10:31:45  Error: Device 'Garage Door' communication failure",
                "2025-01-15 10:32:00  Variable 'Security Armed' set to 'True'",
                "2025-01-15 10:32:15  Device 'Kitchen Temperature' reading: 72.5°F",
                "2025-01-15 10:32:30  Action group 'Morning Routine' executed",
                "2025-01-15 10:32:45  Plugin 'MCP Server' started"
            ]
        else:
            mock_entries = [
                "Device 'Living Room Light' on",
                "Device 'Kitchen Lights' off",
                "Variable 'House Mode' set to 'Away'",
                "Action group 'Good Night Scene' executed",
                "Device 'Front Door Lock' locked",
                "Error: Device 'Garage Door' communication failure",
                "Variable 'Security Armed' set to 'True'",
                "Device 'Kitchen Temperature' reading: 72.5°F",
                "Action group 'Morning Routine' executed",
                "Plugin 'MCP Server' started"
            ]

        # Return limited entries if line_count is specified
        if line_count is not None:
            return mock_entries[:line_count]
        return mock_entries

    def create_variable(
        self,
        name: str,
        value: str = "",
        folder_id: int = 0
    ) -> Dict[str, Any]:
        """
        Mock creating a new variable.

        Args:
            name: The variable name (required)
            value: Initial value (default: empty string)
            folder_id: Folder ID for organization (default: 0 = root)

        Returns:
            Dictionary with created variable information or error
        """
        # Validate name
        if not name or not isinstance(name, str):
            return {"error": "Variable name is required and must be a string"}

        # Validate folder_id
        if not isinstance(folder_id, int):
            return {"error": "folder_id must be an integer"}

        # Generate a new variable ID (max existing ID + 1)
        max_id = max([var["id"] for var in self.variables], default=100)
        new_id = max_id + 1

        # Create the new variable
        new_variable = {
            "id": new_id,
            "name": name,
            "value": str(value) if value is not None else "",
            "folderId": folder_id,
            "readOnly": False
        }

        # Add to mock data
        self.variables.append(new_variable)

        # Return created variable information
        return {
            "variable_id": new_id,
            "name": name,
            "value": new_variable["value"],
            "folder_id": folder_id,
            "read_only": False
        }

    def get_variable_folders(self) -> List[Dict[str, Any]]:
        """
        Mock getting all variable folders.

        Returns:
            List of folder dictionaries
        """
        return [copy.deepcopy(folder) for folder in self.variable_folders]