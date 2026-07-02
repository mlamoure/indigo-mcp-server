"""
Handlers for the event-log investigation tools: historical search and
cause correlation.
"""

import datetime
import logging
from typing import Any, Dict, List, Optional

from ...adapters.data_provider import DataProvider
from ...adapters.indidb import IndiDbStructureStore
from ..base_handler import BaseToolHandler
from .correlation import CauseCorrelator
from .event_log_reader import EventLogReader


def _parse_iso(value: Optional[str], field_name: str):
    if value in (None, ""):
        return None, None
    try:
        return datetime.datetime.fromisoformat(value), None
    except ValueError:
        return None, {
            "error": f"Invalid {field_name}: {value!r} (expected ISO format, "
            f"e.g. 2026-07-02T16:30:00)",
            "success": False,
        }


class LogSearchHandler(BaseToolHandler):
    """Handler for query_event_log and investigate_event."""

    def __init__(
        self,
        data_provider: DataProvider,
        structure_store: IndiDbStructureStore,
        logger: Optional[logging.Logger] = None,
    ):
        super().__init__(tool_name="log_search", logger=logger)
        self.data_provider = data_provider
        self.structure_store = structure_store
        self.reader = EventLogReader(
            logs_folder_supplier=data_provider.get_logs_folder_path, logger=logger
        )
        self.correlator = CauseCorrelator(self.reader, structure_store, data_provider)

    def query_event_log(
        self,
        query: Optional[str] = None,
        regex: bool = False,
        types: Optional[List[str]] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        Read the Indigo event log, newest first.

        With no filters (query/types/time range) this returns the most recent
        entries straight from Indigo's live event log via the Object Model —
        cheap and independent of the log files on disk. Supplying any filter
        switches to a scan of the daily "YYYY-MM-DD Events.txt" files, which
        reaches full history and supports text/regex matching, type filters,
        and time ranges. Either way the output shape is identical.
        """
        try:
            start, error = _parse_iso(start_time, "start_time")
            if error:
                return error
            end, error = _parse_iso(end_time, "end_time")
            if error:
                return error

            has_filter = bool(query or types or start or end)
            if has_filter:
                result = self.reader.search(
                    query=query,
                    regex=regex,
                    types=types,
                    start_time=start,
                    end_time=end,
                    limit=limit,
                    offset=offset,
                )
                if "error" in result:
                    return {**result, "success": False}
                result["source"] = "log_files"
            else:
                result = self._recent_tail(limit, offset)

            result["parameters"] = {
                "query": query,
                "types": types,
                "start_time": start_time,
                "end_time": end_time,
                "limit": limit,
                "offset": offset,
            }
            self.log_tool_outcome(
                "query_event_log",
                True,
                count=result["count"],
                query_info={"search_query": query} if query else None,
            )
            return result
        except Exception as e:
            return self.handle_exception(e, "querying event log")

    def _recent_tail(self, limit: int, offset: int) -> Dict[str, Any]:
        """Most-recent entries from the live IOM event log (no filters)."""
        raw = self.data_provider.get_event_log_list(line_count=limit + offset)
        entries = [self._normalize_iom_entry(e) for e in raw]
        # Present newest-first, consistent with the file-scan path.
        entries.sort(
            key=lambda e: (e["timestamp"] is not None, e["timestamp"]), reverse=True
        )
        page = entries[offset:offset + limit]
        return {
            "entries": page,
            "count": len(page),
            "source": "live",
            # Whether older entries exist beyond what the live log returned.
            "truncated": len(raw) >= (limit + offset) and len(raw) > 0,
        }

    @staticmethod
    def _normalize_iom_entry(entry: Any) -> Dict[str, Any]:
        """Map an indigo.server.getEventLogList dict to the common shape.

        Falls back gracefully if a future Indigo returns plain strings."""
        if isinstance(entry, dict):
            timestamp = entry.get("TimeStamp")
            return {
                "timestamp": timestamp.isoformat()
                if hasattr(timestamp, "isoformat")
                else None,
                "type": entry.get("TypeStr"),
                "message": (entry.get("Message") or "").strip(),
            }
        return {"timestamp": None, "type": None, "message": str(entry).strip()}

    def investigate_event(
        self,
        device_id: Optional[int] = None,
        search_text: Optional[str] = None,
        around_time: Optional[str] = None,
        occurrence: int = 1,
        lookback_seconds: int = 60,
        lookahead_seconds: int = 5,
    ) -> Dict[str, Any]:
        try:
            if device_id is None and not search_text:
                return {
                    "error": "Provide device_id or search_text",
                    "success": False,
                }
            center, error = _parse_iso(around_time, "around_time")
            if error:
                return error
            if not 1 <= lookback_seconds <= 3600:
                return {
                    "error": "lookback_seconds must be between 1 and 3600",
                    "success": False,
                }

            result = self.correlator.investigate(
                device_id=device_id,
                search_text=search_text,
                around_time=center,
                occurrence=max(1, occurrence),
                lookback_seconds=lookback_seconds,
                lookahead_seconds=lookahead_seconds,
            )
            if "error" not in result:
                result["hint"] = (
                    "Use get_automation_details on the top candidate to see "
                    "exactly what it executes."
                )
                self.log_tool_outcome(
                    "investigate_event", True, count=len(result.get("candidates", []))
                )
            return result
        except Exception as e:
            return self.handle_exception(e, "investigating event")
