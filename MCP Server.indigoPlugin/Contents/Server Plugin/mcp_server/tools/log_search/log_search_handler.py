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
    """Handler for search_event_log and investigate_event."""

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

    def search_event_log(
        self,
        query: Optional[str] = None,
        regex: bool = False,
        types: Optional[List[str]] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        try:
            start, error = _parse_iso(start_time, "start_time")
            if error:
                return error
            end, error = _parse_iso(end_time, "end_time")
            if error:
                return error

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

            result["parameters"] = {
                "query": query,
                "types": types,
                "start_time": start_time,
                "end_time": end_time,
                "limit": limit,
                "offset": offset,
            }
            self.log_tool_outcome(
                "search_event_log",
                True,
                count=result["count"],
                query_info={"search_query": query} if query else None,
            )
            return result
        except Exception as e:
            return self.handle_exception(e, "searching event log")

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
