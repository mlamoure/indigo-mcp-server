"""
Base handler class for MCP server tools with standardized logging and common functionality.
"""

import inspect
import logging
from typing import Optional, Any

from ..common.log_style import FAIL, fail as log_fail, activity as log_activity


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
        Log a debug message with standardized format.

        Args:
            message: The message to log
        """
        self.logger.debug(f"[{self.tool_name}]: {message}")
    
    def warning_log(self, message: str) -> None:
        """
        Log a warning message with standardized format.
        
        Args:
            message: The message to log
        """
        self.logger.warning(f"[{self.tool_name}]: {message}")
    
    def error_log(self, message: str) -> None:
        """
        Log one user-facing error line (❌ prefix added if absent).

        Args:
            message: The message to log
        """
        if not message.startswith(FAIL):
            message = f"{FAIL} {message}"
        self.logger.error(message)

    def activity_log(self, message: str, write: bool = True) -> None:
        """
        Log MCP client activity (🔧 prefix).

        Writes (state changes) always log at INFO; reads log at DEBUG unless
        the "Log AI read activity" pref is enabled.

        Args:
            message: The message to log (no emoji; it's added here)
            write: Whether this activity changed state
        """
        log_activity(self.logger, message, write=write)
    
    def handle_exception(self, e: Exception, context: str = "") -> dict:
        """
        Handle exceptions with standardized error reporting.
        
        Args:
            e: The exception that occurred
            context: Additional context about when the error occurred
            
        Returns:
            Dictionary with error information
        """
        action = context.strip().capitalize() if context else self.tool_name
        log_fail(self.logger, action, e)

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

    def device_label(self, device_id) -> str:
        """
        Best-effort display name for a device, for user-facing log lines.

        Returns the device's name when the handler has a data provider and
        the device exists; otherwise 'device {id}'.
        """
        provider = getattr(self, "data_provider", None)
        device = None
        if provider is not None:
            try:
                device = provider.get_device(device_id)
            except Exception:
                device = None
        if device and device.get("name"):
            return device["name"]
        return f"device {device_id}"

    def validate_device_id(self, device_id) -> Optional[dict]:
        """
        Validate a device id parameter.

        Args:
            device_id: The value to validate

        Returns:
            None if valid, error dictionary if invalid
        """
        if not isinstance(device_id, int) or isinstance(device_id, bool) or device_id <= 0:
            error_msg = f"Invalid device_id: {device_id!r}. Must be a positive integer."
            self.error_log(error_msg)
            return {"error": error_msg, "success": False}
        return None

    def log_incoming_request(self, operation: str, params: dict = None) -> None:
        """
        Log an incoming tool request (concise).

        Args:
            operation: The operation being performed
            params: Optional parameters for the request (not logged for brevity)
        """
        # Concise logging - parameters will be shown in outcome if needed
        pass
    
    def log_tool_outcome(self, operation: str, success: bool, details: str = "", count: int = None, query_info: dict = None) -> None:
        """
        Log the outcome of a tool operation.

        Successful read-only outcomes go through log_style.activity() as
        reads (DEBUG unless the "Log AI read activity" pref is on); failures
        log one ERROR line.

        Args:
            operation: The operation that was performed
            success: Whether the operation succeeded
            details: Optional additional details about the outcome
            count: Optional count of items returned/affected
            query_info: Optional dictionary with query context (filters, types, etc.)
        """
        message = operation
        if count is not None:
            message += f" → {count} item{'s' if count != 1 else ''}"

        if query_info:
            query_details = self._format_query_info(query_info)
            if query_details:
                message += f" ({query_details})"

        if details:
            message += f" - {details}"

        if success:
            log_activity(self.logger, message, write=False)
        else:
            self.error_log(f"{operation} failed" + (f" - {details}" if details else ""))

    def _format_query_info(self, query_info: dict) -> str:
        """
        Format query information for logging.

        Args:
            query_info: Dictionary containing query context

        Returns:
            Formatted string with query details
        """
        if not query_info:
            return ""

        parts = []

        if "state_filter" in query_info and query_info["state_filter"]:
            state_filter = query_info["state_filter"]
            if isinstance(state_filter, dict):
                state_parts = [f"{key}={value}" for key, value in state_filter.items()]
                if state_parts:
                    parts.append(f"states: {', '.join(state_parts)}")

        if "device_types" in query_info and query_info["device_types"]:
            parts.append(f"types: {', '.join(query_info['device_types'])}")

        if "search_query" in query_info and query_info["search_query"]:
            parts.append(f"query: '{query_info['search_query']}'")

        return ", ".join(parts)