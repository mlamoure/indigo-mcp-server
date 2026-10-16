"""
Reverse-reference index over a ParsedDb.

Answers "which triggers/schedules/action groups reference entity X, and in
what role?" — the structural half of both `find_automation_references` and
the investigation tool's cause ranking.

Roles:
- watches:          a trigger fires on this device/variable changing
- condition_reads:  a condition compares this device/variable, or the entity's
  id or name appears in a scripted condition's Python source (heuristic)
- acts_on:          an action step commands this device
- sets:             an action step writes this variable
- executes:         an action step runs this action group
- script_reference: this entity's id or name appears inside an embedded
  Python action script (heuristic — text match)
- plugin_config_reference: this entity's id appears inside a plugin action's
  or plugin trigger's config props (heuristic — id-shaped value match)
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from . import schema

# Maximum depth when following action-group → action-group execution chains.
MAX_CHAIN_DEPTH = 5

# Entity-id-shaped runs in script text: 6-10 digits not embedded in an
# identifier, float, or longer number (\w includes digits, so the lookarounds
# reject var1234567, 1.2345678, and 11+-digit runs).
_SCRIPT_ID_RE = re.compile(r"(?<![\w.])(\d{6,10})(?![\w.])")

# Simple single-line string literals (no escapes) — enough to catch the
# common indigo.devices["Name"] / indigo.variables['name'] lookup patterns.
_SCRIPT_STRING_RE = re.compile(r"'([^'\n\\]+)'|\"([^\"\n\\]+)\"")

# Very short literals ("on", "up") collide with ordinary strings too easily.
_MIN_NAME_MATCH_LEN = 3

# (entity_kind, entity_id) — entity_kind is "device" | "variable" | "action_group"
TargetKey = Tuple[str, int]


@dataclass
class Reference:
    """One container referencing one target entity."""

    container_kind: str  # "trigger" | "schedule" | "action_group"
    container_id: int
    role: str
    detail: str = ""
    confidence: str = "exact"  # "exact" | "heuristic"

    def as_dict(self) -> Dict[str, Any]:
        result = {
            "entity_type": self.container_kind,
            "id": self.container_id,
            "role": self.role,
        }
        if self.detail:
            result["detail"] = self.detail
        if self.confidence != "exact":
            result["confidence"] = self.confidence
        return result


@dataclass
class ReverseIndex:
    """Direct references plus the AG→AG execution graph for chain expansion."""

    direct: Dict[TargetKey, List[Reference]] = field(default_factory=dict)
    # action_group_id -> containers with an execute step for it
    exec_parents: Dict[int, List[Tuple[str, int]]] = field(default_factory=dict)

    def add(self, target: TargetKey, ref: Reference) -> None:
        self.direct.setdefault(target, []).append(ref)

    def references_to(self, entity_kind: str, entity_id: int) -> List[Dict[str, Any]]:
        """
        All references to (entity_kind, entity_id), including containers that
        reach it transitively through action-group execution chains.
        """
        results = [ref.as_dict() for ref in self.direct.get((entity_kind, entity_id), [])]

        # Chain expansion: if action group A references the target, anything
        # that executes A (directly or through more AGs) also affects it.
        for ref in self.direct.get((entity_kind, entity_id), []):
            if ref.container_kind != "action_group":
                continue
            for parent_kind, parent_id, chain in self._walk_exec_parents(ref.container_id):
                results.append(
                    {
                        "entity_type": parent_kind,
                        "id": parent_id,
                        "role": ref.role,
                        "detail": ref.detail,
                        "via_action_groups": chain,
                        "confidence": ref.confidence,
                    }
                )
        return results

    def _walk_exec_parents(
        self, action_group_id: int
    ) -> List[Tuple[str, int, List[int]]]:
        """
        Containers that (transitively) execute `action_group_id`.

        Returns (container_kind, container_id, chain) where chain lists the
        intermediate action-group ids ending at `action_group_id`. Cycle-safe
        and bounded at MAX_CHAIN_DEPTH.
        """
        found: List[Tuple[str, int, List[int]]] = []
        seen: Set[Tuple[str, int]] = set()
        frontier: List[Tuple[int, List[int]]] = [(action_group_id, [action_group_id])]
        depth = 0

        while frontier and depth < MAX_CHAIN_DEPTH:
            next_frontier: List[Tuple[int, List[int]]] = []
            for ag_id, chain in frontier:
                for parent_kind, parent_id in self.exec_parents.get(ag_id, []):
                    key = (parent_kind, parent_id)
                    if key in seen:
                        continue
                    seen.add(key)
                    found.append((parent_kind, parent_id, chain))
                    if parent_kind == "action_group":
                        next_frontier.append((parent_id, [parent_id] + chain))
            frontier = next_frontier
            depth += 1

        return found


def build_reverse_index(parsed) -> ReverseIndex:
    """Build the index in one pass over a ParsedDb."""
    index = ReverseIndex()
    known_ids = _known_entity_ids(parsed)
    known_names = _known_entity_names(parsed)

    for trigger_id, trigger in parsed.triggers.items():
        _index_trigger_event(index, trigger_id, trigger)
        _index_container(index, "trigger", trigger_id, trigger, known_ids, known_names)

    for schedule_id, sched in parsed.schedules.items():
        _index_container(index, "schedule", schedule_id, sched, known_ids, known_names)

    for ag_id, action_group in parsed.action_groups.items():
        steps = action_group.get("ActionSteps") or []
        _index_action_steps(index, "action_group", ag_id, steps, known_ids, known_names)

    return index


def _known_entity_ids(parsed) -> Dict[int, str]:
    """id -> entity kind, for the plugin-config heuristic."""
    known: Dict[int, str] = {}
    for dev_id in parsed.device_names:
        known[dev_id] = "device"
    for var_id in parsed.variable_names:
        known[var_id] = "variable"
    for ag_id in parsed.action_groups:
        known[ag_id] = "action_group"
    return known


def _known_entity_names(parsed) -> Dict[str, List[TargetKey]]:
    """Exact entity name -> [(kind, id), ...] for the script-text heuristic.

    Same-name collisions (a device and a variable both named "Garage") keep
    every match — each ref is already flagged heuristic.
    """
    known: Dict[str, List[TargetKey]] = {}
    for dev_id, name in parsed.device_names.items():
        known.setdefault(name, []).append(("device", dev_id))
    for var_id, name in parsed.variable_names.items():
        known.setdefault(name, []).append(("variable", var_id))
    for ag_id, action_group in parsed.action_groups.items():
        name = action_group.get("Name")
        if isinstance(name, str) and name:
            known.setdefault(name, []).append(("action_group", ag_id))
    return known


def _index_trigger_event(index: ReverseIndex, trigger_id: int, trigger: dict) -> None:
    """The entity a trigger watches (its event source)."""
    trigger_class = trigger.get("Class")
    if trigger_class == 501 and isinstance(trigger.get("DeviceID"), int):
        state = trigger.get("DeviceStateSelector") or ""
        index.add(
            ("device", trigger["DeviceID"]),
            Reference("trigger", trigger_id, "watches", detail=f"state {state}".strip()),
        )
    elif trigger_class == 502 and isinstance(trigger.get("VarID"), int):
        index.add(
            ("variable", trigger["VarID"]),
            Reference("trigger", trigger_id, "watches"),
        )


def _index_container(
    index: ReverseIndex,
    container_kind: str,
    container_id: int,
    container: dict,
    known_ids: Dict[int, str],
    known_names: Dict[str, List[TargetKey]],
) -> None:
    """Conditions, action steps, and plugin props of a trigger/schedule."""
    _index_conditions(
        index, container_kind, container_id, container.get("Condition"),
        known_ids, known_names,
    )

    embedded = container.get("ActionGroup") or {}
    steps = embedded.get("ActionSteps") or []
    _index_action_steps(index, container_kind, container_id, steps, known_ids, known_names)

    meta_props = container.get("MetaProps")
    if meta_props:
        _index_plugin_props(index, container_kind, container_id, meta_props, known_ids)


def _index_conditions(
    index: ReverseIndex,
    container_kind: str,
    container_id: int,
    condition: Any,
    known_ids: Dict[int, str],
    known_names: Dict[str, List[TargetKey]],
) -> None:
    if not isinstance(condition, dict):
        return
    # Scripted condition (container Type 4): the only structure is the script
    # text itself. Gate on ScriptSource presence rather than the type code so
    # a future scripted variant still gets scanned.
    script = condition.get("ScriptSource")
    if isinstance(script, str) and script:
        _scan_script_source(
            index, container_kind, container_id, script,
            "condition_reads", known_ids, known_names,
        )
    condition_list = condition.get("ConditionList") or {}
    items = condition_list.get("Conditions") or []
    for item in items:
        if not isinstance(item, dict):
            continue
        cond_type = item.get("Type")
        if cond_type == 3:
            for key in ("VarID", "VarID2"):
                var_id = item.get(key)
                if isinstance(var_id, int) and var_id > 0:
                    index.add(
                        ("variable", var_id),
                        Reference(container_kind, container_id, "condition_reads"),
                    )
        elif cond_type == 7:
            dev_id = item.get("DevID")
            if isinstance(dev_id, int) and dev_id > 0:
                state = item.get("DevState") or ""
                index.add(
                    ("device", dev_id),
                    Reference(
                        container_kind,
                        container_id,
                        "condition_reads",
                        detail=f"state {state}".strip(),
                    ),
                )


def _index_action_steps(
    index: ReverseIndex,
    container_kind: str,
    container_id: int,
    steps: List[Any],
    known_ids: Dict[int, str],
    known_names: Dict[str, List[TargetKey]],
) -> None:
    for step in steps:
        if not isinstance(step, dict):
            continue
        step_class = step.get("Class")

        if step_class == schema.ACTION_CLASS_DEVICE and isinstance(step.get("DeviceID"), int):
            command = schema.lookup(
                schema.DEVICE_ACTION_COMMANDS, step.get("DeviceAction"), "device_action_code"
            )
            index.add(
                ("device", step["DeviceID"]),
                Reference(container_kind, container_id, "acts_on", detail=command),
            )
        elif step_class == schema.ACTION_CLASS_VARIABLE and isinstance(step.get("VarID"), int):
            index.add(
                ("variable", step["VarID"]),
                Reference(container_kind, container_id, "sets"),
            )
        elif step_class == schema.ACTION_CLASS_EXECUTE_ACTION_GROUP and isinstance(
            step.get("ActionGroupID"), int
        ):
            ag_id = step["ActionGroupID"]
            index.add(
                ("action_group", ag_id),
                Reference(container_kind, container_id, "executes"),
            )
            index.exec_parents.setdefault(ag_id, []).append((container_kind, container_id))
        elif step_class == schema.ACTION_CLASS_EMBEDDED_SCRIPT:
            script = step.get("ScriptSource")
            if isinstance(script, str) and script:
                _scan_script_source(
                    index, container_kind, container_id, script,
                    "script_reference", known_ids, known_names,
                )
        elif step_class == schema.ACTION_CLASS_PLUGIN:
            # Class 999 steps can also command a device directly (DeviceID at
            # the step level) in addition to their MetaProps config.
            if isinstance(step.get("DeviceID"), int) and step["DeviceID"] > 0:
                index.add(
                    ("device", step["DeviceID"]),
                    Reference(
                        container_kind,
                        container_id,
                        "acts_on",
                        detail=step.get("TypeLabelPlugin") or step.get("PluginID") or "plugin action",
                    ),
                )
            meta_props = step.get("MetaProps")
            if meta_props:
                _index_plugin_props(index, container_kind, container_id, meta_props, known_ids)


def _scan_script_source(
    index: ReverseIndex,
    container_kind: str,
    container_id: int,
    script: str,
    role: str,
    known_ids: Dict[int, str],
    known_names: Dict[str, List[TargetKey]],
) -> None:
    """
    Heuristic: entity ids and exact quoted entity names appearing in embedded
    Python script text become low-confidence references. False positives (a
    log string that happens to equal an entity name) are the safe direction
    for a "can I delete this?" tool; false negatives were 100% before.
    """
    seen: Set[TargetKey] = set()

    for token in _SCRIPT_ID_RE.findall(script):
        candidate = int(token)
        # Same floor as the plugin-props heuristic: entity ids are large
        # random integers, so small numbers are delays/ports/percentages.
        if candidate < 100000:
            continue
        kind = known_ids.get(candidate)
        if kind is None:
            continue
        target = (kind, candidate)
        if target in seen:
            continue
        seen.add(target)
        index.add(
            target,
            Reference(
                container_kind,
                container_id,
                role,
                detail=f"script references id {candidate}",
                confidence="heuristic",
            ),
        )

    for match in _SCRIPT_STRING_RE.finditer(script):
        literal = match.group(1) or match.group(2)
        if len(literal) < _MIN_NAME_MATCH_LEN:
            continue
        for target in known_names.get(literal, ()):
            if target in seen:
                continue
            seen.add(target)
            index.add(
                target,
                Reference(
                    container_kind,
                    container_id,
                    role,
                    detail=f'script references "{literal}"',
                    confidence="heuristic",
                ),
            )


def _index_plugin_props(
    index: ReverseIndex,
    container_kind: str,
    container_id: int,
    props: Any,
    known_ids: Dict[int, str],
    _seen: Optional[Set[TargetKey]] = None,
) -> None:
    """
    Heuristic: id-shaped values inside plugin config that match a known
    entity id are recorded as low-confidence references.
    """
    if _seen is None:
        _seen = set()

    if isinstance(props, dict):
        values = props.values()
    elif isinstance(props, list):
        values = props
    else:
        values = [props]

    for value in values:
        if isinstance(value, (dict, list)):
            _index_plugin_props(index, container_kind, container_id, value, known_ids, _seen)
            continue
        candidate: Optional[int] = None
        if isinstance(value, int) and not isinstance(value, bool):
            candidate = value
        elif isinstance(value, str) and value.isdigit() and 6 <= len(value) <= 10:
            candidate = int(value)
        # Entity ids are large random integers; a floor screens out config
        # values like ports, delays, and percentages that happen to be ints.
        if candidate is None or candidate < 100000:
            continue
        kind = known_ids.get(candidate)
        if kind is None:
            continue
        target = (kind, candidate)
        if target in _seen:
            continue
        _seen.add(target)
        index.add(
            target,
            Reference(
                container_kind,
                container_id,
                "plugin_config_reference",
                confidence="heuristic",
            ),
        )
