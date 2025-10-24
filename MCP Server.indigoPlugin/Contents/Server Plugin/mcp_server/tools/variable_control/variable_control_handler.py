"""
Variable control handler for MCP server.
"""

import logging
from typing import Dict, Any, Optional, Union

from ...adapters.data_provider import DataProvider
from ..base_handler import BaseToolHandler


class VariableControlHandler(BaseToolHandler):
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
        super().__init__(tool_name="variable_control", logger=logger)
        self.data_provider = data_provider
    
    def update(self, variable_id: int, value: Union[str, int, float, bool]) -> Dict[str, Any]:
        """
        Update a variable's value.

        Args:
            variable_id: The variable ID
            value: The new value (string, number, or boolean)

        Returns:
            Dictionary with operation results
        """
        # Log incoming request
        self.log_incoming_request("update", {"variable_id": variable_id, "value": value})

        try:
            # Validate variable_id
            if not isinstance(variable_id, int):
                error_result = {"error": "variable_id must be an integer", "success": False}
                self.log_tool_outcome("update", False, "Invalid variable_id type")
                return error_result

            # Get variable name for better logging
            variable = self.data_provider.get_variable(variable_id)
            variable_name = variable.get('name', f'ID {variable_id}') if variable else f'ID {variable_id}'

            self.debug_log(f"Attempting to update variable {variable_name} to value: {value}")

            # Perform the update
            result = self.data_provider.update_variable(variable_id, value)

            if "error" in result:
                self.log_tool_outcome("update", False, f"Variable {variable_name}: {result['error']}")
            else:
                variable_name = result.get('variable_name', variable_name)
                previous = result.get('previous', 'unknown')
                current = result.get('current', value)
                details = f"Variable {variable_name}: {previous} -> {current}"
                self.log_tool_outcome("update", True, details)

            return result

        except Exception as e:
            return self.handle_exception(e, f"updating variable ID {variable_id}")

    def create(
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
            Dictionary with operation results
        """
        # Log incoming request
        self.log_incoming_request("create", {
            "name": name,
            "value": value,
            "folder_id": folder_id
        })

        try:
            # Validate name
            if not name or not isinstance(name, str):
                error_result = {"error": "name is required and must be a string", "success": False}
                self.log_tool_outcome("create", False, "Invalid or missing name")
                return error_result

            # Validate folder_id
            if not isinstance(folder_id, int):
                error_result = {"error": "folder_id must be an integer", "success": False}
                self.log_tool_outcome("create", False, "Invalid folder_id type")
                return error_result

            self.debug_log(f"Attempting to create variable '{name}' with value '{value}' in folder {folder_id}")

            # Perform the creation
            result = self.data_provider.create_variable(name, value, folder_id)

            if "error" in result:
                self.log_tool_outcome("create", False, f"Variable '{name}': {result['error']}")
            else:
                variable_id = result.get('variable_id', 'unknown')
                variable_name = result.get('name', name)
                variable_value = result.get('value', value)
                details = f"Variable '{variable_name}' (ID: {variable_id}) created with value: {variable_value}"
                self.log_tool_outcome("create", True, details)

            return result

        except Exception as e:
            return self.handle_exception(e, f"creating variable '{name}'")