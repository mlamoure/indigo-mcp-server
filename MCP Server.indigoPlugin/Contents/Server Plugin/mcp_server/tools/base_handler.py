"""
Base handler class for MCP server tools with standardized logging and common functionality.
"""

import inspect
import logging
from typing import Optional, Any


class BaseToolHandler:
    """Base class for all MCP tool handlers with standardized logging."""
    
    def __init__(
        self,
        tool_name: str,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize the base tool handler.
        
        Args:
            tool_name: Name of the tool (used for logging)
            logger: Optional logger instance
        """
        self.tool_name = tool_name
        self.logger = logger or logging.getLogger("Plugin")
    
    def info_log(self, message: str) -> None:
        """
        Log an info message with standardized format.
        
        Args:
            message: The message to log
        """
        self.logger.info(f"[{self.tool_name}]: {message}")
    
    def debug_log(self, message: str) -> None:
        """
        Log a debug message with caller information.
        
        Args:
            message: The message to log
        """
        # Get caller information
        frame = inspect.currentframe()
        try:
            # Go up the stack to find the actual caller
            caller_frame = frame.f_back
            if caller_frame:
                filename = caller_frame.f_code.co_filename
                line_number = caller_frame.f_lineno
                function_name = caller_frame.f_code.co_name
                
                # Extract just the file name from the full path
                file_name = filename.split('/')[-1]
                
                caller_info = f"{file_name}:{line_number} in {function_name}()"
                self.logger.debug(f"[{self.tool_name}] {caller_info}: {message}")
            else:
                self.logger.debug(f"[{self.tool_name}]: {message}")
        finally:
            del frame
    
    def warning_log(self, message: str) -> None:
        """
        Log a warning message with standardized format.
        
        Args:
            message: The message to log
        """
        self.logger.warning(f"[{self.tool_name}]: {message}")
    
    def error_log(self, message: str) -> None:
        """
        Log an error message with standardized format.
        
        Args:
            message: The message to log
        """
        self.logger.error(f"[{self.tool_name}]: {message}")
    
    def handle_exception(self, e: Exception, context: str = "") -> dict:
        """
        Handle exceptions with standardized error reporting.
        
        Args:
            e: The exception that occurred
            context: Additional context about when the error occurred
            
        Returns:
            Dictionary with error information
        """
        error_message = f"Error in {self.tool_name}"
        if context:
            error_message += f" ({context})"
        error_message += f": {str(e)}"
        
        self.error_log(error_message)
        
        return {
            "error": str(e),
            "tool": self.tool_name,
            "context": context,
            "success": False
        }
    
    def create_success_response(self, data: Any, message: str = "") -> dict:
        """
        Create a standardized success response.
        
        Args:
            data: The data to include in the response
            message: Optional success message
            
        Returns:
            Dictionary with success response
        """
        response = {
            "success": True,
            "tool": self.tool_name,
            "data": data
        }
        
        if message:
            response["message"] = message
            self.info_log(message)
        
        return response
    
    def validate_required_params(self, params: dict, required_keys: list) -> Optional[dict]:
        """
        Validate that required parameters are present.
        
        Args:
            params: Dictionary of parameters to validate
            required_keys: List of required parameter keys
            
        Returns:
            None if valid, error dictionary if invalid
        """
        missing_keys = [key for key in required_keys if key not in params or params[key] is None]
        
        if missing_keys:
            error_msg = f"Missing required parameters: {', '.join(missing_keys)}"
            self.error_log(error_msg)
            return {
                "error": error_msg,
                "tool": self.tool_name,
                "missing_parameters": missing_keys,
                "success": False
            }
        
        return None