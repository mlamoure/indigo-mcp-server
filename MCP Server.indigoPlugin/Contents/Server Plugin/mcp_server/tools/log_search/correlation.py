"""
Cause correlation: given a device change seen in the event log, rank the
triggers / schedules / action groups that fired around the same moment by
how plausibly they caused it.

Scoring combines structural evidence from the reverse-reference index
(does this automation actually act on the device, directly or through
action-group chains?) with temporal proximity. Results always carry the
evidence; the tool reports likelihood, never certainty.
"""

import datetime
import re
from typing import Any, Dict, List, Optional

from .event_log_reader import EventLogReader, LogEntry

AUTOMATION_LOG_TYPES = ["Trigger", "Schedule", "Action Group"]

STRUCTURAL_SCORE = 3.0
CHAIN_DECAY = 0.8
HEURISTIC_SCORE = 1.0

QUOTED_NAME_RE = re.compile(r'"([^"]+)"')

_LOG_TYPE_TO_KIND = {
    "trigger": "trigger",
    "schedule": "schedule",
    "action group": "action_group",
}


def extract_element_name(entry: LogEntry) -> str:
    """
    Automation log lines either carry the element name bare
    ("Trigger\tSunset lights") or quoted inside a phrase
    ('Schedule\tschedule "Check lights" (delayed action)').
    """
    quoted = QUOTED_NAME_RE.search(entry.message)
    if quoted:
        return quoted.group(1)
    return entry.message.strip()


class CauseCorrelator:
    """Builds the ranked candidate-cause list for one target event."""

    def __init__(self, reader: EventLogReader, structure_store, data_provider):
        self.reader = reader
        self.structure_store = structure_store
        self.data_provider = data_provider

    # ------------------------------------------------------------------

    def investigate(
        self,
        device_id: Optional[int] = None,
        search_text: Optional[str] = None,
        around_time: Optional[datetime.datetime] = None,
        occurrence: int = 1,
        lookback_seconds: int = 60,
        lookahead_seconds: int = 5,
    ) -> Dict[str, Any]:
        device = None
        if device_id is not None:
            device = self._describe_device(device_id)
            if device is None:
                return {"error": f"Device {device_id} not found"}
            needle = f'"{device["name"]}"'
        elif search_text:
            needle = search_text
        else:
            return {"error": "Provide device_id or search_text"}

        target = self._locate_target(needle, around_time, occurrence)
        if target is None:
            return {
                "error": "No matching log line found",
                "searched_for": needle,
                "hint": "The change may predate the retained log files, or the "
                "device may log under a different name.",
            }

        candidates = self._collect_candidates(target, lookback_seconds, lookahead_seconds)
        notes: List[str] = []
        if not candidates:
            notes.append(
                "No trigger/schedule/action-group activity in the window — the "
                "change was likely manual/physical control, an external app or "
                "voice assistant, or a plugin acting without a log line."
            )

        result = {
            "target_event": {
                "timestamp": target.timestamp.isoformat() if target.timestamp else None,
                "type": target.type,
                "line": target.message,
            },
            "window": {
                "lookback_seconds": lookback_seconds,
                "lookahead_seconds": lookahead_seconds,
            },
            "candidates": self._rank(candidates, target, device_id, lookback_seconds),
            "notes": notes,
        }
        if device is not None:
            result["target_event"]["device"] = device
        return result

    # ------------------------------------------------------------------

    def _describe_device(self, device_id: int) -> Optional[Dict[str, Any]]:
        name = None
        try:
            entity = self.data_provider.get_device(device_id)
            if entity:
                name = entity.get("name")
        except Exception:
            pass
        if name is None:
            name = self.structure_store.lookup_name("device", device_id)
        if name is None:
            return None
        return {"id": device_id, "name": name}

    def _locate_target(
        self,
        needle: str,
        around_time: Optional[datetime.datetime],
        occurrence: int,
    ) -> Optional[LogEntry]:
        found = self.reader.search(query=needle, limit=max(occurrence, 50))
        if found.get("error") or not found.get("entries"):
            return None

        # Re-materialize LogEntry objects (search returns dicts, newest first)
        entries = [
            LogEntry(
                timestamp=datetime.datetime.fromisoformat(e["timestamp"])
                if e["timestamp"]
                else None,
                type=e["type"],
                message=e["message"],
            )
            for e in found["entries"]
            if e["timestamp"] is not None
        ]
        if not entries:
            return None

        if around_time is not None:
            return min(entries, key=lambda e: abs((e.timestamp - around_time).total_seconds()))
        index = min(occurrence, len(entries)) - 1
        return entries[index]

    def _collect_candidates(
        self, target: LogEntry, lookback_seconds: int, lookahead_seconds: int
    ) -> List[LogEntry]:
        if target.timestamp is None:
            return []
        entries = self.reader.entries_around(
            target.timestamp, lookback_seconds, lookahead_seconds, types=AUTOMATION_LOG_TYPES
        )
        # The target line itself is never a candidate.
        return [e for e in entries if e is not target and e.message != target.message]

    # ------------------------------------------------------------------

    def _rank(
        self,
        candidates: List[LogEntry],
        target: LogEntry,
        device_id: Optional[int],
        lookback_seconds: int,
    ) -> List[Dict[str, Any]]:
        references = (
            self.structure_store.find_references("device", device_id) if device_id else []
        )
        refs_by_container: Dict[Any, List[Dict[str, Any]]] = {}
        for ref in references:
            refs_by_container.setdefault((ref["entity_type"], ref["id"]), []).append(ref)

        ranked = []
        seen_keys = set()
        for entry in candidates:
            kind = _LOG_TYPE_TO_KIND.get((entry.type or "").lower())
            if kind is None:
                continue
            name = extract_element_name(entry)
            elem_id = self._resolve_name(kind, name)
            key = (kind, elem_id or name, entry.timestamp)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            delta = (target.timestamp - entry.timestamp).total_seconds()
            score = 0.0
            evidence: List[str] = []

            if delta >= 0:
                score += max(0.0, 1.0 - delta / max(lookback_seconds, 1))
                evidence.append(f"fired {delta:.1f}s before the target event")
            else:
                score += 0.5 * max(0.0, 1.0 + delta / max(lookback_seconds, 1))
                evidence.append(f"logged {-delta:.1f}s after the target event")

            relationship = None
            if elem_id is not None:
                for ref in refs_by_container.get((kind, elem_id), []):
                    if ref["role"] in ("acts_on", "sets"):
                        chain = ref.get("via_action_groups") or []
                        depth = len(chain)
                        score += STRUCTURAL_SCORE * (CHAIN_DECAY ** depth)
                        relationship = {"role": ref["role"]}
                        if chain:
                            relationship["via_action_groups"] = chain
                            chain_names = " → ".join(
                                str(c.get("name", c)) if isinstance(c, dict) else str(c)
                                for c in chain
                            )
                            evidence.append(
                                f"acts on the device through action group(s): {chain_names}"
                            )
                        else:
                            evidence.append(f'directly {ref["role"].replace("_", " ")} the device')
                        break
                    if ref["role"] == "plugin_config_reference" and relationship is None:
                        score += HEURISTIC_SCORE
                        relationship = {"role": "plugin_config_reference"}
                        evidence.append(
                            "the device id appears in this automation's plugin configuration"
                        )
            if relationship is None:
                evidence.append("temporal proximity only — no structural link found")

            candidate: Dict[str, Any] = {
                "entity_type": kind,
                "name": name,
                "score": round(score, 2),
                "log_timestamp": entry.timestamp.isoformat(),
                "seconds_before_event": round(delta, 1),
                "evidence": evidence,
            }
            if elem_id is not None:
                candidate["id"] = elem_id
            if relationship is not None:
                candidate["relationship"] = relationship
            ranked.append(candidate)

        ranked.sort(key=lambda c: c["score"], reverse=True)
        for rank, candidate in enumerate(ranked, start=1):
            candidate["rank"] = rank
        return ranked

    def _resolve_name(self, kind: str, name: str) -> Optional[int]:
        structures = self.structure_store.get_all_structures(kind)
        matches = [
            elem_id
            for elem_id, struct in structures.items()
            if struct.get("Name") == name
        ]
        if len(matches) == 1:
            return matches[0]
        return None
