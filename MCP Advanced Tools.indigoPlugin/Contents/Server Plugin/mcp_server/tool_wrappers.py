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
from .common.log_style import fail as log_fail


class ToolWrappers:
    """Collection of wrapper methods for MCP tools."""

    def __init__(
        self,
        search_handler,
        automation_handler=None,
        log_search_handler=None,
        subscription_handler=None,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize tool wrappers with handler dependencies.

        Args:
            search_handler: Search entities handler
            automation_handler: Trigger/schedule/action-group introspection handler
            log_search_handler: Event-log query and investigation handler
            subscription_handler: Event subscription handler (webhooks enabled)
            logger: Optional logger instance
        """
        self.search_handler = search_handler
        self.automation_handler = automation_handler
        self.log_search_handler = log_search_handler
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
            log_fail(self.logger, label, e)
            payload: Dict[str, Any] = {"error": str(e), "success": False}
            if _error_extra:
                payload.update(_error_extra)
            return safe_json_dumps(payload)

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
        limit: int = None,
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

        self.logger.debug(
            f"[search_entities]: query: '{query}', "
            f"device_types: {device_types}, "
            f"entity_types: {entity_types}, "
            f"state_filter: {state_filter}, "
            f"limit: {limit}, offset: {offset}"
        )

        return self._call(
            "Search",
            self.search_handler.search,
            query=query,
            device_types=device_types,
            entity_types=entity_types,
            state_filter=state_filter,
            limit=limit,
            offset=offset,
            _error_extra={"query": query},
        )

    def tool_query_event_log(
        self,
        query: str = None,
        regex: bool = False,
        types: List[str] = None,
        start_time: str = None,
        end_time: str = None,
        limit: int = 50,
        offset: int = 0
    ) -> str:
        """Query event log tool implementation (recent tail or filtered search)."""
        return self._call(
            "Read event log",
            self.log_search_handler.query_event_log,
            query=query, regex=regex, types=types,
            start_time=start_time, end_time=end_time,
            limit=limit, offset=offset
        )

    def tool_list_triggers(
        self,
        name_contains: str = None,
        enabled_only: bool = False,
        trigger_type: str = None,
        folder_id: int = None,
        limit: int = 50,
        offset: int = 0
    ) -> str:
        """List triggers tool implementation."""
        return self._call(
            "List triggers",
            self.automation_handler.list_triggers,
            name_contains=name_contains, enabled_only=enabled_only,
            trigger_type=trigger_type, folder_id=folder_id,
            limit=limit, offset=offset
        )

    def tool_list_schedules(
        self,
        name_contains: str = None,
        enabled_only: bool = False,
        folder_id: int = None,
        sort_by: str = "next_execution",
        limit: int = 50,
        offset: int = 0
    ) -> str:
        """List schedules tool implementation."""
        return self._call(
            "List schedules",
            self.automation_handler.list_schedules,
            name_contains=name_contains, enabled_only=enabled_only,
            folder_id=folder_id, sort_by=sort_by, limit=limit, offset=offset
        )

    def tool_get_trigger_details(self, trigger_id: int, include_scripts: bool = True) -> str:
        """Explain a trigger in full (event, conditions, action steps)."""
        return self._call(
            "Explain trigger", self.automation_handler.get_details,
            entity_type="trigger", entity_id=trigger_id, include_scripts=include_scripts
        )

    def tool_get_schedule_details(self, schedule_id: int, include_scripts: bool = True) -> str:
        """Explain a schedule in full (timing, conditions, action steps)."""
        return self._call(
            "Explain schedule", self.automation_handler.get_details,
            entity_type="schedule", entity_id=schedule_id, include_scripts=include_scripts
        )

    def tool_get_action_group_details(self, action_group_id: int, include_scripts: bool = True) -> str:
        """Explain an action group in full (its action steps)."""
        return self._call(
            "Explain action group", self.automation_handler.get_details,
            entity_type="action_group", entity_id=action_group_id, include_scripts=include_scripts
        )

    def tool_find_automation_references(
        self,
        entity_type: str,
        entity_id: int,
        include_server_check: bool = True
    ) -> str:
        """Find automation references tool implementation."""
        return self._call(
            "Find automation references",
            self.automation_handler.find_references,
            entity_type=entity_type, entity_id=entity_id,
            include_server_check=include_server_check
        )

    def tool_investigate_event(
        self,
        device_id: int = None,
        search_text: str = None,
        around_time: str = None,
        occurrence: int = 1,
        lookback_seconds: int = 60,
        lookahead_seconds: int = 5
    ) -> str:
        """Investigate event tool implementation."""
        return self._call(
            "Investigate event",
            self.log_search_handler.investigate_event,
            device_id=device_id, search_text=search_text,
            around_time=around_time, occurrence=occurrence,
            lookback_seconds=lookback_seconds, lookahead_seconds=lookahead_seconds
        )

    def _control(self, entity_type, entity_id, action, duration_seconds,
                 delay_seconds, duplicate_name, folder_id, confirm) -> str:
        return self._call(
            f"Control {entity_type.replace('_', ' ')}",
            self.automation_handler.control,
            entity_type=entity_type, entity_id=entity_id, action=action,
            duration_seconds=duration_seconds, delay_seconds=delay_seconds,
            duplicate_name=duplicate_name, folder_id=folder_id, confirm=confirm
        )

    def tool_control_trigger(
        self, trigger_id: int, action: str, duration_seconds: int = None,
        delay_seconds: int = None, duplicate_name: str = None,
        folder_id: int = None, confirm: bool = False
    ) -> str:
        """Trigger lifecycle control (enable/disable/duplicate/move/delete)."""
        return self._control("trigger", trigger_id, action, duration_seconds,
                             delay_seconds, duplicate_name, folder_id, confirm)

    def tool_control_schedule(
        self, schedule_id: int, action: str, duration_seconds: int = None,
        delay_seconds: int = None, duplicate_name: str = None,
        folder_id: int = None, confirm: bool = False
    ) -> str:
        """Schedule lifecycle control (enable/disable/duplicate/move/delete)."""
        return self._control("schedule", schedule_id, action, duration_seconds,
                             delay_seconds, duplicate_name, folder_id, confirm)

    def tool_control_action_group(
        self, action_group_id: int, action: str,
        duplicate_name: str = None, folder_id: int = None, confirm: bool = False
    ) -> str:
        """Action-group lifecycle control (duplicate/move/delete)."""
        return self._control("action_group", action_group_id, action, None,
                             None, duplicate_name, folder_id, confirm)

    def tool_update_trigger(self, trigger_id: int, fields: Dict = None) -> str:
        """Edit a trigger's name/description and event settings."""
        return self._call(
            "Update trigger", self.automation_handler.update,
            entity_type="trigger", entity_id=trigger_id, fields=fields
        )

    def tool_update_schedule(self, schedule_id: int, fields: Dict = None) -> str:
        """Edit a schedule's name/description."""
        return self._call(
            "Update schedule", self.automation_handler.update,
            entity_type="schedule", entity_id=schedule_id, fields=fields
        )

    def tool_update_action_group(self, action_group_id: int, fields: Dict = None) -> str:
        """Edit an action group's name/description."""
        return self._call(
            "Update action group", self.automation_handler.update,
            entity_type="action_group", entity_id=action_group_id, fields=fields
        )

    # Event subscription wrapper methods
    def tool_create_event_subscription(self, **kwargs) -> str:
        """Create event subscription tool implementation."""
        return self._call(
            "Create event subscription",
            self.subscription_handler.create_subscription, **kwargs
        )

    def tool_list_event_subscriptions(self, subscription_id: str = None) -> str:
        """List event subscriptions tool implementation."""
        return self._call(
            "List event subscriptions",
            self.subscription_handler.list_subscriptions,
            subscription_id=subscription_id
        )

    def tool_delete_event_subscription(self, subscription_id: str) -> str:
        """Delete event subscription tool implementation."""
        return self._call(
            "Delete event subscription",
            self.subscription_handler.delete_subscription,
            subscription_id=subscription_id
        )
