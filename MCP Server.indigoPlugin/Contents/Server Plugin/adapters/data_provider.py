"""
Abstract data provider interface for accessing Indigo entities.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional


class DataProvider(ABC):
    """Abstract interface for accessing Indigo entity data."""
    
    @abstractmethod
    def get_all_devices(self) -> List[Dict[str, Any]]:
        """
        Get all devices.
        
        Returns:
            List of device dictionaries with standard fields:
            - id: Device ID
            - name: Device name
            - description: Device description
            - model: Device model
            - type: Device type ID
            - address: Device address
            - enabled: Whether device is enabled
            - states: Device states dictionary
        """
        pass
    
    @abstractmethod
    def get_device(self, device_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a specific device by ID.
        
        Args:
            device_id: The device ID
            
        Returns:
            Device dictionary or None if not found
        """
        pass
    
    @abstractmethod
    def get_all_variables(self) -> List[Dict[str, Any]]:
        """
        Get all variables.
        
        Returns:
            List of variable dictionaries with standard fields:
            - id: Variable ID
            - name: Variable name
            - value: Variable value
            - folderId: Folder ID
            - readOnly: Whether variable is read-only
        """
        pass
    
    @abstractmethod
    def get_variable(self, variable_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a specific variable by ID.
        
        Args:
            variable_id: The variable ID
            
        Returns:
            Variable dictionary or None if not found
        """
        pass
    
    @abstractmethod
    def get_all_actions(self) -> List[Dict[str, Any]]:
        """
        Get all action groups.
        
        Returns:
            List of action group dictionaries with standard fields:
            - id: Action group ID
            - name: Action group name
            - folderId: Folder ID
            - description: Action group description
        """
        pass
    
    @abstractmethod
    def get_action(self, action_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a specific action group by ID.
        
        Args:
            action_id: The action group ID
            
        Returns:
            Action group dictionary or None if not found
        """
        pass