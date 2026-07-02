"""
Renders a merged IOM + .indiDb view of a trigger, schedule, or action group.

Merge precedence: the live IOM wins for identity/liveness fields (name,
description, enabled, event spec, next execution); the database file supplies
the structure the IOM cannot see (action steps, condition trees, timing
detail). Every decoded node keeps a `raw` dict and unknown codes render as
"unknown" kinds, so a format change degrades output instead of breaking it.
"""

import logging
from typing import Any, Dict, List, Optional

from ...adapters.data_provider import DataProvider
from ...adapters.indidb import IndiDbStructureStore
from ...adapters.indidb import schema

SCRIPT_TRUNCATE_CHARS = 4000

# Raw-step keys that are hoisted into decoded fields and would only add bulk.
_RAW_STEP_EXCLUDES = {"ScriptSource", "MetaProps", "ObjVers"}


class ExplainRenderer:
    """Builds the normalized 'explain' document for one automation element."""

    def __init__(
        self,
        data_provider: DataProvider,
        structure_store: IndiDbStructureStore,
        logger: Optional[logging.Logger] = None,
    ):
        self.data_provider = data_provider
        self.structure_store = structure_store
        self.logger = logger or logging.getLogger("Plugin")

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def render(
        self, entity_type: str, entity_id: int, include_scripts: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Returns the merged document, or None when the element exists in
        neither the live IOM nor the database file.
        """
        live = self._live_lookup(entity_type, entity_id)
        struct = self.structure_store.get_structure(entity_type, entity_id)
        if live is None and struct is None:
            return None

        names = _NameResolver(self.data_provider, self.structure_store)
        struct = struct or {}
        live = live or {}

        doc: Dict[str, Any] = {
            "id": entity_id,
            "entity_type": entity_type,
            "name": live.get("name") or struct.get("Name"),
            "description": live.get("description") or "",
            "enabled": live.get("enabled", struct.get("Enabled")),
        }
        folder_id = live.get("folderId", struct.get("FolderID"))
        if folder_id:
            doc["folder"] = {"id": folder_id, "name": live.get("folderName")}

        if entity_type == "trigger":
            doc["trigger_event"] = self._render_trigger_event(live, struct, names)
        elif entity_type == "schedule":
            doc["next_execution"] = live.get("next_execution")
            doc["schedule_timing"] = self._render_schedule_timing(live, struct)

        if struct:
            doc["conditions"] = self._render_conditions(struct.get("Condition"), names)
            doc["action_steps"] = self._render_action_steps(
                _extract_steps(entity_type, struct), names, include_scripts
            )

        doc["meta"] = self._render_meta(live, struct)
        return doc

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------

    def _live_lookup(self, entity_type: str, entity_id: int) -> Optional[Dict[str, Any]]:
        if entity_type == "trigger":
            return self.data_provider.get_trigger(entity_id)
        if entity_type == "schedule":
            return self.data_provider.get_schedule(entity_id)
        if entity_type == "action_group":
            return self.data_provider.get_action_group(entity_id)
        return None

    def _render_trigger_event(
        self, live: Dict[str, Any], struct: Dict[str, Any], names: "_NameResolver"
    ) -> Dict[str, Any]:
        kind = live.get("type")
        raw: Dict[str, Any] = {}
        for key in ("Class", "DeviceID", "DeviceStateChange", "DeviceStateSelector",
                    "VarID", "VarChange", "VarValue", "PluginID", "TypeIdPlugin",
                    "TypeLabelPlugin"):
            if key in struct:
                raw[key] = struct[key]
        if kind is None and "Class" in struct:
            kind = schema.lookup(schema.TRIGGER_CLASS_KINDS, struct["Class"], "trigger_class")

        event: Dict[str, Any] = {"kind": kind or "unknown", "raw": raw}

        if "deviceId" in live or struct.get("Class") == 501:
            device_id = live.get("deviceId", struct.get("DeviceID"))
            event["device"] = names.resolve("device", device_id)
            event["state"] = live.get("stateSelector", struct.get("DeviceStateSelector"))
            event["change_type"] = live.get("stateChangeType") or schema.lookup(
                schema.STATE_CHANGE_TYPES, struct.get("DeviceStateChange"), "state_change_code"
            )
            event["value"] = live.get("stateValue") or None
        elif "variableId" in live or struct.get("Class") == 502:
            variable_id = live.get("variableId", struct.get("VarID"))
            event["variable"] = names.resolve("variable", variable_id)
            event["change_type"] = live.get("variableChangeType") or schema.lookup(
                schema.VAR_CHANGE_TYPES, struct.get("VarChange"), "var_change_code"
            )
            event["value"] = live.get("variableValue") or struct.get("VarValue") or None
        elif "pluginId" in live or struct.get("Class") == 598:
            plugin_id = live.get("pluginId", struct.get("PluginID"))
            event["plugin_id"] = plugin_id
            event["event_type_id"] = live.get("pluginTypeId", struct.get("TypeIdPlugin"))
            event["event_label"] = struct.get("TypeLabelPlugin")
            config = live.get("pluginProps")
            if config is None:
                config = _plugin_config_from_meta_props(struct.get("MetaProps"), plugin_id)
            if config:
                event["config"] = config

        return event

    def _render_schedule_timing(
        self, live: Dict[str, Any], struct: Dict[str, Any]
    ) -> Dict[str, Any]:
        raw: Dict[str, Any] = {}
        for key in ("TimeType", "DateType", "RepeatInterval", "Countdown",
                    "RandomizeAmount", "UseEndLimit", "AutoDelete",
                    "DateStartDay", "DateStartMonth", "DateStartYear",
                    "DateEndDay", "DateEndMonth", "DateEndYear"):
            if key in struct:
                raw[key] = struct[key]

        timing = {
            "date_type": live.get("date_type")
            or schema.lookup(schema.DATE_TYPES, struct.get("DateType"), "date_type_code"),
            "time_type": live.get("time_type")
            or schema.lookup(schema.TIME_TYPES, struct.get("TimeType"), "time_type_code"),
            "time": live.get("absolute_time"),
            "sun_delta_seconds": live.get("sun_delta_seconds"),
            "randomize_by_seconds": live.get("randomize_by_seconds"),
            "auto_delete": live.get("auto_delete"),
            "raw": raw,
        }
        if struct.get("Countdown"):
            timing["countdown_seconds"] = struct["Countdown"]
        if struct.get("RepeatInterval") not in (None, 0, 1):
            timing["repeat_interval"] = struct["RepeatInterval"]
        return timing

    def _render_conditions(
        self, condition: Any, names: "_NameResolver"
    ) -> Dict[str, Any]:
        if not isinstance(condition, dict):
            return {"type": "none"}
        container_type = condition.get("Type")
        if container_type == schema.CONDITION_CONTAINER_NONE or "ConditionList" not in condition:
            return {"type": "none"}
        if container_type != schema.CONDITION_CONTAINER_LIST:
            return {"type": "unknown", "raw": condition}

        condition_list = condition.get("ConditionList") or {}
        items = []
        for item in condition_list.get("Conditions") or []:
            if isinstance(item, dict):
                items.append(self._render_condition_item(item, names))
        return {
            "type": "condition_list",
            "logic": schema.lookup(
                schema.CONDITION_LOGIC, condition_list.get("Logic"), "logic_code"
            ),
            "items": items,
        }

    def _render_condition_item(
        self, item: Dict[str, Any], names: "_NameResolver"
    ) -> Dict[str, Any]:
        cond_type = item.get("Type")
        kind = schema.lookup(schema.CONDITION_TYPE_KINDS, cond_type, "condition_type")
        raw = {key: value for key, value in item.items() if key != "ObjVers"}
        rendered: Dict[str, Any] = {"kind": kind, "raw": raw}

        if cond_type == 3:
            rendered["variable"] = names.resolve("variable", item.get("VarID"))
            rendered["comparison"] = schema.lookup(
                schema.CONDITION_COMPARISONS, item.get("VarState"), "comparison_code"
            )
            if item.get("CompareVarToValue", True):
                rendered["value"] = item.get("VarValue")
            else:
                rendered["compare_to_variable"] = names.resolve("variable", item.get("VarID2"))
        elif cond_type == 5:
            rendered["start_time"] = _seconds_to_hms(item.get("StartTimeDate"))
            rendered["end_time"] = _seconds_to_hms(item.get("EndTimeDate"))
            rendered["operator_code"] = item.get("TimeDateCompareOperator")
        elif cond_type == 7:
            rendered["device"] = names.resolve("device", item.get("DevID"))
            rendered["state"] = item.get("DevState")
            rendered["comparison"] = schema.lookup(
                schema.CONDITION_COMPARISONS, item.get("DevComp"), "comparison_code"
            )
            rendered["value"] = item.get("DevValue")

        return rendered

    def _render_action_steps(
        self, steps: List[Any], names: "_NameResolver", include_scripts: bool
    ) -> List[Dict[str, Any]]:
        rendered_steps = []
        for step in steps:
            if not isinstance(step, dict):
                continue
            step_class = step.get("Class")
            if step_class == schema.ACTION_CLASS_NONE:
                continue  # empty placeholder rows carry no information
            rendered_steps.append(
                self._render_step(step, len(rendered_steps), names, include_scripts)
            )
        return rendered_steps

    def _render_step(
        self,
        step: Dict[str, Any],
        index: int,
        names: "_NameResolver",
        include_scripts: bool,
    ) -> Dict[str, Any]:
        step_class = step.get("Class")
        kind = schema.lookup(schema.ACTION_CLASS_KINDS, step_class, "action_class")
        rendered: Dict[str, Any] = {"index": index, "kind": kind}

        if step.get("DelayAction") and step.get("DelayAmount"):
            rendered["delay_seconds"] = step["DelayAmount"]
            if "ReplaceExistingDelayedAction" in step:
                rendered["replace_existing_delay"] = step["ReplaceExistingDelayedAction"]

        if step_class == schema.ACTION_CLASS_DEVICE:
            rendered["device"] = names.resolve("device", step.get("DeviceID"))
            rendered["command"] = schema.lookup(
                schema.DEVICE_ACTION_COMMANDS, step.get("DeviceAction"), "device_action_code"
            )
            if step.get("DeviceActionValue") not in (None, 0):
                rendered["value"] = step["DeviceActionValue"]
        elif step_class == schema.ACTION_CLASS_VARIABLE:
            rendered["variable"] = names.resolve("variable", step.get("VarID"))
            rendered["command"] = schema.lookup(
                schema.VARIABLE_ACTION_COMMANDS, step.get("VarAction"), "variable_action_code"
            )
            rendered["value"] = step.get("VarValue")
        elif step_class == schema.ACTION_CLASS_EXECUTE_ACTION_GROUP:
            rendered["action_group"] = names.resolve("action_group", step.get("ActionGroupID"))
        elif step_class == schema.ACTION_CLASS_EMBEDDED_SCRIPT:
            script = step.get("ScriptSource") or ""
            rendered["language"] = "python"
            rendered["script_length"] = len(script)
            if include_scripts:
                truncated = len(script) > SCRIPT_TRUNCATE_CHARS
                rendered["script_source"] = (
                    script[:SCRIPT_TRUNCATE_CHARS] if truncated else script
                )
                rendered["script_truncated"] = truncated
            else:
                first_line = script.strip().splitlines()[0] if script.strip() else ""
                rendered["script_first_line"] = first_line
        elif step_class == schema.ACTION_CLASS_PLUGIN:
            plugin_id = step.get("PluginID")
            rendered["plugin_id"] = plugin_id
            rendered["action_type_id"] = step.get("TypeIdPlugin")
            rendered["action_label"] = step.get("TypeLabelPlugin")
            config = _plugin_config_from_meta_props(step.get("MetaProps"), plugin_id)
            if config:
                rendered["config"] = config
            if isinstance(step.get("DeviceID"), int) and step["DeviceID"] > 0:
                rendered["device"] = names.resolve("device", step["DeviceID"])

        rendered["raw"] = {
            key: value for key, value in step.items() if key not in _RAW_STEP_EXCLUDES
        }
        return rendered

    def _render_meta(self, live: Dict[str, Any], struct: Dict[str, Any]) -> Dict[str, Any]:
        meta: Dict[str, Any] = {
            "live_available": bool(live),
            "structure_available": bool(struct),
            "structure_source": self.structure_store.freshness(),
        }
        if live and struct:
            meta["structure_stale"] = live.get("name") != struct.get("Name")
        if not struct:
            meta["note"] = (
                "Structure (action steps, conditions) unavailable: the element "
                "is not in the database file yet — it may have been created "
                "moments ago, or the file could not be read."
            )
        elif not live:
            meta["note"] = (
                "Element found only in the database file, not in the live "
                "server — it may have been deleted recently."
            )
        return meta


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


class _NameResolver:
    """Per-request memoized {id, name} resolution.

    The parsed database file supplies names for free; the live provider is
    the fallback so brand-new entities still resolve.
    """

    def __init__(self, data_provider: DataProvider, structure_store: IndiDbStructureStore):
        self.data_provider = data_provider
        self.structure_store = structure_store
        self._cache: Dict[Any, Optional[Dict[str, Any]]] = {}

    def resolve(self, entity_kind: str, entity_id: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(entity_id, int) or entity_id <= 0:
            return None
        key = (entity_kind, entity_id)
        if key in self._cache:
            return self._cache[key]

        name = self.structure_store.lookup_name(entity_kind, entity_id)
        if name is None:
            name = self._live_name(entity_kind, entity_id)

        result: Dict[str, Any] = {"id": entity_id, "name": name}
        if name is None:
            result["note"] = "not found — deleted?"
        self._cache[key] = result
        return result

    def _live_name(self, entity_kind: str, entity_id: int) -> Optional[str]:
        try:
            if entity_kind == "device":
                entity = self.data_provider.get_device(entity_id)
            elif entity_kind == "variable":
                entity = self.data_provider.get_variable(entity_id)
            elif entity_kind == "action_group":
                entity = self.data_provider.get_action(entity_id)
            elif entity_kind == "trigger":
                entity = self.data_provider.get_trigger(entity_id)
            elif entity_kind == "schedule":
                entity = self.data_provider.get_schedule(entity_id)
            else:
                entity = None
        except Exception:
            entity = None
        return entity.get("name") if entity else None


def _extract_steps(entity_type: str, struct: Dict[str, Any]) -> List[Any]:
    """Action groups hold ActionSteps directly; triggers and schedules nest
    them inside an embedded ActionGroup element."""
    if entity_type == "action_group":
        return struct.get("ActionSteps") or []
    embedded = struct.get("ActionGroup") or {}
    return embedded.get("ActionSteps") or []


def _plugin_config_from_meta_props(meta_props: Any, plugin_id: Optional[str]) -> Optional[dict]:
    """MetaProps is {plugin_id: {config...}}; unwrap to the inner dict."""
    if not isinstance(meta_props, dict):
        return None
    if plugin_id and isinstance(meta_props.get(plugin_id), dict):
        return meta_props[plugin_id]
    if len(meta_props) == 1:
        only_value = next(iter(meta_props.values()))
        if isinstance(only_value, dict):
            return only_value
    return meta_props or None


def _seconds_to_hms(value: Any) -> Optional[str]:
    if not isinstance(value, int):
        return None
    hours, remainder = divmod(value % (24 * 3600), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
