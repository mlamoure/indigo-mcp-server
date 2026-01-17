"""
Indigo data provider implementation for accessing Indigo entities.
"""

try:
    import indigo
except ImportError:
    pass

import logging
import time
from typing import Dict, List, Any, Optional

from .data_provider import DataProvider
from ..common.json_encoder import filter_json, KEYS_TO_KEEP_MINIMAL_DEVICES


class IndigoDataProvider(DataProvider):
    """Data provider implementation for accessing Indigo entities."""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize the Indigo data provider.
        
        Args:
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger("Plugin")
    
    def get_all_devices(self) -> List[Dict[str, Any]]:
        """
        Get all devices from Indigo.
        
        Returns:
            List of device dictionaries with minimal fields
        """
        devices = []
        try:
            for dev_id in indigo.devices:
                dev = indigo.devices[dev_id]
                devices.append(dict(dev))
        except Exception as e:
            self.logger.error(f"Error getting all devices: {e}")
            
        # Apply filtering to return only minimal keys
        return filter_json(devices, KEYS_TO_KEEP_MINIMAL_DEVICES)
    
    def get_device(self, device_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a specific device by ID.
        
        Args:
            device_id: The device ID
            
        Returns:
            Device dictionary or None if not found
        """
        try:
            if device_id in indigo.devices:
                dev = indigo.devices[device_id]
                return dict(dev)
        except Exception as e:
            self.logger.error(f"Error getting device {device_id}: {e}")
            
        return None
    
    def get_all_variables(self) -> List[Dict[str, Any]]:
        """
        Get all variables from Indigo with minimal fields for listing.

        Returns:
            List of variable dictionaries with minimal fields:
            - id: Variable ID
            - name: Variable name
            - folderName: Folder name (only if not in root, i.e., folderId != 0)
        """
        variables = []
        try:
            # Build folder lookup map for efficient folder name resolution
            folder_map = {}
            try:
                for folder in indigo.variables.folders:
                    folder_map[folder.id] = folder.name
            except Exception as folder_error:
                self.logger.error(f"Error building folder map: {folder_error}")

            # Get all variables with filtered fields
            for var_id in indigo.variables:
                var = indigo.variables[var_id]

                # Build minimal variable dict
                minimal_var = {
                    "id": var.id,
                    "name": var.name
                }

                # Add folder name if variable is not in root (folderId != 0)
                if hasattr(var, 'folderId') and var.folderId != 0:
                    folder_name = folder_map.get(var.folderId, f"Unknown Folder ({var.folderId})")
                    minimal_var["folderName"] = folder_name

                variables.append(minimal_var)

        except Exception as e:
            self.logger.error(f"Error getting all variables: {e}")

        return variables
    
    def get_variable(self, variable_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a specific variable by ID.

        Args:
            variable_id: The variable ID

        Returns:
            Variable dictionary or None if not found
        """
        try:
            if variable_id in indigo.variables:
                var = indigo.variables[variable_id]
                return dict(var)
        except Exception as e:
            self.logger.error(f"Error getting variable {variable_id}: {e}")

        return None

    def get_all_variables_unfiltered(self) -> List[Dict[str, Any]]:
        """
        Get all variables from Indigo with complete data (unfiltered for vector store).

        Returns:
            List of complete variable dictionaries with all fields
        """
        variables = []
        try:
            for var_id in indigo.variables:
                var = indigo.variables[var_id]
                variables.append(dict(var))
        except Exception as e:
            self.logger.error(f"Error getting all variables (unfiltered): {e}")

        return variables

    def get_all_actions(self) -> List[Dict[str, Any]]:
        """
        Get all action groups from Indigo.
        
        Returns:
            List of action group dictionaries with standard fields
        """
        actions = []
        try:
            for action_id in indigo.actionGroups:
                action = indigo.actionGroups[action_id]
                actions.append(dict(action))
        except Exception as e:
            self.logger.error(f"Error getting all actions: {e}")
            
        return actions
    
    def get_action(self, action_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a specific action group by ID.
        
        Args:
            action_id: The action group ID
            
        Returns:
            Action group dictionary or None if not found
        """
        try:
            if action_id in indigo.actionGroups:
                action = indigo.actionGroups[action_id]
                return dict(action)
        except Exception as e:
            self.logger.error(f"Error getting action {action_id}: {e}")
            
        return None
    
    def get_action_group(self, action_group_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a specific action group by ID.
        
        Args:
            action_group_id: The action group ID
            
        Returns:
            Action group dictionary or None if not found
        """
        return self.get_action(action_group_id)
    
    def get_all_devices_unfiltered(self) -> List[Dict[str, Any]]:
        """
        Get all devices from Indigo with complete data (unfiltered for vector store).
        
        Returns:
            List of complete device dictionaries
        """
        devices = []
        try:
            for dev_id in indigo.devices:
                dev = indigo.devices[dev_id]
                devices.append(dict(dev))
        except Exception as e:
            self.logger.error(f"Error getting all devices (unfiltered): {e}")
            
        return devices
    
    def get_all_entities_for_vector_store(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all entities formatted for vector store updates with complete data.

        Returns:
            Dictionary with 'devices', 'variables', 'actions' keys
        """
        return {
            "devices": self.get_all_devices_unfiltered(),
            "variables": self.get_all_variables_unfiltered(),
            "actions": self.get_all_actions()
        }
    
    def turn_on_device(self, device_id: int) -> Dict[str, Any]:
        """
        Turn on a device.
        
        Args:
            device_id: The device ID to turn on
            
        Returns:
            Dictionary with operation results
        """
        try:
            if device_id not in indigo.devices:
                return {"error": f"Device {device_id} not found"}
            
            # Get initial device state
            device_before = indigo.devices[device_id]
            previous_state = device_before.onState
            
            # Turn on the device
            indigo.device.turnOn(device_id)
            
            # Wait 1 second for device state to update
            time.sleep(1)
            
            # Get fresh device object from Indigo to detect actual state changes
            device_after = indigo.devices[device_id]
            current_state = device_after.onState
            
            return {
                "changed": previous_state != current_state,
                "previous": previous_state,
                "current": current_state,
                "device_name": device_after.name
            }
            
        except Exception as e:
            self.logger.error(f"Error turning on device {device_id}: {e}")
            return {"error": str(e)}
    
    def turn_off_device(self, device_id: int) -> Dict[str, Any]:
        """
        Turn off a device.
        
        Args:
            device_id: The device ID to turn off
            
        Returns:
            Dictionary with operation results
        """
        try:
            if device_id not in indigo.devices:
                return {"error": f"Device {device_id} not found"}
            
            # Get initial device state
            device_before = indigo.devices[device_id]
            previous_state = device_before.onState
            
            # Turn off the device
            indigo.device.turnOff(device_id)
            
            # Wait 1 second for device state to update
            time.sleep(1)
            
            # Get fresh device object from Indigo to detect actual state changes
            device_after = indigo.devices[device_id]
            current_state = device_after.onState
            
            return {
                "changed": previous_state != current_state,
                "previous": previous_state,
                "current": current_state,
                "device_name": device_after.name
            }
            
        except Exception as e:
            self.logger.error(f"Error turning off device {device_id}: {e}")
            return {"error": str(e)}
    
    def set_device_brightness(self, device_id: int, brightness: float) -> Dict[str, Any]:
        """
        Set brightness level for a dimmer device.
        
        Args:
            device_id: The device ID
            brightness: Brightness level (0-1 or 0-100)
            
        Returns:
            Dictionary with operation results
        """
        try:
            if device_id not in indigo.devices:
                return {"error": f"Device {device_id} not found"}
            
            # Get initial device state
            device_before = indigo.devices[device_id]
            
            # Check if device supports brightness
            if not hasattr(device_before, 'brightness'):
                return {"error": f"Device {device_id} does not support brightness control"}
            
            previous_brightness = device_before.brightness
            
            # Normalize brightness value
            # If value is between 0 and 1, convert to 0-100 range
            if 0 <= brightness <= 1:
                brightness_value = int(brightness * 100)
            elif 0 <= brightness <= 100:
                brightness_value = int(brightness)
            else:
                return {"error": f"Invalid brightness value: {brightness}. Must be 0-1 or 0-100"}
            
            # Set brightness
            indigo.dimmer.setBrightness(device_id, value=brightness_value)
            
            # Wait 1 second for device state to update
            time.sleep(1)
            
            # Get fresh device object from Indigo to detect actual state changes
            device_after = indigo.devices[device_id]
            current_brightness = device_after.brightness
            
            return {
                "changed": previous_brightness != current_brightness,
                "previous": previous_brightness,
                "current": current_brightness,
                "device_name": device_after.name
            }
            
        except Exception as e:
            self.logger.error(f"Error setting brightness for device {device_id}: {e}")
            return {"error": str(e)}
    
    def update_variable(self, variable_id: int, value: Any) -> Dict[str, Any]:
        """
        Update a variable's value.
        
        Args:
            variable_id: The variable ID
            value: The new value
            
        Returns:
            Dictionary with operation results
        """
        try:
            if variable_id not in indigo.variables:
                return {"error": f"Variable {variable_id} not found"}
            
            variable = indigo.variables[variable_id]
            
            # Check if variable is read-only
            if hasattr(variable, 'readOnly') and variable.readOnly:
                return {"error": f"Variable {variable_id} is read-only"}
            
            previous_value = variable.value
            
            # Update variable value - convert to string as Indigo variables are strings
            indigo.variable.updateValue(variable_id, value=str(value))
            
            # Get updated value
            variable.refreshFromServer()
            current_value = variable.value
            
            return {
                "previous": previous_value,
                "current": current_value
            }
            
        except Exception as e:
            self.logger.error(f"Error updating variable {variable_id}: {e}")
            return {"error": str(e)}
    
    def execute_action_group(self, action_group_id: int, delay: Optional[int] = None) -> Dict[str, Any]:
        """
        Execute an action group.
        
        Args:
            action_group_id: The action group ID
            delay: Optional delay in seconds before execution
            
        Returns:
            Dictionary with operation results
        """
        try:
            if action_group_id not in indigo.actionGroups:
                return {"error": f"Action group {action_group_id} not found"}
            
            # Execute action group with optional delay
            if delay and delay > 0:
                indigo.actionGroup.execute(action_group_id, delay=delay)
            else:
                indigo.actionGroup.execute(action_group_id)
            
            return {
                "success": True,
                "job_id": None  # Indigo doesn't provide job IDs for action group execution
            }
            
        except Exception as e:
            self.logger.error(f"Error executing action group {action_group_id}: {e}")
            return {"error": str(e), "success": False}

    def get_event_log_list(
        self,
        line_count: Optional[int] = None,
        show_timestamp: bool = True
    ) -> List[str]:
        """
        Get recent event log entries from Indigo server.

        Args:
            line_count: Number of log entries to return (default: all recent entries)
            show_timestamp: Include timestamps in log entries (default: True)

        Returns:
            List of log entry strings
        """
        try:
            # Build parameters for getEventLogList
            params = {
                "returnAsList": True,  # Always return as list for structured data
                "showTimeStamp": show_timestamp
            }

            if line_count is not None:
                params["lineCount"] = line_count

            # Get log entries from Indigo server
            log_entries = indigo.server.getEventLogList(**params)

            return log_entries if log_entries else []

        except Exception as e:
            self.logger.error(f"Error getting event log list: {e}")
            return []

    def create_variable(
        self,
        name: str,
        value: str = "",
        folder_id: int = 0
    ) -> Dict[str, Any]:
        """
        Create a new variable.

        Args:
            name: The variable name (required)
            value: Initial value (default: empty string)
            folder_id: Folder ID for organization (default: 0 = root)

        Returns:
            Dictionary with variable information or error
        """
        try:
            # Validate name
            if not name or not isinstance(name, str):
                return {"error": "Variable name is required and must be a string"}

            # Validate folder_id
            if not isinstance(folder_id, int):
                return {"error": "folder_id must be an integer"}

            # Convert value to string (Indigo variables are always strings)
            value_str = str(value) if value is not None else ""

            # Create the variable using Indigo API
            # indigo.variable.create(name, value=None, folder=0)
            new_variable = indigo.variable.create(name, value=value_str, folder=folder_id)

            # Return the created variable information
            return {
                "variable_id": new_variable.id,
                "name": new_variable.name,
                "value": new_variable.value,
                "folder_id": new_variable.folderId,
                "read_only": new_variable.readOnly if hasattr(new_variable, 'readOnly') else False
            }

        except Exception as e:
            self.logger.error(f"Error creating variable '{name}': {e}")
            return {"error": str(e)}

    def get_variable_folders(self) -> List[Dict[str, Any]]:
        """
        Get all variable folders.

        Returns:
            List of folder dictionaries with standard fields
        """
        folders = []
        try:
            for folder in indigo.variables.folders:
                folders.append({
                    "id": folder.id,
                    "name": folder.name,
                    "description": folder.description if hasattr(folder, 'description') else ""
                })
        except Exception as e:
            self.logger.error(f"Error getting variable folders: {e}")

        return folders

    def set_device_color_levels(
        self,
        device_id: int,
        red_level: Optional[float] = None,
        green_level: Optional[float] = None,
        blue_level: Optional[float] = None,
        white_level: Optional[float] = None,
        white_level2: Optional[float] = None,
        white_temperature: Optional[int] = None,
        delay: int = 0
    ) -> Dict[str, Any]:
        """
        Set color levels for an RGB/RGBW device.

        Args:
            device_id: The device ID
            red_level: Red level (0-100), optional
            green_level: Green level (0-100), optional
            blue_level: Blue level (0-100), optional
            white_level: White level (0-100), optional
            white_level2: Second white level (0-100), optional (for dual white devices)
            white_temperature: White temperature in Kelvin (1200-15000), optional
            delay: Delay in seconds before applying (default: 0)

        Returns:
            Dictionary with operation results
        """
        try:
            if device_id not in indigo.devices:
                return {"error": f"Device {device_id} not found"}

            device = indigo.devices[device_id]

            # Check if device supports color control
            if not hasattr(device, 'supportsRGB') or not device.supportsRGB:
                return {"error": f"Device {device_id} does not support RGB color control"}

            # Build kwargs for setColorLevels
            kwargs = {}
            if red_level is not None:
                kwargs['redLevel'] = red_level
            if green_level is not None:
                kwargs['greenLevel'] = green_level
            if blue_level is not None:
                kwargs['blueLevel'] = blue_level
            if white_level is not None:
                kwargs['whiteLevel'] = white_level
            if white_level2 is not None:
                kwargs['whiteLevel2'] = white_level2
            if white_temperature is not None:
                kwargs['whiteTemperature'] = white_temperature
            if delay > 0:
                kwargs['delay'] = delay

            # Get previous color state
            previous_state = {
                "red": device.redLevel if hasattr(device, 'redLevel') else None,
                "green": device.greenLevel if hasattr(device, 'greenLevel') else None,
                "blue": device.blueLevel if hasattr(device, 'blueLevel') else None,
                "white": device.whiteLevel if hasattr(device, 'whiteLevel') else None,
            }

            # Set color levels
            indigo.dimmer.setColorLevels(device_id, **kwargs)

            # Wait 1 second for device state to update
            time.sleep(1)

            # Get fresh device object
            device_after = indigo.devices[device_id]
            current_state = {
                "red": device_after.redLevel if hasattr(device_after, 'redLevel') else None,
                "green": device_after.greenLevel if hasattr(device_after, 'greenLevel') else None,
                "blue": device_after.blueLevel if hasattr(device_after, 'blueLevel') else None,
                "white": device_after.whiteLevel if hasattr(device_after, 'whiteLevel') else None,
            }

            return {
                "success": True,
                "previous": previous_state,
                "current": current_state,
                "device_name": device_after.name
            }

        except Exception as e:
            self.logger.error(f"Error setting color levels for device {device_id}: {e}")
            return {"error": str(e)}

    def set_thermostat_heat_setpoint(self, device_id: int, value: float) -> Dict[str, Any]:
        """
        Set heating setpoint for a thermostat device.

        Args:
            device_id: The device ID
            value: Temperature setpoint value

        Returns:
            Dictionary with operation results
        """
        try:
            if device_id not in indigo.devices:
                return {"error": f"Device {device_id} not found"}

            device = indigo.devices[device_id]

            # Check if device is a thermostat
            if device.deviceTypeId != indigo.kDeviceTypeId.Thermostat:
                return {"error": f"Device {device_id} is not a thermostat"}

            # Check if device supports heat setpoint
            if not device.pluginProps.get("SupportsHeatSetpoint", False):
                return {"error": f"Device {device_id} does not support heat setpoint"}

            # Get previous setpoint
            previous_setpoint = device.heatSetpoint if hasattr(device, 'heatSetpoint') else None

            # Set heat setpoint
            indigo.thermostat.setHeatSetpoint(device_id, value=value)

            # Wait 1 second for device state to update
            time.sleep(1)

            # Get fresh device object
            device_after = indigo.devices[device_id]
            current_setpoint = device_after.heatSetpoint if hasattr(device_after, 'heatSetpoint') else None

            return {
                "success": True,
                "previous": previous_setpoint,
                "current": current_setpoint,
                "device_name": device_after.name
            }

        except Exception as e:
            self.logger.error(f"Error setting heat setpoint for device {device_id}: {e}")
            return {"error": str(e)}

    def set_thermostat_cool_setpoint(self, device_id: int, value: float) -> Dict[str, Any]:
        """
        Set cooling setpoint for a thermostat device.

        Args:
            device_id: The device ID
            value: Temperature setpoint value

        Returns:
            Dictionary with operation results
        """
        try:
            if device_id not in indigo.devices:
                return {"error": f"Device {device_id} not found"}

            device = indigo.devices[device_id]

            # Check if device is a thermostat
            if device.deviceTypeId != indigo.kDeviceTypeId.Thermostat:
                return {"error": f"Device {device_id} is not a thermostat"}

            # Check if device supports cool setpoint
            if not device.pluginProps.get("SupportsCoolSetpoint", False):
                return {"error": f"Device {device_id} does not support cool setpoint"}

            # Get previous setpoint
            previous_setpoint = device.coolSetpoint if hasattr(device, 'coolSetpoint') else None

            # Set cool setpoint
            indigo.thermostat.setCoolSetpoint(device_id, value=value)

            # Wait 1 second for device state to update
            time.sleep(1)

            # Get fresh device object
            device_after = indigo.devices[device_id]
            current_setpoint = device_after.coolSetpoint if hasattr(device_after, 'coolSetpoint') else None

            return {
                "success": True,
                "previous": previous_setpoint,
                "current": current_setpoint,
                "device_name": device_after.name
            }

        except Exception as e:
            self.logger.error(f"Error setting cool setpoint for device {device_id}: {e}")
            return {"error": str(e)}

    def set_thermostat_hvac_mode(self, device_id: int, mode: str) -> Dict[str, Any]:
        """
        Set HVAC operating mode for a thermostat device.

        Args:
            device_id: The device ID
            mode: HVAC mode (heat, cool, auto, off, heatCool, programHeat, programCool, programAuto)

        Returns:
            Dictionary with operation results
        """
        try:
            if device_id not in indigo.devices:
                return {"error": f"Device {device_id} not found"}

            device = indigo.devices[device_id]

            # Check if device is a thermostat
            if device.deviceTypeId != indigo.kDeviceTypeId.Thermostat:
                return {"error": f"Device {device_id} is not a thermostat"}

            # Check if device supports HVAC mode
            if not device.pluginProps.get("SupportsHvacOperationMode", False):
                return {"error": f"Device {device_id} does not support HVAC mode control"}

            # Get previous mode
            previous_mode = device.hvacMode if hasattr(device, 'hvacMode') else None

            # Map mode string to indigo.kHvacMode enum
            mode_map = {
                "heat": indigo.kHvacMode.Heat,
                "cool": indigo.kHvacMode.Cool,
                "auto": indigo.kHvacMode.HeatCool,
                "off": indigo.kHvacMode.Off,
                "heatcool": indigo.kHvacMode.HeatCool,
                "programheat": indigo.kHvacMode.ProgramHeat,
                "programcool": indigo.kHvacMode.ProgramCool,
                "programauto": indigo.kHvacMode.ProgramAuto,
            }

            mode_lower = mode.lower()
            if mode_lower not in mode_map:
                return {"error": f"Invalid HVAC mode: {mode}. Valid modes: {', '.join(mode_map.keys())}"}

            # Set HVAC mode
            indigo.thermostat.setHvacMode(device_id, value=mode_map[mode_lower])

            # Wait 1 second for device state to update
            time.sleep(1)

            # Get fresh device object
            device_after = indigo.devices[device_id]
            current_mode = device_after.hvacMode if hasattr(device_after, 'hvacMode') else None

            return {
                "success": True,
                "previous": str(previous_mode) if previous_mode else None,
                "current": str(current_mode) if current_mode else None,
                "device_name": device_after.name
            }

        except Exception as e:
            self.logger.error(f"Error setting HVAC mode for device {device_id}: {e}")
            return {"error": str(e)}

    def set_thermostat_fan_mode(self, device_id: int, mode: str) -> Dict[str, Any]:
        """
        Set fan operating mode for a thermostat device.

        Args:
            device_id: The device ID
            mode: Fan mode (auto, alwaysOn)

        Returns:
            Dictionary with operation results
        """
        try:
            if device_id not in indigo.devices:
                return {"error": f"Device {device_id} not found"}

            device = indigo.devices[device_id]

            # Check if device is a thermostat
            if device.deviceTypeId != indigo.kDeviceTypeId.Thermostat:
                return {"error": f"Device {device_id} is not a thermostat"}

            # Check if device supports fan mode
            if not device.pluginProps.get("SupportsHvacFanMode", False):
                return {"error": f"Device {device_id} does not support fan mode control"}

            # Get previous mode
            previous_mode = device.fanMode if hasattr(device, 'fanMode') else None

            # Map mode string to indigo.kFanMode enum
            mode_map = {
                "auto": indigo.kFanMode.Auto,
                "alwayson": indigo.kFanMode.AlwaysOn,
            }

            mode_lower = mode.lower()
            if mode_lower not in mode_map:
                return {"error": f"Invalid fan mode: {mode}. Valid modes: {', '.join(mode_map.keys())}"}

            # Set fan mode
            indigo.thermostat.setFanMode(device_id, value=mode_map[mode_lower])

            # Wait 1 second for device state to update
            time.sleep(1)

            # Get fresh device object
            device_after = indigo.devices[device_id]
            current_mode = device_after.fanMode if hasattr(device_after, 'fanMode') else None

            return {
                "success": True,
                "previous": str(previous_mode) if previous_mode else None,
                "current": str(current_mode) if current_mode else None,
                "device_name": device_after.name
            }

        except Exception as e:
            self.logger.error(f"Error setting fan mode for device {device_id}: {e}")
            return {"error": str(e)}