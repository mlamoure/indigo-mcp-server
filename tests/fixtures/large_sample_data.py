"""
Large sample data for comprehensive testing.
Contains 20+ items per entity type to ensure we test beyond LanceDB's default limit.
"""

class LargeSampleData:
    """Large dataset for testing with >10 items per entity type."""
    
    # 25 Devices - various types to test comprehensive scenarios
    DEVICES = [
        # Lighting devices (1-8)
        {"id": 1001, "name": "Living Room Dimmer", "description": "Main ceiling light dimmer control", 
         "model": "SwitchLinc Dimmer", "type": "dimmer", "address": "1A.2B.3C", "enabled": True,
         "states": {"brightness": 75, "onOffState": True}, "protocol": "Insteon", "deviceTypeId": "dimmer"},
        {"id": 1002, "name": "Kitchen Light Switch", "description": "Kitchen overhead lighting", 
         "model": "SwitchLinc Relay", "type": "relay", "address": "1A.2B.3D", "enabled": True,
         "states": {"onOffState": True}, "protocol": "Insteon", "deviceTypeId": "relay"},
        {"id": 1003, "name": "Bedroom Dimmer", "description": "Master bedroom dimmer switch", 
         "model": "SwitchLinc Dimmer", "type": "dimmer", "address": "1A.2B.3E", "enabled": True,
         "states": {"brightness": 50, "onOffState": False}, "protocol": "Insteon", "deviceTypeId": "dimmer"},
        {"id": 1004, "name": "Hallway Light", "description": "Hallway ceiling light", 
         "model": "SwitchLinc Relay", "type": "relay", "address": "1A.2B.3F", "enabled": True,
         "states": {"onOffState": False}, "protocol": "Insteon", "deviceTypeId": "relay"},
        {"id": 1005, "name": "Bathroom Vanity", "description": "Bathroom vanity lights", 
         "model": "SwitchLinc Dimmer", "type": "dimmer", "address": "1A.2B.40", "enabled": True,
         "states": {"brightness": 100, "onOffState": True}, "protocol": "Insteon", "deviceTypeId": "dimmer"},
        {"id": 1006, "name": "Office Lamp", "description": "Office desk lamp module", 
         "model": "LampLinc", "type": "dimmer", "address": "1A.2B.41", "enabled": True,
         "states": {"brightness": 60, "onOffState": True}, "protocol": "Insteon", "deviceTypeId": "dimmer"},
        {"id": 1007, "name": "Garage Light", "description": "Garage overhead lights", 
         "model": "SwitchLinc Relay", "type": "relay", "address": "1A.2B.42", "enabled": True,
         "states": {"onOffState": False}, "protocol": "Insteon", "deviceTypeId": "relay"},
        {"id": 1008, "name": "Porch Light", "description": "Front porch light fixture", 
         "model": "SwitchLinc Dimmer", "type": "dimmer", "address": "1A.2B.43", "enabled": True,
         "states": {"brightness": 40, "onOffState": True}, "protocol": "Insteon", "deviceTypeId": "dimmer"},
        
        # Sensors (9-16)
        {"id": 1009, "name": "Living Room Temperature", "description": "Living room temp/humidity sensor", 
         "model": "Wireless Thermostat", "type": "sensor", "address": "1A.2B.44", "enabled": True,
         "states": {"temperature": 72.5, "humidity": 45}, "protocol": "Insteon", "deviceTypeId": "sensor"},
        {"id": 1010, "name": "Kitchen Motion", "description": "Kitchen motion detector", 
         "model": "Motion Sensor II", "type": "sensor", "address": "1A.2B.45", "enabled": True,
         "states": {"motion": False, "battery": 85}, "protocol": "Insteon", "deviceTypeId": "sensor"},
        {"id": 1011, "name": "Front Door Sensor", "description": "Front door open/close sensor", 
         "model": "Open/Close Sensor", "type": "sensor", "address": "1A.2B.46", "enabled": True,
         "states": {"isOpen": False, "battery": 92}, "protocol": "Insteon", "deviceTypeId": "sensor"},
        {"id": 1012, "name": "Garage Door Sensor", "description": "Garage door position sensor", 
         "model": "Open/Close Sensor", "type": "sensor", "address": "1A.2B.47", "enabled": True,
         "states": {"isOpen": False, "battery": 78}, "protocol": "Insteon", "deviceTypeId": "sensor"},
        {"id": 1013, "name": "Basement Water Sensor", "description": "Basement water leak detector", 
         "model": "Leak Sensor", "type": "sensor", "address": "1A.2B.48", "enabled": True,
         "states": {"wetness": False, "battery": 95}, "protocol": "Insteon", "deviceTypeId": "sensor"},
        {"id": 1014, "name": "Bedroom Temperature", "description": "Master bedroom temperature sensor", 
         "model": "Wireless Thermostat", "type": "sensor", "address": "1A.2B.49", "enabled": True,
         "states": {"temperature": 70.0, "humidity": 42}, "protocol": "Insteon", "deviceTypeId": "sensor"},
        {"id": 1015, "name": "Hallway Motion", "description": "Hallway motion sensor", 
         "model": "Motion Sensor II", "type": "sensor", "address": "1A.2B.4A", "enabled": True,
         "states": {"motion": False, "battery": 88}, "protocol": "Insteon", "deviceTypeId": "sensor"},
        {"id": 1016, "name": "Back Door Sensor", "description": "Back door security sensor", 
         "model": "Open/Close Sensor", "type": "sensor", "address": "1A.2B.4B", "enabled": True,
         "states": {"isOpen": False, "battery": 81}, "protocol": "Insteon", "deviceTypeId": "sensor"},
        
        # Thermostats (17-19)
        {"id": 1017, "name": "Main Thermostat", "description": "Main floor HVAC control", 
         "model": "Smart Thermostat", "type": "thermostat", "address": "1A.2B.4C", "enabled": True,
         "states": {"temperature": 72, "setpoint": 72, "mode": "auto", "fanMode": "auto"}, 
         "protocol": "Insteon", "deviceTypeId": "thermostat"},
        {"id": 1018, "name": "Upstairs Thermostat", "description": "Second floor climate control", 
         "model": "Smart Thermostat", "type": "thermostat", "address": "1A.2B.4D", "enabled": True,
         "states": {"temperature": 71, "setpoint": 70, "mode": "cool", "fanMode": "on"}, 
         "protocol": "Insteon", "deviceTypeId": "thermostat"},
        {"id": 1019, "name": "Basement Thermostat", "description": "Basement zone control", 
         "model": "Smart Thermostat", "type": "thermostat", "address": "1A.2B.4E", "enabled": True,
         "states": {"temperature": 68, "setpoint": 68, "mode": "off", "fanMode": "auto"}, 
         "protocol": "Insteon", "deviceTypeId": "thermostat"},
        
        # Outlets and Appliances (20-25)
        {"id": 1020, "name": "Coffee Maker Outlet", "description": "Kitchen coffee maker control", 
         "model": "On/Off Module", "type": "relay", "address": "1A.2B.4F", "enabled": True,
         "states": {"onOffState": False}, "protocol": "Insteon", "deviceTypeId": "relay"},
        {"id": 1021, "name": "TV Power Outlet", "description": "Living room TV power control", 
         "model": "On/Off Module", "type": "relay", "address": "1A.2B.50", "enabled": True,
         "states": {"onOffState": True}, "protocol": "Insteon", "deviceTypeId": "relay"},
        {"id": 1022, "name": "Fan Control", "description": "Bedroom ceiling fan speed control", 
         "model": "FanLinc", "type": "speedcontrol", "address": "1A.2B.51", "enabled": True,
         "states": {"speed": 2, "onOffState": True}, "protocol": "Insteon", "deviceTypeId": "speedcontrol"},
        {"id": 1023, "name": "Sprinkler Zone 1", "description": "Front yard sprinkler control", 
         "model": "IOLinc", "type": "sprinkler", "address": "1A.2B.52", "enabled": True,
         "states": {"onOffState": False}, "protocol": "Insteon", "deviceTypeId": "sprinkler"},
        {"id": 1024, "name": "Pool Pump", "description": "Swimming pool pump control", 
         "model": "Heavy Duty Module", "type": "relay", "address": "1A.2B.53", "enabled": True,
         "states": {"onOffState": False}, "protocol": "Insteon", "deviceTypeId": "relay"},
        {"id": 1025, "name": "Holiday Lights", "description": "Outdoor holiday lighting control", 
         "model": "Outdoor Module", "type": "relay", "address": "1A.2B.54", "enabled": True,
         "states": {"onOffState": False}, "protocol": "Insteon", "deviceTypeId": "relay"},
    ]
    
    # 22 Variables - various types and values
    VARIABLES = [
        {"id": 2001, "name": "House Mode", "value": "Home", "folderId": 1, "readOnly": False},
        {"id": 2002, "name": "Security Armed", "value": "False", "folderId": 1, "readOnly": False},
        {"id": 2003, "name": "Vacation Mode", "value": "False", "folderId": 1, "readOnly": False},
        {"id": 2004, "name": "Guest Mode", "value": "False", "folderId": 1, "readOnly": False},
        {"id": 2005, "name": "Night Mode", "value": "True", "folderId": 1, "readOnly": False},
        {"id": 2006, "name": "Temperature Setpoint", "value": "72", "folderId": 2, "readOnly": False},
        {"id": 2007, "name": "Humidity Target", "value": "45", "folderId": 2, "readOnly": False},
        {"id": 2008, "name": "Energy Saving Mode", "value": "True", "folderId": 2, "readOnly": False},
        {"id": 2009, "name": "Sunrise Time", "value": "06:45", "folderId": 3, "readOnly": True},
        {"id": 2010, "name": "Sunset Time", "value": "19:30", "folderId": 3, "readOnly": True},
        {"id": 2011, "name": "Is Daytime", "value": "True", "folderId": 3, "readOnly": True},
        {"id": 2012, "name": "Motion Timeout", "value": "300", "folderId": 4, "readOnly": False},
        {"id": 2013, "name": "Dim Level Default", "value": "50", "folderId": 4, "readOnly": False},
        {"id": 2014, "name": "Auto Lock Delay", "value": "180", "folderId": 4, "readOnly": False},
        {"id": 2015, "name": "Alarm Active", "value": "False", "folderId": 5, "readOnly": False},
        {"id": 2016, "name": "Last Motion Time", "value": "2024-01-15 14:30:00", "folderId": 5, "readOnly": True},
        {"id": 2017, "name": "Door Count", "value": "0", "folderId": 5, "readOnly": True},
        {"id": 2018, "name": "Power Usage", "value": "2450", "folderId": 6, "readOnly": True},
        {"id": 2019, "name": "Water Usage", "value": "125", "folderId": 6, "readOnly": True},
        {"id": 2020, "name": "HVAC Runtime", "value": "420", "folderId": 6, "readOnly": True},
        {"id": 2021, "name": "Debug Mode", "value": "False", "folderId": 7, "readOnly": False},
        {"id": 2022, "name": "System Version", "value": "2024.2.0", "folderId": 7, "readOnly": True},
    ]
    
    # 23 Actions - various automation scenarios
    ACTIONS = [
        {"id": 3001, "name": "Good Morning", "folderId": 1, 
         "description": "Turn on lights, disarm security, adjust thermostat for morning"},
        {"id": 3002, "name": "Good Night", "folderId": 1, 
         "description": "Turn off all lights, lock doors, arm security system"},
        {"id": 3003, "name": "Away Mode", "folderId": 1, 
         "description": "Set house to away mode with security and energy savings"},
        {"id": 3004, "name": "Home Mode", "folderId": 1, 
         "description": "Welcome home scene with lights and comfort settings"},
        {"id": 3005, "name": "Movie Time", "folderId": 2, 
         "description": "Dim lights, turn on TV, set audio system"},
        {"id": 3006, "name": "Dinner Scene", "folderId": 2, 
         "description": "Set dining room lights, play background music"},
        {"id": 3007, "name": "Party Mode", "folderId": 2, 
         "description": "Set festive lighting and music throughout house"},
        {"id": 3008, "name": "Reading Mode", "folderId": 2, 
         "description": "Optimal lighting for reading in living room"},
        {"id": 3009, "name": "All Lights Off", "folderId": 3, 
         "description": "Turn off every light in the house"},
        {"id": 3010, "name": "All Lights On", "folderId": 3, 
         "description": "Turn on all lights to full brightness"},
        {"id": 3011, "name": "Outdoor Lights On", "folderId": 3, 
         "description": "Turn on all exterior lighting"},
        {"id": 3012, "name": "Outdoor Lights Off", "folderId": 3, 
         "description": "Turn off all exterior lighting"},
        {"id": 3013, "name": "Panic Button", "folderId": 4, 
         "description": "Flash all lights, sound alarm, send notifications"},
        {"id": 3014, "name": "Fire Alert", "folderId": 4, 
         "description": "Emergency response for fire detection"},
        {"id": 3015, "name": "Water Leak Response", "folderId": 4, 
         "description": "Shut off water, send alerts for leak detection"},
        {"id": 3016, "name": "Intrusion Alert", "folderId": 4, 
         "description": "Security response for unauthorized entry"},
        {"id": 3017, "name": "Morning Coffee", "folderId": 5, 
         "description": "Start coffee maker, turn on kitchen lights"},
        {"id": 3018, "name": "Bedtime Routine", "folderId": 5, 
         "description": "Gradual dimming, lock check, thermostat adjustment"},
        {"id": 3019, "name": "Pet Care", "folderId": 5, 
         "description": "Activate pet feeders, adjust temperature"},
        {"id": 3020, "name": "Plant Watering", "folderId": 5, 
         "description": "Run sprinkler zones for garden and lawn"},
        {"id": 3021, "name": "Energy Save Mode", "folderId": 6, 
         "description": "Optimize all systems for energy efficiency"},
        {"id": 3022, "name": "Test All Systems", "folderId": 7, 
         "description": "Run diagnostic test on all devices"},
        {"id": 3023, "name": "Reset to Defaults", "folderId": 7, 
         "description": "Reset all devices to default settings"},
    ]
    
    @classmethod
    def get_device_count(cls):
        """Get the number of devices in the dataset."""
        return len(cls.DEVICES)
    
    @classmethod
    def get_variable_count(cls):
        """Get the number of variables in the dataset."""
        return len(cls.VARIABLES)
    
    @classmethod
    def get_action_count(cls):
        """Get the number of actions in the dataset."""
        return len(cls.ACTIONS)
    
    @classmethod
    def get_total_count(cls):
        """Get the total number of entities."""
        return len(cls.DEVICES) + len(cls.VARIABLES) + len(cls.ACTIONS)
    
    @classmethod
    def get_subset(cls, device_count=None, variable_count=None, action_count=None):
        """Get a subset of the data for specific test scenarios."""
        devices = cls.DEVICES[:device_count] if device_count else cls.DEVICES
        variables = cls.VARIABLES[:variable_count] if variable_count else cls.VARIABLES
        actions = cls.ACTIONS[:action_count] if action_count else cls.ACTIONS
        return {
            "devices": devices,
            "variables": variables,
            "actions": actions
        }