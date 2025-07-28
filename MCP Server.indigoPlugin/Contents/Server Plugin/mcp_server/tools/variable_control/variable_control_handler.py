"""
Variable control handler for MCP server.
"""

import logging
from typing import Dict, Any, Optional, Union

from ...adapters.data_provider import DataProvider


class VariableControlHandler:
    """Handler for variable control operations."""
    
    def __init__(
        self,
        data_provider: DataProvider,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize the variable control handler.
        
        Args:
            data_provider: Data provider for variable operations
            logger: Optional logger instance
        """
        self.data_provider = data_provider
        self.logger = logger or logging.getLogger("Plugin")
    
    def update(self, variable_id: int, value: Union[str, int, float, bool]) -> Dict[str, Any]:
        """
        Update a variable's value.
        
        Args:
            variable_id: The variable ID
            value: The new value (string, number, or boolean)
            
        Returns:
            Dictionary with operation results
        """
        try:
            # Validate variable_id
            if not isinstance(variable_id, int):
                return {"error": "variable_id must be an integer"}
            
            # Log the update attempt
            self.logger.info(f"Updating variable {variable_id} to value: {value}")
            
            # Perform the update
            result = self.data_provider.update_variable(variable_id, value)
            
            if "error" in result:
                self.logger.error(f"Failed to update variable {variable_id}: {result['error']}")
            else:
                self.logger.info(f"Variable {variable_id} updated successfully. Previous: {result.get('previous')}, Current: {result.get('current')}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Unexpected error updating variable {variable_id}: {e}")
            return {"error": str(e)}