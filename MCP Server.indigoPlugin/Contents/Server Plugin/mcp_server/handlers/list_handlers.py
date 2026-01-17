"""
Shared handlers for listing Indigo entities.
Used by both MCP tools and resources for consistent behavior.
"""

import logging
from typing import Dict, List, Any, Optional

from ..adapters.data_provider import DataProvider
from ..common.state_filter import StateFilter
from ..common.indigo_device_types import DeviceClassifier
from ..tools.base_handler import BaseToolHandler


class ListHandlers(BaseToolHandler):
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
        super().__init__(tool_name="list_handlers", logger=logger)
        self.data_provider = data_provider
    
    def list_all_devices(
        self,
        state_filter: Optional[Dict[str, Any]] = None,
        device_types: Optional[List[str]] = None,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Get all devices, optionally filtered by state and/or type, with pagination support.

        Args:
            state_filter: Optional state conditions to filter by
            device_types: Optional list of device types to filter by
            limit: Maximum number of devices to return (default: no limit)
            offset: Number of devices to skip (default: 0)

        Returns:
            Dictionary with devices list, count, and pagination info
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
                self.debug_log(f"Filtered to {len(devices)} devices by state conditions: {state_filter}")

            # Calculate total count before pagination
            total_count = len(devices)

            # Apply pagination
            if offset > 0:
                devices = devices[offset:]

            if limit is not None and limit > 0:
                devices = devices[:limit]

            # Check if there are more results
            has_more = (offset + len(devices)) < total_count

            # Create query info for logging
            query_info = {}
            if state_filter:
                query_info["state_filter"] = state_filter
            if device_types:
                query_info["device_types"] = device_types
            if limit:
                query_info["limit"] = limit
            if offset:
                query_info["offset"] = offset

            self.log_tool_outcome("list_devices", True, count=len(devices), query_info=query_info)

            return {
                "devices": devices,
                "count": len(devices),
                "total_count": total_count,
                "offset": offset,
                "has_more": has_more
            }

        except Exception as e:
            self.error_log(f"Error listing devices: {e}")
            raise
    
    def list_all_variables(
        self,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Get all variables with pagination support.

        Args:
            limit: Maximum number of variables to return (default: no limit)
            offset: Number of variables to skip (default: 0)

        Returns:
            Dictionary with variables list, count, and pagination info
        """
        try:
            variables = self.data_provider.get_all_variables()

            # Calculate total count before pagination
            total_count = len(variables)

            # Apply pagination
            if offset > 0:
                variables = variables[offset:]

            if limit is not None and limit > 0:
                variables = variables[:limit]

            # Check if there are more results
            has_more = (offset + len(variables)) < total_count

            # Create query info for logging
            query_info = {}
            if limit:
                query_info["limit"] = limit
            if offset:
                query_info["offset"] = offset

            self.log_tool_outcome("list_variables", True, count=len(variables), query_info=query_info)

            return {
                "variables": variables,
                "count": len(variables),
                "total_count": total_count,
                "offset": offset,
                "has_more": has_more
            }

        except Exception as e:
            self.error_log(f"Error listing variables: {e}")
            raise
    
    def list_all_action_groups(
        self,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Get all action groups with pagination support.

        Args:
            limit: Maximum number of action groups to return (default: no limit)
            offset: Number of action groups to skip (default: 0)

        Returns:
            Dictionary with action groups list, count, and pagination info
        """
        try:
            actions = self.data_provider.get_all_actions()

            # Calculate total count before pagination
            total_count = len(actions)

            # Apply pagination
            if offset > 0:
                actions = actions[offset:]

            if limit is not None and limit > 0:
                actions = actions[:limit]

            # Check if there are more results
            has_more = (offset + len(actions)) < total_count

            # Create query info for logging
            query_info = {}
            if limit:
                query_info["limit"] = limit
            if offset:
                query_info["offset"] = offset

            self.log_tool_outcome("list_action_groups", True, count=len(actions), query_info=query_info)

            return {
                "action_groups": actions,
                "count": len(actions),
                "total_count": total_count,
                "offset": offset,
                "has_more": has_more
            }

        except Exception as e:
            self.error_log(f"Error listing action groups: {e}")
            raise
    
    def get_devices_by_state(
        self,
        state_conditions: Dict[str, Any],
        device_types: Optional[List[str]] = None,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Get devices matching specific state conditions with pagination support.

        Args:
            state_conditions: State requirements using Indigo state names
            device_types: Optional list of device types to filter
            limit: Maximum number of devices to return (default: no limit)
            offset: Number of devices to skip (default: 0)

        Returns:
            Dictionary with matching devices and summary
        """
        try:
            # Get devices (optionally filtered by type) with pagination
            result = self.list_all_devices(
                state_filter=state_conditions,
                device_types=device_types,
                limit=limit,
                offset=offset
            )

            # Create summary
            summary = f"Found {result['total_count']} devices matching state conditions"
            if device_types:
                summary += f" (types: {', '.join(device_types)})"
            if limit:
                summary += f" (showing {result['count']} starting from {offset})"

            return {
                "devices": result["devices"],
                "count": result["count"],
                "total_count": result["total_count"],
                "offset": result["offset"],
                "has_more": result["has_more"],
                "state_conditions": state_conditions,
                "device_types": device_types,
                "summary": summary
            }

        except Exception as e:
            self.logger.error(f"Error getting devices by state: {e}")
            raise

    def list_variable_folders(self) -> Dict[str, Any]:
        """
        Get all variable folders.

        Returns:
            Dictionary with folder list and count
        """
        try:
            # Get all variable folders
            folders = self.data_provider.get_variable_folders()

            # Create summary
            summary = f"Found {len(folders)} variable folders"

            return {
                "folders": folders,
                "count": len(folders),
                "summary": summary
            }

        except Exception as e:
            self.logger.error(f"Error listing variable folders: {e}")
            raise