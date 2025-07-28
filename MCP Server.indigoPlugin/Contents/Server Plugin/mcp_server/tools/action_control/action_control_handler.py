"""
Action control handler for MCP server.
"""

import logging
from typing import Dict, Any, Optional

from ...adapters.data_provider import DataProvider


class ActionControlHandler:
    """Handler for action group control operations."""
    
    def __init__(
        self,
        data_provider: DataProvider,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize the action control handler.
        
        Args:
            data_provider: Data provider for action operations
            logger: Optional logger instance
        """
        self.data_provider = data_provider
        self.logger = logger or logging.getLogger("Plugin")
    
    def execute(self, action_group_id: int, delay: Optional[int] = None) -> Dict[str, Any]:
        """
        Execute an action group.
        
        Args:
            action_group_id: The action group ID to execute
            delay: Optional delay in seconds before execution
            
        Returns:
            Dictionary with operation results
        """
        try:
            # Validate action_group_id
            if not isinstance(action_group_id, int):
                return {"error": "action_group_id must be an integer", "success": False}
            
            # Validate delay if provided
            if delay is not None:
                if not isinstance(delay, int) or delay < 0:
                    return {"error": "delay must be a non-negative integer", "success": False}
            
            # Log the execution attempt
            if delay:
                self.logger.info(f"Scheduling action group {action_group_id} for execution in {delay} seconds")
            else:
                self.logger.info(f"Executing action group {action_group_id} immediately")
            
            # Execute the action group
            result = self.data_provider.execute_action_group(action_group_id, delay)
            
            if result.get("success"):
                self.logger.info(f"Action group {action_group_id} execution initiated successfully")
            else:
                self.logger.error(f"Failed to execute action group {action_group_id}: {result.get('error')}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Unexpected error executing action group {action_group_id}: {e}")
            return {"error": str(e), "success": False}