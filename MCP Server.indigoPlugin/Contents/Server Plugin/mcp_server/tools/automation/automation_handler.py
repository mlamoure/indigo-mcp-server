"""
Automation introspection handlers: list triggers/schedules, explain one
automation element, and reverse-lookup what references an entity.
"""

import logging
from typing import Any, Dict, List, Optional

from ...adapters.data_provider import DataProvider
from ...adapters.indidb import IndiDbStructureStore
from ..base_handler import BaseToolHandler
from .explain_renderer import ExplainRenderer

AUTOMATION_ENTITY_TYPES = ("trigger", "schedule", "action_group")
REFERENCE_ENTITY_TYPES = ("device", "variable", "action_group")

# Which control actions are valid for which entity type. Action groups have
# no enabled flag and no delayed-action queue of their own in the IOM.
CONTROL_ACTIONS = {
    "trigger": {"enable", "disable", "execute", "duplicate", "move_to_folder",
                "remove_delayed_actions", "delete"},
    "schedule": {"enable", "disable", "execute", "duplicate", "move_to_folder",
                 "remove_delayed_actions", "delete"},
    "action_group": {"execute", "duplicate", "move_to_folder", "delete"},
}


class AutomationHandler(BaseToolHandler):
    """Handler for trigger/schedule/action-group introspection tools."""

    def __init__(
        self,
        data_provider: DataProvider,
        structure_store: IndiDbStructureStore,
        logger: Optional[logging.Logger] = None,
        delete_enabled_supplier=None,
        editing_enabled_supplier=None,
    ):
        super().__init__(tool_name="automation", logger=logger)
        self.data_provider = data_provider
        self.structure_store = structure_store
        self.renderer = ExplainRenderer(data_provider, structure_store, logger=logger)
        self.delete_enabled_supplier = delete_enabled_supplier or (lambda: False)
        self.editing_enabled_supplier = editing_enabled_supplier or (lambda: False)

    # ------------------------------------------------------------------
    # list_triggers
    # ------------------------------------------------------------------

    def list_triggers(
        self,
        name_contains: Optional[str] = None,
        enabled_only: bool = False,
        trigger_type: Optional[str] = None,
        folder_id: Optional[int] = None,
        limit: Optional[int] = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        try:
            triggers = self.data_provider.get_all_triggers()

            if name_contains:
                needle = name_contains.lower()
                triggers = [t for t in triggers if needle in (t.get("name") or "").lower()]
            if enabled_only:
                triggers = [t for t in triggers if t.get("enabled")]
            if trigger_type:
                triggers = [t for t in triggers if t.get("type") == trigger_type]
            if folder_id is not None:
                triggers = [t for t in triggers if t.get("folderId") == folder_id]

            for trigger in triggers:
                trigger["watching"] = self._trigger_event_summary(trigger)

            triggers.sort(key=lambda t: (t.get("name") or "").lower())
            page, total_count, has_more = _paginate(triggers, limit, offset)

            self.log_tool_outcome("list_triggers", True, count=len(page))
            return {
                "triggers": page,
                "count": len(page),
                "total_count": total_count,
                "offset": offset,
                "has_more": has_more,
            }
        except Exception as e:
            return self.handle_exception(e, "listing triggers")

    def _trigger_event_summary(self, trigger: Dict[str, Any]) -> str:
        trigger_type = trigger.get("type")
        if trigger_type == "device_state_change":
            device = self._entity_name("device", trigger.get("deviceId"))
            summary = f'device "{device}" state {trigger.get("stateSelector")} {trigger.get("stateChangeType")}'
            if trigger.get("stateValue"):
                summary += f' "{trigger["stateValue"]}"'
            return summary
        if trigger_type == "variable_change":
            variable = self._entity_name("variable", trigger.get("variableId"))
            summary = f'variable "{variable}" {trigger.get("variableChangeType")}'
            if trigger.get("variableValue"):
                summary += f' "{trigger["variableValue"]}"'
            return summary
        if trigger_type == "plugin_event":
            return f'plugin event {trigger.get("pluginTypeId")} from {trigger.get("pluginId")}'
        return (trigger_type or "unknown").replace("_", " ")

    def _entity_name(self, entity_kind: str, entity_id: Any) -> str:
        if not isinstance(entity_id, int):
            return "?"
        name = self.structure_store.lookup_name(entity_kind, entity_id)
        return name if name is not None else str(entity_id)

    # ------------------------------------------------------------------
    # list_schedules
    # ------------------------------------------------------------------

    def list_schedules(
        self,
        name_contains: Optional[str] = None,
        enabled_only: bool = False,
        folder_id: Optional[int] = None,
        sort_by: str = "next_execution",
        limit: Optional[int] = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        try:
            schedules = self.data_provider.get_all_schedules()

            if name_contains:
                needle = name_contains.lower()
                schedules = [s for s in schedules if needle in (s.get("name") or "").lower()]
            if enabled_only:
                schedules = [s for s in schedules if s.get("enabled")]
            if folder_id is not None:
                schedules = [s for s in schedules if s.get("folderId") == folder_id]

            for sched in schedules:
                sched["timing_summary"] = self._schedule_timing_summary(sched)

            if sort_by == "name":
                schedules.sort(key=lambda s: (s.get("name") or "").lower())
            else:  # next_execution; None sorts last
                schedules.sort(
                    key=lambda s: (s.get("next_execution") is None, s.get("next_execution") or "")
                )

            page, total_count, has_more = _paginate(schedules, limit, offset)

            self.log_tool_outcome("list_schedules", True, count=len(page))
            return {
                "schedules": page,
                "count": len(page),
                "total_count": total_count,
                "offset": offset,
                "has_more": has_more,
            }
        except Exception as e:
            return self.handle_exception(e, "listing schedules")

    @staticmethod
    def _schedule_timing_summary(sched: Dict[str, Any]) -> str:
        date_type = sched.get("date_type") or "?"
        time_type = sched.get("time_type") or "?"
        date_part = date_type.replace("_", " ")

        if time_type == "absolute":
            time_part = f'at {sched.get("absolute_time") or "?"}'
        elif time_type in ("sunrise", "sunset"):
            delta = sched.get("sun_delta_seconds") or 0
            if delta:
                sign = "+" if delta > 0 else "-"
                time_part = f"at {time_type} {sign}{abs(delta) // 60}m"
            else:
                time_part = f"at {time_type}"
        elif time_type == "countdown":
            time_part = "on countdown timer"
        else:
            time_part = time_type.replace("_", " ")

        summary = f"{date_part} {time_part}"
        if sched.get("randomize_by_seconds"):
            summary += f' (randomized ±{sched["randomize_by_seconds"] // 60}m)'
        return summary

    # ------------------------------------------------------------------
    # get_automation_details
    # ------------------------------------------------------------------

    def get_details(
        self,
        entity_type: str,
        entity_id: int,
        include_scripts: bool = True,
    ) -> Dict[str, Any]:
        try:
            if entity_type not in AUTOMATION_ENTITY_TYPES:
                return {
                    "error": f"Invalid entity_type: {entity_type!r}. "
                    f"Valid types: {', '.join(AUTOMATION_ENTITY_TYPES)}",
                    "success": False,
                }
            document = self.renderer.render(
                entity_type, int(entity_id), include_scripts=include_scripts
            )
            if document is None:
                return {"error": f"{entity_type} {entity_id} not found"}
            self.log_tool_outcome(
                f"get_automation_details({entity_type} {entity_id})", True
            )
            return document
        except Exception as e:
            return self.handle_exception(e, f"explaining {entity_type} {entity_id}")

    # ------------------------------------------------------------------
    # find_automation_references
    # ------------------------------------------------------------------

    def find_references(
        self,
        entity_type: str,
        entity_id: int,
        include_server_check: bool = True,
    ) -> Dict[str, Any]:
        try:
            if entity_type not in REFERENCE_ENTITY_TYPES:
                return {
                    "error": f"Invalid entity_type: {entity_type!r}. "
                    f"Valid types: {', '.join(REFERENCE_ENTITY_TYPES)}",
                    "success": False,
                }
            entity_id = int(entity_id)

            references = self.structure_store.find_references(entity_type, entity_id)
            for ref in references:
                ref["name"] = self._entity_name(ref["entity_type"], ref["id"])
                ref["source"] = "database_file"
                if "via_action_groups" in ref:
                    ref["via_action_groups"] = [
                        {"id": ag_id, "name": self._entity_name("action_group", ag_id)}
                        for ag_id in ref["via_action_groups"]
                    ]

            notes: List[str] = []
            if include_server_check:
                self._merge_server_dependencies(entity_type, entity_id, references, notes)

            target_name = self._entity_name(entity_type, entity_id)
            self.log_tool_outcome(
                f"find_automation_references({entity_type} '{target_name}')",
                True,
                count=len(references),
            )
            return {
                "target": {"entity_type": entity_type, "id": entity_id, "name": target_name},
                "references": references,
                "count": len(references),
                "notes": notes,
                "structure_source": self.structure_store.freshness(),
            }
        except Exception as e:
            return self.handle_exception(e, f"finding references to {entity_type} {entity_id}")

    # ------------------------------------------------------------------
    # automation_control
    # ------------------------------------------------------------------

    def control(
        self,
        entity_type: str,
        entity_id: int,
        action: str,
        duration_seconds: Optional[int] = None,
        delay_seconds: Optional[int] = None,
        duplicate_name: Optional[str] = None,
        folder_id: Optional[int] = None,
        confirm: bool = False,
    ) -> Dict[str, Any]:
        try:
            if entity_type not in CONTROL_ACTIONS:
                return {
                    "error": f"Invalid entity_type: {entity_type!r}. "
                    f"Valid types: {', '.join(sorted(CONTROL_ACTIONS))}",
                    "success": False,
                }
            valid_actions = CONTROL_ACTIONS[entity_type]
            if action not in valid_actions:
                return {
                    "error": f"Invalid action {action!r} for {entity_type}. "
                    f"Valid actions: {', '.join(sorted(valid_actions))}",
                    "success": False,
                }
            entity_id = int(entity_id)

            if action == "delete":
                if not self.delete_enabled_supplier():
                    return {
                        "error": "Deleting automations via MCP is disabled. Enable "
                        "'Allow AI to delete automations' in the MCP Server plugin "
                        "preferences to permit it.",
                        "success": False,
                    }
                if not confirm:
                    name = self._entity_name(entity_type, entity_id)
                    return {
                        "error": f"Deletion is irreversible. Call again with "
                        f"confirm=true to delete {entity_type} '{name}' ({entity_id}).",
                        "success": False,
                        "requires_confirmation": True,
                    }

            if action == "move_to_folder" and folder_id is None:
                return {"error": "move_to_folder requires folder_id", "success": False}

            name = self._entity_name(entity_type, entity_id)
            command = action
            value = None
            if action in ("enable", "disable"):
                command = "enable"
                value = action == "enable"

            result = self.data_provider.automation_command(
                entity_type,
                entity_id,
                command,
                value=value,
                delay=delay_seconds,
                duration=duration_seconds,
                duplicate_name=duplicate_name,
                folder_id=folder_id,
            )

            if result.get("error"):
                self.error_log(
                    f"{action} {entity_type} '{name}' failed: {result['error']}"
                )
                return result

            result["action"] = action
            result["name"] = name
            summary = f"{entity_type.replace('_', ' ')} '{name}' {action}"
            if action in ("enable", "disable") and duration_seconds:
                summary += f" (auto-reverts in {duration_seconds}s)"
            if action == "duplicate":
                summary += f" → '{result.get('new_name')}' ({result.get('new_id')})"
            if action == "execute" and delay_seconds:
                summary += f" (in {delay_seconds}s)"
            self.activity_log(summary)
            return result
        except Exception as e:
            return self.handle_exception(
                e, f"running {action} on {entity_type} {entity_id}"
            )

    # ------------------------------------------------------------------
    # update_automation (experimental field editing)
    # ------------------------------------------------------------------

    # Fields whose values must reference an existing entity.
    _REFERENCE_FIELDS = {"device_id": "device", "variable_id": "variable"}

    def update(
        self,
        entity_type: str,
        entity_id: int,
        fields: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        try:
            if not self.editing_enabled_supplier():
                return {
                    "error": "Editing automations via MCP is disabled. Enable "
                    "'Allow AI to edit automations (experimental)' in the MCP "
                    "Server plugin preferences to permit it.",
                    "success": False,
                }
            if entity_type not in AUTOMATION_ENTITY_TYPES:
                return {
                    "error": f"Invalid entity_type: {entity_type!r}. "
                    f"Valid types: {', '.join(AUTOMATION_ENTITY_TYPES)}",
                    "success": False,
                }
            if not fields or not isinstance(fields, dict):
                return {"error": "fields must be a non-empty object", "success": False}
            entity_id = int(entity_id)

            # Referenced entities must exist — a typo'd device id would
            # otherwise silently retarget the trigger at nothing.
            for field, kind in self._REFERENCE_FIELDS.items():
                if field in fields:
                    target_id = fields[field]
                    if not isinstance(target_id, int) or (
                        self.structure_store.lookup_name(kind, target_id) is None
                        and self._live_entity_missing(kind, target_id)
                    ):
                        return {
                            "error": f"{field}={target_id!r} does not match an "
                            f"existing {kind}",
                            "success": False,
                        }

            name = self._entity_name(entity_type, entity_id)
            result = self.data_provider.update_automation_fields(
                entity_type, entity_id, fields
            )
            if result.get("error"):
                self.error_log(f"update {entity_type} '{name}' failed: {result['error']}")
                return result

            changed = [
                field
                for field in fields
                if result["before"].get(field) != result["after"].get(field)
            ]
            self.activity_log(
                f"{entity_type.replace('_', ' ')} '{name}' updated: "
                f"{', '.join(changed) if changed else 'no effective change'}"
            )
            result["note"] = (
                "Field editing uses Indigo's replaceOnServer(), which does not "
                "touch the element's action steps or conditions. Verify with "
                "get_automation_details if in doubt."
            )
            return result
        except Exception as e:
            return self.handle_exception(e, f"updating {entity_type} {entity_id}")

    def _live_entity_missing(self, kind: str, entity_id: int) -> bool:
        try:
            if kind == "device":
                return self.data_provider.get_device(entity_id) is None
            if kind == "variable":
                return self.data_provider.get_variable(entity_id) is None
        except Exception:
            pass
        return True

    def _merge_server_dependencies(
        self,
        entity_type: str,
        entity_id: int,
        references: List[Dict[str, Any]],
        notes: List[str],
    ) -> None:
        """Cross-check with the server's own dependency graph; add anything
        the file-based scan missed as 'referenced (server-reported)'."""
        deps = self.data_provider.get_dependencies(entity_type, entity_id)
        if deps.get("error"):
            notes.append(f"Server dependency check unavailable: {deps['error']}")
            return

        seen = {(ref["entity_type"], ref["id"]) for ref in references}
        singular = {
            "triggers": "trigger",
            "schedules": "schedule",
            "action_groups": "action_group",
            "devices": "device",
            "variables": "variable",
            "control_pages": "control_page",
        }
        for plural_key, kind in singular.items():
            for item in deps.get(plural_key) or []:
                key = (kind, item["id"])
                if key in seen:
                    for ref in references:
                        if (ref["entity_type"], ref["id"]) == key:
                            ref["source"] = "database_file+server"
                    continue
                references.append(
                    {
                        "entity_type": kind,
                        "id": item["id"],
                        "name": item.get("name"),
                        "role": "referenced",
                        "source": "server",
                    }
                )


def _paginate(items: List[Any], limit: Optional[int], offset: int):
    total_count = len(items)
    if offset > 0:
        items = items[offset:]
    if limit is not None and limit > 0:
        items = items[:limit]
    has_more = (offset + len(items)) < total_count
    return items, total_count, has_more
