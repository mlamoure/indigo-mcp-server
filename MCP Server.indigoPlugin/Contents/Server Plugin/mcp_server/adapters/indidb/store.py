"""
Mtime-cached access to the parsed .indiDb structures.

The Indigo server rewrites the database file within minutes of changes, so
the parse is cached on (mtime, size) and refreshed lazily on access. A parse
failure (e.g. reading mid-rewrite) retains the last good cache; the next
access retries.
"""

import datetime
import logging
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from .parser import ParsedDb, parse_indidb
from .reverse_index import build_reverse_index

_KIND_ATTRS = {
    "trigger": "triggers",
    "schedule": "schedules",
    "action_group": "action_groups",
}


class IndiDbStructureStore:
    """Lazy, cached, read-only view of the database file's structures."""

    def __init__(
        self,
        db_path_supplier: Callable[[], Optional[str]],
        logger: Optional[logging.Logger] = None,
        stat_throttle_seconds: float = 2.0,
    ):
        """
        Args:
            db_path_supplier: Returns the database file path (from
                indigo.server.getDbFilePath() in production, a fixture path
                in tests). May return None when unavailable.
            logger: Optional logger instance.
            stat_throttle_seconds: Minimum interval between os.stat checks,
                so bursts of tool calls don't stat the file repeatedly.
        """
        self._db_path_supplier = db_path_supplier
        self.logger = logger or logging.getLogger("Plugin")
        self._stat_throttle_seconds = stat_throttle_seconds
        self._lock = threading.Lock()
        self._cache: Optional[ParsedDb] = None
        self._last_stat_time = 0.0

    # ------------------------------------------------------------------
    # Public accessors — all degrade to None/empty rather than raising.
    # ------------------------------------------------------------------

    def get_structure(self, kind: str, elem_id: int) -> Optional[dict]:
        """Raw-normalized structure dict for one trigger/schedule/action_group."""
        parsed = self._ensure_fresh()
        attr = _KIND_ATTRS.get(kind)
        if parsed is None or attr is None:
            return None
        return getattr(parsed, attr).get(elem_id)

    def get_all_structures(self, kind: str) -> Dict[int, dict]:
        parsed = self._ensure_fresh()
        attr = _KIND_ATTRS.get(kind)
        if parsed is None or attr is None:
            return {}
        return getattr(parsed, attr)

    def find_references(self, entity_kind: str, entity_id: int) -> List[Dict[str, Any]]:
        """Role-tagged containers referencing (entity_kind, entity_id)."""
        parsed = self._ensure_fresh()
        if parsed is None or parsed.reverse_index is None:
            return []
        return parsed.reverse_index.references_to(entity_kind, entity_id)

    def lookup_name(self, entity_kind: str, entity_id: int) -> Optional[str]:
        """Fallback name resolution from the file (devices/variables/AGs)."""
        parsed = self._ensure_fresh()
        if parsed is None:
            return None
        if entity_kind == "device":
            return parsed.device_names.get(entity_id)
        if entity_kind == "variable":
            return parsed.variable_names.get(entity_id)
        if entity_kind == "action_group":
            ag = parsed.action_groups.get(entity_id)
            return ag.get("Name") if isinstance(ag, dict) else None
        if entity_kind == "trigger":
            trigger = parsed.triggers.get(entity_id)
            return trigger.get("Name") if isinstance(trigger, dict) else None
        if entity_kind == "schedule":
            sched = parsed.schedules.get(entity_id)
            return sched.get("Name") if isinstance(sched, dict) else None
        return None

    def freshness(self) -> Dict[str, Any]:
        """Metadata for tool responses about where structure data came from."""
        parsed = self._ensure_fresh()
        if parsed is None:
            return {"available": False}
        return {
            "available": True,
            "file_modified": datetime.datetime.fromtimestamp(parsed.mtime).isoformat(),
            "counts": parsed.counts(),
            "note": (
                "Action steps and conditions come from Indigo's database file, "
                "which the server rewrites within minutes of changes; very "
                "recent edits may not be reflected yet."
            ),
        }

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def _ensure_fresh(self) -> Optional[ParsedDb]:
        with self._lock:
            now = time.monotonic()
            if self._cache is not None and (now - self._last_stat_time) < self._stat_throttle_seconds:
                return self._cache

            path = None
            try:
                path = self._db_path_supplier()
            except Exception as e:
                self.logger.debug(f"indiDb path lookup failed: {e}")
            if not path or not os.path.isfile(path):
                return self._cache

            self._last_stat_time = now
            try:
                stat = os.stat(path)
            except OSError as e:
                self.logger.debug(f"indiDb stat failed: {e}")
                return self._cache

            if self._cache is not None and (
                stat.st_mtime == self._cache.mtime and stat.st_size == self._cache.size
            ):
                return self._cache

            try:
                started = time.monotonic()
                parsed = parse_indidb(path)
                parsed.mtime = stat.st_mtime
                parsed.size = stat.st_size
                parsed.reverse_index = build_reverse_index(parsed)
                self._cache = parsed
                elapsed_ms = (time.monotonic() - started) * 1000
                self.logger.debug(
                    f"indiDb parsed in {elapsed_ms:.0f}ms: {parsed.counts()}"
                )
            except Exception as e:
                # Mid-rewrite reads can hand us a torn file; keep the last
                # good parse and retry on the next access.
                self.logger.debug(f"indiDb parse failed (mid-rewrite?): {e}")
            return self._cache
