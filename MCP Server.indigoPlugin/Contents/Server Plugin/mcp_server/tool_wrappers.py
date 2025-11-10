"""
Tool wrapper methods for MCP server.

Provides wrapper methods that connect MCP tool calls to their implementations.
Each wrapper handles parameter validation, error handling, and JSON serialization.
"""

from typing import Any, Dict, List, Optional
import logging

from .common.json_encoder import safe_json_dumps
from .common.indigo_device_types import DeviceTypeResolver, IndigoDeviceType, IndigoEntityType


class ToolWrappers:
    """Collection of wrapper methods for MCP tools."""

    def __init__(
        self,
        search_handler,
        get_devices_by_type_handler,
        device_control_handler,
        rgb_control_handler,
        thermostat_control_handler,
        variable_control_handler,
        action_control_handler,
        historical_analysis_handler,
        list_handlers,
        log_query_handler,
        plugin_control_handler,
        data_provider,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize tool wrappers with handler dependencies.

        Args:
            search_handler: Search entities handler
            get_devices_by_type_handler: Get devices by type handler
            device_control_handler: Device control handler
            rgb_control_handler: RGB control handler
            thermostat_control_handler: Thermostat control handler
            variable_control_handler: Variable control handler
            action_control_handler: Action control handler
            historical_analysis_handler: Historical analysis handler
            list_handlers: List handlers instance
            log_query_handler: Log query handler
            plugin_control_handler: Plugin control handler
            data_provider: Data provider for direct entity access
            logger: Optional logger instance
        """
        self.search_handler = search_handler
        self.get_devices_by_type_handler = get_devices_by_type_handler
        self.device_control_handler = device_control_handler
        self.rgb_control_handler = rgb_control_handler
        self.thermostat_control_handler = thermostat_control_handler
        self.variable_control_handler = variable_control_handler
        self.action_control_handler = action_control_handler
        self.historical_analysis_handler = historical_analysis_handler
        self.list_handlers = list_handlers
        self.log_query_handler = log_query_handler
        self.plugin_control_handler = plugin_control_handler
        self.data_provider = data_provider
        self.logger = logger or logging.getLogger(__name__)

    # Tool wrapper methods
    def tool_search_entities(
        self,
        query: str,
        device_types: List[str] = None,
        entity_types: List[str] = None,
        state_filter: Dict = None,
        limit: int = 50,
        offset: int = 0
    ) -> str:
        """Search entities tool implementation with pagination."""
        try:
            # Validate device types
            if device_types:
                resolved_types, invalid_device_types = DeviceTypeResolver.resolve_device_types(device_types)
                if invalid_device_types:
                    # Generate helpful error message with suggestions
                    error_parts = [f"Invalid device types: {invalid_device_types}"]
                    error_parts.append(f"Valid types: {IndigoDeviceType.get_all_types()}")

                    # Add suggestions for each invalid type
                    for invalid_type in invalid_device_types:
                        suggestions = DeviceTypeResolver.get_suggestions_for_invalid_type(invalid_type)
                        if suggestions:
                            error_parts.append(f"Did you mean: {', '.join(suggestions)}")

                    return safe_json_dumps({
                        "error": " | ".join(error_parts),
                        "query": query
                    })

                # Use resolved types for the search
                device_types = resolved_types

            # Validate entity types
            if entity_types:
                invalid_entity_types = [
                    et for et in entity_types
                    if not IndigoEntityType.is_valid_type(et)
                ]
                if invalid_entity_types:
                    return safe_json_dumps({
                        "error": f"Invalid entity types: {invalid_entity_types}",
                        "query": query
                    })

            self.logger.info(
                f"[search_entities]: query: '{query}', "
                f"device_types: {device_types}, "
                f"entity_types: {entity_types}, "
                f"state_filter: {state_filter}, "
                f"limit: {limit}, offset: {offset}"
            )

            results = self.search_handler.search(
                query=query,
                device_types=device_types,
                entity_types=entity_types,
                state_filter=state_filter,
                limit=limit,
                offset=offset
            )
            return safe_json_dumps(results)

        except Exception as e:
            self.logger.error(f"[search_entities]: Error - {e}")
            return safe_json_dumps({"error": str(e), "query": query})

    def tool_get_devices_by_type(self, device_type: str) -> str:
        """Get devices by type tool implementation."""
        try:
            result = self.get_devices_by_type_handler.get_devices(device_type)
            return safe_json_dumps(result)
        except Exception as e:
            self.logger.error(f"Get devices by type error: {e}")
            return safe_json_dumps({"error": str(e), "device_type": device_type})

    def tool_device_turn_on(self, device_id: int) -> str:
        """Turn on device tool implementation."""
        try:
            result = self.device_control_handler.turn_on(device_id)
            return safe_json_dumps(result)
        except Exception as e:
            self.logger.error(f"Device turn on error: {e}")
            return safe_json_dumps({"error": str(e)})

    def tool_device_turn_off(self, device_id: int) -> str:
        """Turn off device tool implementation."""
        try:
            result = self.device_control_handler.turn_off(device_id)
            return safe_json_dumps(result)
        except Exception as e:
            self.logger.error(f"Device turn off error: {e}")
            return safe_json_dumps({"error": str(e)})

    def tool_device_set_brightness(self, device_id: int, brightness: float) -> str:
        """Set device brightness tool implementation."""
        try:
            result = self.device_control_handler.set_brightness(device_id, brightness)
            return safe_json_dumps(result)
        except Exception as e:
            self.logger.error(f"Device set brightness error: {e}")
            return safe_json_dumps({"error": str(e)})

    def tool_device_set_rgb_color(
        self,
        device_id: int,
        red: int,
        green: int,
        blue: int,
        delay: int = 0
    ) -> str:
        """Set RGB color using 0-255 values tool implementation."""
        try:
            result = self.rgb_control_handler.set_rgb_color(device_id, red, green, blue, delay)
            return safe_json_dumps(result)
        except Exception as e:
            self.logger.error(f"RGB color set error: {e}")
            return safe_json_dumps({"error": str(e)})

    def tool_device_set_rgb_percent(
        self,
        device_id: int,
        red_percent: float,
        green_percent: float,
        blue_percent: float,
        delay: int = 0
    ) -> str:
        """Set RGB color using 0-100 percentages tool implementation."""
        try:
            result = self.rgb_control_handler.set_rgb_percent(
                device_id, red_percent, green_percent, blue_percent, delay
            )
            return safe_json_dumps(result)
        except Exception as e:
            self.logger.error(f"RGB percent set error: {e}")
            return safe_json_dumps({"error": str(e)})

    def tool_device_set_hex_color(
        self,
        device_id: int,
        hex_color: str,
        delay: int = 0
    ) -> str:
        """Set RGB color using hex code tool implementation."""
        try:
            result = self.rgb_control_handler.set_hex_color(device_id, hex_color, delay)
            return safe_json_dumps(result)
        except Exception as e:
            self.logger.error(f"Hex color set error: {e}")
            return safe_json_dumps({"error": str(e)})

    def tool_device_set_named_color(
        self,
        device_id: int,
        color_name: str,
        delay: int = 0
    ) -> str:
        """Set RGB color using named color tool implementation."""
        try:
            result = self.rgb_control_handler.set_named_color(device_id, color_name, delay)
            return safe_json_dumps(result)
        except Exception as e:
            self.logger.error(f"Named color set error: {e}")
            return safe_json_dumps({"error": str(e)})

    def tool_device_set_white_levels(
        self,
        device_id: int,
        white_level: Optional[float] = None,
        white_level2: Optional[float] = None,
        white_temperature: Optional[int] = None,
        delay: int = 0
    ) -> str:
        """Set white channel levels tool implementation."""
        try:
            result = self.rgb_control_handler.set_white_levels(
                device_id, white_level, white_level2, white_temperature, delay
            )
            return safe_json_dumps(result)
        except Exception as e:
            self.logger.error(f"White levels set error: {e}")
            return safe_json_dumps({"error": str(e)})

    def tool_thermostat_set_heat_setpoint(self, device_id: int, temperature: float) -> str:
        """Set thermostat heat setpoint tool implementation."""
        try:
            result = self.thermostat_control_handler.set_heat_setpoint(device_id, temperature)
            return safe_json_dumps(result)
        except Exception as e:
            self.logger.error(f"Thermostat heat setpoint error: {e}")
            return safe_json_dumps({"error": str(e)})

    def tool_thermostat_set_cool_setpoint(self, device_id: int, temperature: float) -> str:
        """Set thermostat cool setpoint tool implementation."""
        try:
            result = self.thermostat_control_handler.set_cool_setpoint(device_id, temperature)
            return safe_json_dumps(result)
        except Exception as e:
            self.logger.error(f"Thermostat cool setpoint error: {e}")
            return safe_json_dumps({"error": str(e)})

    def tool_thermostat_set_hvac_mode(self, device_id: int, mode: str) -> str:
        """Set thermostat HVAC mode tool implementation."""
        try:
            result = self.thermostat_control_handler.set_hvac_mode(device_id, mode)
            return safe_json_dumps(result)
        except Exception as e:
            self.logger.error(f"Thermostat HVAC mode error: {e}")
            return safe_json_dumps({"error": str(e)})

    def tool_thermostat_set_fan_mode(self, device_id: int, mode: str) -> str:
        """Set thermostat fan mode tool implementation."""
        try:
            result = self.thermostat_control_handler.set_fan_mode(device_id, mode)
            return safe_json_dumps(result)
        except Exception as e:
            self.logger.error(f"Thermostat fan mode error: {e}")
            return safe_json_dumps({"error": str(e)})

    def tool_variable_update(self, variable_id: int, value: str) -> str:
        """Update variable tool implementation."""
        try:
            result = self.variable_control_handler.update(variable_id, value)
            return safe_json_dumps(result)
        except Exception as e:
            self.logger.error(f"Variable update error: {e}")
            return safe_json_dumps({"error": str(e)})

    def tool_variable_create(
        self,
        name: str,
        value: str = "",
        folder_id: int = 0
    ) -> str:
        """Create variable tool implementation."""
        try:
            result = self.variable_control_handler.create(name, value, folder_id)
            return safe_json_dumps(result)
        except Exception as e:
            self.logger.error(f"Variable create error: {e}")
            return safe_json_dumps({"error": str(e)})

    def tool_action_execute_group(
        self,
        action_group_id: int,
        delay: int = None
    ) -> str:
        """Execute action group tool implementation."""
        try:
            result = self.action_control_handler.execute(action_group_id, delay)
            return safe_json_dumps(result)
        except Exception as e:
            self.logger.error(f"Action execute error: {e}")
            return safe_json_dumps({"error": str(e)})

    def tool_analyze_historical_data(
        self,
        query: str,
        device_names: List[str],
        time_range_days: int = 30
    ) -> str:
        """Analyze historical data tool implementation."""
        try:
            result = self.historical_analysis_handler.analyze_historical_data(
                query, device_names, time_range_days
            )
            return safe_json_dumps(result)
        except Exception as e:
            self.logger.error(f"Historical analysis error: {e}")
            return safe_json_dumps({"error": str(e)})

    def tool_list_devices(
        self,
        state_filter: Dict = None,
        limit: int = 50,
        offset: int = 0
    ) -> str:
        """List devices tool implementation with pagination."""
        try:
            result = self.list_handlers.list_all_devices(
                state_filter=state_filter,
                limit=limit,
                offset=offset
            )
            return safe_json_dumps(result)
        except Exception as e:
            self.logger.error(f"List devices error: {e}")
            return safe_json_dumps({"error": str(e)})

    def tool_list_variables(self, limit: int = 50, offset: int = 0) -> str:
        """List variables tool implementation with pagination."""
        try:
            result = self.list_handlers.list_all_variables(limit=limit, offset=offset)
            return safe_json_dumps(result)
        except Exception as e:
            self.logger.error(f"List variables error: {e}")
            return safe_json_dumps({"error": str(e)})

    def tool_list_action_groups(self, limit: int = 50, offset: int = 0) -> str:
        """List action groups tool implementation with pagination."""
        try:
            result = self.list_handlers.list_all_action_groups(limit=limit, offset=offset)
            return safe_json_dumps(result)
        except Exception as e:
            self.logger.error(f"List action groups error: {e}")
            return safe_json_dumps({"error": str(e)})

    def tool_list_variable_folders(self) -> str:
        """List variable folders tool implementation."""
        try:
            folders = self.list_handlers.list_variable_folders()
            return safe_json_dumps(folders)
        except Exception as e:
            self.logger.error(f"List variable folders error: {e}")
            return safe_json_dumps({"error": str(e)})

    def tool_get_devices_by_state(
        self,
        state_conditions: Dict,
        device_types: List[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> str:
        """Get devices by state tool implementation with pagination."""
        try:
            # Validate device types if provided
            if device_types:
                resolved_types, invalid_types = DeviceTypeResolver.resolve_device_types(device_types)
                if invalid_types:
                    # Generate helpful error message with suggestions
                    error_parts = [f"Invalid device types: {invalid_types}"]
                    error_parts.append(f"Valid types: {IndigoDeviceType.get_all_types()}")

                    # Add suggestions for each invalid type
                    for invalid_type in invalid_types:
                        suggestions = DeviceTypeResolver.get_suggestions_for_invalid_type(invalid_type)
                        if suggestions:
                            error_parts.append(f"Did you mean: {', '.join(suggestions)}")

                    return safe_json_dumps({
                        "error": " | ".join(error_parts)
                    })

                # Use resolved types for the query
                device_types = resolved_types

            result = self.list_handlers.get_devices_by_state(
                state_conditions=state_conditions,
                device_types=device_types,
                limit=limit,
                offset=offset
            )
            return safe_json_dumps(result)
        except Exception as e:
            self.logger.error(f"Get devices by state error: {e}")
            return safe_json_dumps({"error": str(e)})

    def tool_get_device_by_id(self, device_id: int) -> str:
        """Get device by ID tool implementation."""
        try:
            device = self.data_provider.get_device(device_id)
            if device is None:
                return safe_json_dumps({
                    "error": f"Device {device_id} not found"
                })
            return safe_json_dumps(device)
        except Exception as e:
            self.logger.error(f"Get device by ID error: {e}")
            return safe_json_dumps({"error": str(e)})

    def tool_get_variable_by_id(self, variable_id: int) -> str:
        """Get variable by ID tool implementation."""
        try:
            variable = self.data_provider.get_variable(variable_id)
            if variable is None:
                return safe_json_dumps({
                    "error": f"Variable {variable_id} not found"
                })
            return safe_json_dumps(variable)
        except Exception as e:
            self.logger.error(f"Get variable by ID error: {e}")
            return safe_json_dumps({"error": str(e)})

    def tool_get_action_group_by_id(self, action_group_id: int) -> str:
        """Get action group by ID tool implementation."""
        try:
            action = self.data_provider.get_action_group(action_group_id)
            if action is None:
                return safe_json_dumps({
                    "error": f"Action group {action_group_id} not found"
                })
            return safe_json_dumps(action)
        except Exception as e:
            self.logger.error(f"Get action group by ID error: {e}")
            return safe_json_dumps({"error": str(e)})

    def tool_query_event_log(
        self,
        line_count: int = 20,
        show_timestamp: bool = True
    ) -> str:
        """Query event log tool implementation."""
        try:
            result = self.log_query_handler.query(
                line_count=line_count,
                show_timestamp=show_timestamp
            )
            return safe_json_dumps(result)
        except Exception as e:
            self.logger.error(f"Query event log error: {e}")
            return safe_json_dumps({"error": str(e)})

    def tool_list_plugins(self, include_disabled: bool = False) -> str:
        """List plugins tool implementation."""
        try:
            result = self.plugin_control_handler.list_plugins(include_disabled)
            return safe_json_dumps(result)
        except Exception as e:
            self.logger.error(f"List plugins error: {e}")
            return safe_json_dumps({"error": str(e)})

    def tool_get_plugin_by_id(self, plugin_id: str) -> str:
        """Get plugin by ID tool implementation."""
        try:
            result = self.plugin_control_handler.get_plugin_by_id(plugin_id)
            return safe_json_dumps(result)
        except Exception as e:
            self.logger.error(f"Get plugin by ID error: {e}")
            return safe_json_dumps({"error": str(e)})

    def tool_restart_plugin(self, plugin_id: str) -> str:
        """Restart plugin tool implementation."""
        try:
            result = self.plugin_control_handler.restart_plugin(plugin_id)
            return safe_json_dumps(result)
        except Exception as e:
            self.logger.error(f"Restart plugin error: {e}")
            return safe_json_dumps({"error": str(e)})

    def tool_get_plugin_status(self, plugin_id: str) -> str:
        """Get plugin status tool implementation."""
        try:
            result = self.plugin_control_handler.get_plugin_status(plugin_id)
            return safe_json_dumps(result)
        except Exception as e:
            self.logger.error(f"Get plugin status error: {e}")
            return safe_json_dumps({"error": str(e)})

    # Resource wrapper methods
    def resource_list_devices(self) -> str:
        """List all devices resource."""
        try:
            devices = self.list_handlers.list_all_devices()
            return safe_json_dumps(devices)
        except Exception as e:
            self.logger.error(f"Resource list devices error: {e}")
            return safe_json_dumps({"error": str(e)})

    def resource_get_device(self, device_id: str) -> str:
        """Get specific device resource."""
        try:
            device = self.data_provider.get_device(int(device_id))
            if device is None:
                return safe_json_dumps({
                    "error": f"Device {device_id} not found"
                })
            return safe_json_dumps(device)
        except Exception as e:
            self.logger.error(f"Resource get device error: {e}")
            return safe_json_dumps({"error": str(e)})

    def resource_list_variables(self) -> str:
        """List all variables resource."""
        try:
            variables = self.list_handlers.list_all_variables()
            return safe_json_dumps(variables)
        except Exception as e:
            self.logger.error(f"Resource list variables error: {e}")
            return safe_json_dumps({"error": str(e)})

    def resource_get_variable(self, variable_id: str) -> str:
        """Get specific variable resource."""
        try:
            variable = self.data_provider.get_variable(int(variable_id))
            if variable is None:
                return safe_json_dumps({
                    "error": f"Variable {variable_id} not found"
                })
            return safe_json_dumps(variable)
        except Exception as e:
            self.logger.error(f"Resource get variable error: {e}")
            return safe_json_dumps({"error": str(e)})

    def resource_list_actions(self) -> str:
        """List all action groups resource."""
        try:
            actions = self.list_handlers.list_all_action_groups()
            return safe_json_dumps(actions)
        except Exception as e:
            self.logger.error(f"Resource list actions error: {e}")
            return safe_json_dumps({"error": str(e)})

    def resource_get_action(self, action_id: str) -> str:
        """Get specific action group resource."""
        try:
            action = self.data_provider.get_action_group(int(action_id))
            if action is None:
                return safe_json_dumps({
                    "error": f"Action group {action_id} not found"
                })
            return safe_json_dumps(action)
        except Exception as e:
            self.logger.error(f"Resource get action error: {e}")
            return safe_json_dumps({"error": str(e)})
