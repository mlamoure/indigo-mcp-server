"""
Sample data for testing.
"""

from typing import Dict, List, Any


class SampleData:
    """Sample test data for different scenarios."""
    
    DEVICES = [
        {
            "id": 1,
            "name": "Living Room Dimmer",
            "description": "Main living room ceiling light dimmer",
            "model": "SwitchLinc Dimmer",
            "type": "dimmer",
            "address": "1A.2B.3C",
            "enabled": True,
            "states": {"brightness": 75, "onOffState": True},
            "protocol": "Insteon",
            "deviceTypeId": "dimmer"
        },
        {
            "id": 2,
            "name": "Kitchen Temperature Sensor",
            "description": "Temperature and humidity sensor for kitchen",
            "model": "TempLinc",
            "type": "sensor",
            "address": "2A.3B.4C",
            "enabled": True,
            "states": {"temperature": 72.5, "humidity": 45, "battery": 90},
            "protocol": "Insteon",
            "deviceTypeId": "sensor"
        },
        {
            "id": 3,
            "name": "Front Door Lock",
            "description": "Smart deadbolt for front entrance",
            "model": "Yale Assure Lock",
            "type": "lock",
            "address": "3A.4B.5C",
            "enabled": True,
            "states": {"locked": True, "battery": 85},
            "protocol": "Z-Wave",
            "deviceTypeId": "lock"
        },
        {
            "id": 4,
            "name": "Bedroom Light Switch",
            "description": "On/off switch for bedroom overhead light",
            "model": "SwitchLinc Relay",
            "type": "switch",
            "address": "4A.5B.6C",
            "enabled": True,
            "states": {"onOffState": False},
            "protocol": "Insteon",
            "deviceTypeId": "relay"
        }
    ]
    
    VARIABLES = [
        {
            "id": 101,
            "name": "House Mode",
            "value": "Home",
            "folderId": 1,
            "readOnly": False
        },
        {
            "id": 102,
            "name": "Security System Armed",
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
        },
        {
            "id": 104,
            "name": "Sunset Time",
            "value": "19:45",
            "folderId": 3,
            "readOnly": True
        },
        {
            "id": 105,
            "name": "Vacation Mode",
            "value": "False",
            "folderId": 1,
            "readOnly": False
        }
    ]
    
    ACTIONS = [
        {
            "id": 201,
            "name": "Good Night Scene",
            "folderId": 1,
            "description": "Turn off all lights, lock doors, and arm security"
        },
        {
            "id": 202,
            "name": "Away Mode",
            "folderId": 1,
            "description": "Activate security system and adjust thermostat for away"
        },
        {
            "id": 203,
            "name": "Morning Routine",
            "folderId": 2,
            "description": "Turn on lights, start coffee maker, disarm security"
        },
        {
            "id": 204,
            "name": "Movie Time",
            "folderId": 2,
            "description": "Dim lights, close blinds, turn on entertainment system"
        },
        {
            "id": 205,
            "name": "Vacation Security",
            "folderId": 3,
            "description": "Enhanced security settings for extended absence"
        }
    ]
    
    @classmethod
    def get_device_by_id(cls, device_id: int) -> Dict[str, Any]:
        """Get a device by ID."""
        for device in cls.DEVICES:
            if device["id"] == device_id:
                return device.copy()
        return None
    
    @classmethod
    def get_variable_by_id(cls, variable_id: int) -> Dict[str, Any]:
        """Get a variable by ID."""
        for variable in cls.VARIABLES:
            if variable["id"] == variable_id:
                return variable.copy()
        return None
    
    @classmethod
    def get_action_by_id(cls, action_id: int) -> Dict[str, Any]:
        """Get an action by ID."""
        for action in cls.ACTIONS:
            if action["id"] == action_id:
                return action.copy()
        return None


# Test query scenarios
TEST_QUERIES = {
    "device_search": [
        "find all lights",
        "show me temperature sensors",
        "list all switches in the bedroom",
        "dimmer in living room"
    ],
    "variable_search": [
        "house mode variable",
        "show security variables",
        "temperature variables",
        "all variables with true value"
    ],
    "action_search": [
        "good night scene",
        "show all scenes",
        "morning routine actions",
        "security related actions"
    ],
    "general_search": [
        "everything in bedroom",
        "all security items",
        "temperature related devices",
        "all lighting controls"
    ]
}


# Expected result counts for test queries
EXPECTED_RESULTS = {
    "find all lights": {"devices": 2, "variables": 0, "actions": 0},
    "house mode variable": {"devices": 0, "variables": 1, "actions": 0},
    "good night scene": {"devices": 0, "variables": 0, "actions": 1},
    "temperature": {"devices": 1, "variables": 1, "actions": 0}
}