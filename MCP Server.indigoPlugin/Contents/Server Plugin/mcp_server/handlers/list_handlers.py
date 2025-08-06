"""
Shared handlers for listing Indigo entities.
Used by both MCP tools and resources for consistent behavior.
"""

import logging
from typing import Dict, List, Any, Optional

from ..adapters.data_provider import DataProvider
from ..common.state_filter import StateFilter
from ..common.indigo_device_types import DeviceClassifier


class ListHandlers:
    """Shared handlers for listing entities."""
    
    def __init__(
        self, 
        data_provider: DataProvider,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize the list handlers.
        
        Args:
            data_provider: Data provider for accessing entity data
            logger: Optional logger instance
        """
        self.data_provider = data_provider
        self.logger = logger or logging.getLogger("Plugin")
    
    def list_all_devices(
        self, 
        state_filter: Optional[Dict[str, Any]] = None,
        device_types: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all devices, optionally filtered by state and/or type.
        
        Args:
            state_filter: Optional state conditions to filter by
            device_types: Optional list of device types to filter by
            
        Returns:
            List of device dictionaries
        """
        try:
            # Get all devices
            devices = self.data_provider.get_all_devices()
            
            # Apply device type filtering if specified
            if device_types:
                filtered_devices = []
                device_type_set = set(device_types)
                
                for device in devices:
                    classified_type = DeviceClassifier.classify_device(device)
                    if classified_type in device_type_set:
                        filtered_devices.append(device)
                
                devices = filtered_devices
            
            # Apply state filtering if specified
            if state_filter:
                devices = StateFilter.filter_by_state(devices, state_filter)
                self.logger.debug(f"Filtered to {len(devices)} devices by state conditions: {state_filter}")
            
            self.logger.info(f"Returning {len(devices)} devices")
            return devices
            
        except Exception as e:
            self.logger.error(f"Error listing devices: {e}")
            raise
    
    def list_all_variables(self) -> List[Dict[str, Any]]:
        """
        Get all variables.
        
        Returns:
            List of variable dictionaries
        """
        try:
            variables = self.data_provider.get_all_variables()
            self.logger.info(f"Returning {len(variables)} variables")
            return variables
            
        except Exception as e:
            self.logger.error(f"Error listing variables: {e}")
            raise
    
    def list_all_action_groups(self) -> List[Dict[str, Any]]:
        """
        Get all action groups.
        
        Returns:
            List of action group dictionaries
        """
        try:
            actions = self.data_provider.get_all_actions()
            self.logger.info(f"Returning {len(actions)} action groups")
            return actions
            
        except Exception as e:
            self.logger.error(f"Error listing action groups: {e}")
            raise
    
    def get_devices_by_state(
        self,
        state_conditions: Dict[str, Any],
        device_types: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Get devices matching specific state conditions.
        
        Args:
            state_conditions: State requirements using Indigo state names
            device_types: Optional list of device types to filter
            
        Returns:
            Dictionary with matching devices and summary
        """
        try:
            # Get devices (optionally filtered by type)
            devices = self.list_all_devices(
                state_filter=state_conditions,
                device_types=device_types
            )
            
            # Create summary
            summary = f"Found {len(devices)} devices matching state conditions"
            if device_types:
                summary += f" (types: {', '.join(device_types)})"
            
            return {
                "devices": devices,
                "count": len(devices),
                "state_conditions": state_conditions,
                "device_types": device_types,
                "summary": summary
            }
            
        except Exception as e:
            self.logger.error(f"Error getting devices by state: {e}")
            raise