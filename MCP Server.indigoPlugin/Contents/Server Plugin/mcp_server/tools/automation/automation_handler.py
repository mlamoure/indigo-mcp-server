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


class AutomationHandler(BaseToolHandler):
    """Handler for trigger/schedule/action-group introspection tools."""

    def __init__(
        self,
        data_provider: DataProvider,
        structure_store: IndiDbStructureStore,
        logger: Optional[logging.Logger] = None,
    ):
        super().__init__(tool_name="automation", logger=logger)
        self.data_provider = data_provider
        self.structure_store = structure_store
        self.renderer = ExplainRenderer(data_provider, structure_store, logger=logger)

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
