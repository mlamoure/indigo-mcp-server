"""
Streaming parser for the .indiDb XML database file.

The file is a single <Database type="dict"> element whose children include
ActionGroupList, TriggerList, TDTriggerList (schedules), DeviceList and
VariableList vectors. Elements use a `type` attribute (string / integer /
bool / real / dict / vector) that drives decoding into plain Python values.

Only trigger/schedule/action-group structures are kept in full. Devices and
variables contribute just id→name maps (used for fallback name resolution
and for the reverse index's plugin-config heuristic). Everything is cleared
as parsing proceeds so the ~5MB tree is never held in memory.
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ParsedDb:
    """Normalized contents of one parse of the database file."""

    mtime: float = 0.0
    size: int = 0
    triggers: Dict[int, dict] = field(default_factory=dict)
    schedules: Dict[int, dict] = field(default_factory=dict)
    action_groups: Dict[int, dict] = field(default_factory=dict)
    device_names: Dict[int, str] = field(default_factory=dict)
    variable_names: Dict[int, str] = field(default_factory=dict)
    reverse_index: Optional[Any] = None  # ReverseIndex, attached by the store

    def counts(self) -> Dict[str, int]:
        return {
            "triggers": len(self.triggers),
            "schedules": len(self.schedules),
            "action_groups": len(self.action_groups),
        }


def decode_element(elem: ET.Element) -> Any:
    """
    Decode one typed XML element into a plain Python value.

    Unknown or missing `type` attributes degrade gracefully: elements with
    children decode as dicts, leaf elements as strings.
    """
    elem_type = elem.get("type")

    if elem_type == "vector":
        return [decode_element(child) for child in elem]
    if elem_type == "dict" or (elem_type is None and len(elem)):
        return {child.tag: decode_element(child) for child in elem}

    text = elem.text or ""
    if elem_type == "integer":
        try:
            return int(text)
        except ValueError:
            return text
    if elem_type == "real":
        try:
            return float(text)
        except ValueError:
            return text
    if elem_type == "bool":
        return text.strip().lower() == "true"
    return text


# Top-level lists we keep in full, mapped to ParsedDb attribute names.
_STRUCTURE_LISTS = {
    "TriggerList": "triggers",
    "TDTriggerList": "schedules",
    "ActionGroupList": "action_groups",
}

# Top-level lists reduced to id→name maps.
_NAME_LISTS = {
    "DeviceList": "device_names",
    "VariableList": "variable_names",
}


def parse_indidb(path: str) -> ParsedDb:
    """
    Parse the database file at `path`.

    Raises on unreadable/malformed XML (the store retains its previous good
    parse in that case). Elements without a usable integer ID are skipped.
    """
    parsed = ParsedDb()

    # Track which top-level list we are inside; harvest and clear each of
    # its direct children on their end events so memory stays flat.
    current_list: Optional[str] = None
    depth = 0

    for event, elem in ET.iterparse(path, events=("start", "end")):
        if event == "start":
            depth += 1
            if depth == 2 and (elem.tag in _STRUCTURE_LISTS or elem.tag in _NAME_LISTS):
                current_list = elem.tag
            continue

        # end event
        depth -= 1
        if depth == 2:
            if current_list in _STRUCTURE_LISTS:
                item = decode_element(elem)
                elem_id = item.get("ID") if isinstance(item, dict) else None
                if isinstance(elem_id, int):
                    getattr(parsed, _STRUCTURE_LISTS[current_list])[elem_id] = item
            elif current_list in _NAME_LISTS:
                # Pull ID/Name without decoding the whole entry.
                elem_id_text = elem.findtext("ID")
                name = elem.findtext("Name")
                try:
                    elem_id = int(elem_id_text)
                except (TypeError, ValueError):
                    elem_id = None
                if elem_id is not None and name is not None:
                    getattr(parsed, _NAME_LISTS[current_list])[elem_id] = name
            elem.clear()
        elif depth == 1:
            current_list = None
            elem.clear()

    return parsed
