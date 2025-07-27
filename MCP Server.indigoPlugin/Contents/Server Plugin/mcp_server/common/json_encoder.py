"""
Custom JSON encoder for handling Indigo entity serialization.
"""

import json
from datetime import datetime, date
from typing import Any


class IndigoJSONEncoder(json.JSONEncoder):
    """JSON encoder that handles datetime objects and other non-serializable types."""
    
    def default(self, obj: Any) -> Any:
        """
        Convert non-serializable objects to serializable format.
        
        Args:
            obj: Object to serialize
            
        Returns:
            Serializable representation of the object
        """
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif hasattr(obj, '__dict__'):
            # Handle custom objects by converting to dict
            return obj.__dict__
        elif isinstance(obj, bytes):
            # Handle bytes by decoding to string
            return obj.decode('utf-8', errors='ignore')
        
        # Let the base class raise TypeError for unsupported types
        return super().default(obj)


def safe_json_dumps(data: Any, indent: int = 2) -> str:
    """
    Safely serialize data to JSON string using custom encoder.
    
    Args:
        data: Data to serialize
        indent: JSON indentation level
        
    Returns:
        JSON string representation
    """
    return json.dumps(data, cls=IndigoJSONEncoder, indent=indent)