"""
Device type definitions for Indigo devices.
"""

from enum import Enum
from typing import List


class IndigoDeviceType(str, Enum):
    """
    Enum for Indigo device types based on deviceTypeId field values.
    
    These values correspond to the deviceTypeId field found in Indigo device dictionaries
    and can be used for filtering devices by type.
    """
    DIMMER = "dimmer"
    RELAY = "relay"
    SENSOR = "sensor"
    MULTIIO = "multiio"
    SPEEDCONTROL = "speedcontrol"
    SPRINKLER = "sprinkler"
    THERMOSTAT = "thermostat"
    DEVICE = "device"  # Base device type
    
    @classmethod
    def get_all_types(cls) -> List[str]:
        """Get list of all device type values."""
        return [device_type.value for device_type in cls]
    
    @classmethod
    def is_valid_type(cls, device_type: str) -> bool:
        """Check if a device type string is valid."""
        return device_type in cls.get_all_types()


class IndigoEntityType(str, Enum):
    """Enum for Indigo entity types."""
    DEVICE = "device"
    VARIABLE = "variable"
    ACTION = "action"
    
    @classmethod
    def get_all_types(cls) -> List[str]:
        """Get list of all entity type values."""
        return [entity_type.value for entity_type in cls]
    
    @classmethod
    def is_valid_type(cls, entity_type: str) -> bool:
        """Check if an entity type string is valid."""
        return entity_type in cls.get_all_types()