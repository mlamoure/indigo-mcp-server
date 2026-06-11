"""
Tool wrapper methods for MCP server.

Provides wrapper methods that connect MCP tool calls to their implementations.
Each wrapper keeps its explicit name and signature — mcp_handler binds them by
name, and a wrong keyword argument must raise TypeError at the call site so the
dispatcher can return an MCP "Tool Execution Error" (isError) result. Execution,
JSON serialization, and error shaping all funnel through _call().
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
        subscription_handler=None,
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
        self.subscription_handler = subscription_handler
        self.logger = logger or logging.getLogger(__name__)

    ########################################
    # Shared execution / error shaping
    ########################################

    def _call(
        self,
        label: str,
        fn,
        *args,
        _error_extra: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> str:
        """
        Execute a handler call and serialize the result.

        Single choke point for the wrapper layer: handler exceptions are
        logged once here and returned as an error payload instead of raised.
        Argument-binding errors (wrong kwarg on the wrapper itself) happen
        before _call is entered, so they still raise TypeError to the
        dispatcher as the MCP isError path requires.
        """
        try:
            return safe_json_dumps(fn(*args, **kwargs))
        except Exception as e:
            self.logger.error(f"[{label}]: Error - {e}")
            payload: Dict[str, Any] = {"error": str(e), "success": False}
            if _error_extra:
                payload.update(_error_extra)
            return safe_json_dumps(payload)

    def _get_by_id(self, label: str, fetch, entity_id, not_found: str) -> str:
        """
        Fetch an entity by id, mapping a None result to a not-found error.

        Coercion happens inside the call so a non-numeric id (resources pass
        strings) becomes an error payload rather than an exception.
        """
        def run():
            entity = fetch(int(entity_id))
            if entity is None:
                return {"error": not_found}
            return entity
        return self._call(label, run)

    @staticmethod
    def _validate_device_types(device_types: List[str]) -> tuple:
        """
        Resolve device type aliases, building a helpful error message for
        invalid ones (with suggestions).

        Returns:
            (resolved_types, error_message) — error_message is None when valid.
        """
        resolved_types, invalid_types = DeviceTypeResolver.resolve_device_types(device_types)
        if not invalid_types:
            return resolved_types, None

        error_parts = [f"Invalid device types: {invalid_types}"]
        error_parts.append(f"Valid types: {IndigoDeviceType.get_all_types()}")
        for invalid_type in invalid_types:
            suggestions = DeviceTypeResolver.get_suggestions_for_invalid_type(invalid_type)
            if suggestions:
                error_parts.append(f"Did you mean: {', '.join(suggestions)}")
        return None, " | ".join(error_parts)

    ########################################
    # Tool wrapper methods
    ########################################

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
        if device_types:
            device_types, error = self._validate_device_types(device_types)
            if error:
                return safe_json_dumps({"error": error, "query": query})

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

        return self._call(
            "search_entities",
            self.search_handler.search,
            query=query,
            device_types=device_types,
            entity_types=entity_types,
            state_filter=state_filter,
            limit=limit,
            offset=offset,
            _error_extra={"query": query},
        )

    def tool_get_devices_by_type(self, device_type: str, limit: int = 50, offset: int = 0) -> str:
        """Get devices by type tool implementation with pagination."""
        return self._call(
            "get_devices_by_type",
            self.get_devices_by_type_handler.get_devices,
            device_type, limit=limit, offset=offset,
            _error_extra={"device_type": device_type},
        )

    def tool_device_turn_on(self, device_id: int) -> str:
        """Turn on device tool implementation."""
        return self._call("device_turn_on", self.device_control_handler.turn_on, device_id)

    def tool_device_turn_off(self, device_id: int) -> str:
        """Turn off device tool implementation."""
        return self._call("device_turn_off", self.device_control_handler.turn_off, device_id)

    def tool_device_set_brightness(self, device_id: int, brightness: float) -> str:
        """Set device brightness tool implementation."""
        return self._call(
            "device_set_brightness",
            self.device_control_handler.set_brightness, device_id, brightness
        )

    def tool_device_set_rgb_color(
        self,
        device_id: int,
        red: int,
        green: int,
        blue: int,
        delay: int = 0
    ) -> str:
        """Set RGB color using 0-255 values tool implementation."""
        return self._call(
            "device_set_rgb_color",
            self.rgb_control_handler.set_rgb_color, device_id, red, green, blue, delay
        )

    def tool_device_set_rgb_percent(
        self,
        device_id: int,
        red_percent: float,
        green_percent: float,
        blue_percent: float,
        delay: int = 0
    ) -> str:
        """Set RGB color using 0-100 percentages tool implementation."""
        return self._call(
            "device_set_rgb_percent",
            self.rgb_control_handler.set_rgb_percent,
            device_id, red_percent, green_percent, blue_percent, delay
        )

    def tool_device_set_hex_color(
        self,
        device_id: int,
        hex_color: str,
        delay: int = 0
    ) -> str:
        """Set RGB color using hex code tool implementation."""
        return self._call(
            "device_set_hex_color",
            self.rgb_control_handler.set_hex_color, device_id, hex_color, delay
        )

    def tool_device_set_named_color(
        self,
        device_id: int,
        color_name: str,
        delay: int = 0
    ) -> str:
        """Set RGB color using named color tool implementation."""
        return self._call(
            "device_set_named_color",
            self.rgb_control_handler.set_named_color, device_id, color_name, delay
        )

    def tool_device_set_white_levels(
        self,
        device_id: int,
        white_level: Optional[float] = None,
        white_level2: Optional[float] = None,
        white_temperature: Optional[int] = None,
        delay: int = 0
    ) -> str:
        """Set white channel levels tool implementation."""
        return self._call(
            "device_set_white_levels",
            self.rgb_control_handler.set_white_levels,
            device_id, white_level, white_level2, white_temperature, delay
        )

    def tool_thermostat_set_heat_setpoint(self, device_id: int, temperature: float) -> str:
        """Set thermostat heat setpoint tool implementation."""
        return self._call(
            "thermostat_set_heat_setpoint",
            self.thermostat_control_handler.set_heat_setpoint, device_id, temperature
        )

    def tool_thermostat_set_cool_setpoint(self, device_id: int, temperature: float) -> str:
        """Set thermostat cool setpoint tool implementation."""
        return self._call(
            "thermostat_set_cool_setpoint",
            self.thermostat_control_handler.set_cool_setpoint, device_id, temperature
        )

    def tool_thermostat_set_hvac_mode(self, device_id: int, mode: str) -> str:
        """Set thermostat HVAC mode tool implementation."""
        return self._call(
            "thermostat_set_hvac_mode",
            self.thermostat_control_handler.set_hvac_mode, device_id, mode
        )

    def tool_thermostat_set_fan_mode(self, device_id: int, mode: str) -> str:
        """Set thermostat fan mode tool implementation."""
        return self._call(
            "thermostat_set_fan_mode",
            self.thermostat_control_handler.set_fan_mode, device_id, mode
        )

    def tool_variable_update(self, variable_id: int, value: str) -> str:
        """Update variable tool implementation."""
        return self._call(
            "variable_update", self.variable_control_handler.update, variable_id, value
        )

    def tool_variable_create(
        self,
        name: str,
        value: str = "",
        folder_id: int = 0
    ) -> str:
        """Create variable tool implementation."""
        return self._call(
            "variable_create", self.variable_control_handler.create, name, value, folder_id
        )

    def tool_action_execute_group(
        self,
        action_group_id: int,
        delay: int = None
    ) -> str:
        """Execute action group tool implementation."""
        return self._call(
            "action_execute_group", self.action_control_handler.execute, action_group_id, delay
        )

    def tool_analyze_historical_data(
        self,
        query: str,
        device_names: List[str],
        time_range_days: int = 30
    ) -> str:
        """Analyze historical data tool implementation."""
        return self._call(
            "analyze_historical_data",
            self.historical_analysis_handler.analyze_historical_data,
            query, device_names, time_range_days
        )

    def tool_list_devices(
        self,
        state_filter: Dict = None,
        limit: int = 50,
        offset: int = 0
    ) -> str:
        """List devices tool implementation with pagination."""
        return self._call(
            "list_devices",
            self.list_handlers.list_all_devices,
            state_filter=state_filter, limit=limit, offset=offset
        )

    def tool_list_variables(self, limit: int = 50, offset: int = 0) -> str:
        """List variables tool implementation with pagination."""
        return self._call(
            "list_variables",
            self.list_handlers.list_all_variables, limit=limit, offset=offset
        )

    def tool_list_action_groups(self, limit: int = 50, offset: int = 0) -> str:
        """List action groups tool implementation with pagination."""
        return self._call(
            "list_action_groups",
            self.list_handlers.list_all_action_groups, limit=limit, offset=offset
        )

    def tool_list_variable_folders(self) -> str:
        """List variable folders tool implementation."""
        return self._call("list_variable_folders", self.list_handlers.list_variable_folders)

    def tool_get_devices_by_state(
        self,
        state_conditions: Dict,
        device_types: List[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> str:
        """Get devices by state tool implementation with pagination."""
        if device_types:
            device_types, error = self._validate_device_types(device_types)
            if error:
                return safe_json_dumps({"error": error})

        return self._call(
            "get_devices_by_state",
            self.list_handlers.get_devices_by_state,
            state_conditions=state_conditions,
            device_types=device_types,
            limit=limit,
            offset=offset,
        )

    def tool_get_device_by_id(self, device_id: int) -> str:
        """Get device by ID tool implementation."""
        return self._get_by_id(
            "get_device_by_id", self.data_provider.get_device,
            device_id, f"Device {device_id} not found"
        )

    def tool_get_variable_by_id(self, variable_id: int) -> str:
        """Get variable by ID tool implementation."""
        return self._get_by_id(
            "get_variable_by_id", self.data_provider.get_variable,
            variable_id, f"Variable {variable_id} not found"
        )

    def tool_get_action_group_by_id(self, action_group_id: int) -> str:
        """Get action group by ID tool implementation."""
        return self._get_by_id(
            "get_action_group_by_id", self.data_provider.get_action_group,
            action_group_id, f"Action group {action_group_id} not found"
        )

    def tool_query_event_log(
        self,
        line_count: int = 20,
        show_timestamp: bool = True
    ) -> str:
        """Query event log tool implementation."""
        return self._call(
            "query_event_log",
            self.log_query_handler.query,
            line_count=line_count, show_timestamp=show_timestamp
        )

    def tool_list_plugins(self, include_disabled: bool = False) -> str:
        """List plugins tool implementation."""
        return self._call(
            "list_plugins", self.plugin_control_handler.list_plugins, include_disabled
        )

    def tool_get_plugin_by_id(self, plugin_id: str) -> str:
        """Get plugin by ID tool implementation."""
        return self._call(
            "get_plugin_by_id", self.plugin_control_handler.get_plugin_by_id, plugin_id
        )

    def tool_restart_plugin(self, plugin_id: str) -> str:
        """Restart plugin tool implementation."""
        return self._call(
            "restart_plugin", self.plugin_control_handler.restart_plugin, plugin_id
        )

    def tool_get_plugin_status(self, plugin_id: str) -> str:
        """Get plugin status tool implementation."""
        return self._call(
            "get_plugin_status", self.plugin_control_handler.get_plugin_status, plugin_id
        )

    # Event subscription wrapper methods
    def tool_create_event_subscription(self, **kwargs) -> str:
        """Create event subscription tool implementation."""
        return self._call(
            "create_event_subscription",
            self.subscription_handler.create_subscription, **kwargs
        )

    def tool_list_event_subscriptions(self, subscription_id: str = None) -> str:
        """List event subscriptions tool implementation."""
        return self._call(
            "list_event_subscriptions",
            self.subscription_handler.list_subscriptions,
            subscription_id=subscription_id
        )

    def tool_delete_event_subscription(self, subscription_id: str) -> str:
        """Delete event subscription tool implementation."""
        return self._call(
            "delete_event_subscription",
            self.subscription_handler.delete_subscription,
            subscription_id=subscription_id
        )

    # Resource wrapper methods
    def resource_list_devices(self) -> str:
        """List all devices resource."""
        return self._call("resource_list_devices", self.list_handlers.list_all_devices)

    def resource_get_device(self, device_id: str) -> str:
        """Get specific device resource."""
        return self._get_by_id(
            "resource_get_device", self.data_provider.get_device,
            device_id, f"Device {device_id} not found"
        )

    def resource_list_variables(self) -> str:
        """List all variables resource."""
        return self._call("resource_list_variables", self.list_handlers.list_all_variables)

    def resource_get_variable(self, variable_id: str) -> str:
        """Get specific variable resource."""
        return self._get_by_id(
            "resource_get_variable", self.data_provider.get_variable,
            variable_id, f"Variable {variable_id} not found"
        )

    def resource_list_actions(self) -> str:
        """List all action groups resource."""
        return self._call("resource_list_actions", self.list_handlers.list_all_action_groups)

    def resource_get_action(self, action_id: str) -> str:
        """Get specific action group resource."""
        return self._get_by_id(
            "resource_get_action", self.data_provider.get_action_group,
            action_id, f"Action group {action_id} not found"
        )
