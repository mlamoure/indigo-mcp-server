"""
Indigo data provider implementation for accessing Indigo entities.
"""

try:
    import indigo
except ImportError:
    pass

import logging
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
        Get all variables from Indigo.
        
        Returns:
            List of variable dictionaries with standard fields
        """
        variables = []
        try:
            for var_id in indigo.variables:
                var = indigo.variables[var_id]
                variables.append(dict(var))
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
            "variables": self.get_all_variables(),
            "actions": self.get_all_actions()
        }