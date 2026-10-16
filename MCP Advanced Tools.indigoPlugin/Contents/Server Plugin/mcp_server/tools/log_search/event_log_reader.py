"""
Reader for Indigo's daily event-log files.

Indigo writes one file per day under its Logs folder, named
"YYYY-MM-DD Events.txt", with tab-separated lines:

    2026-07-02 16:30:00.415\tAction Group\tTurn off all outdoor hue lights

Continuation lines (multi-line messages, e.g. script tracebacks) do not
start with a timestamp and are appended to the preceding entry.
"""

import datetime
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

LOG_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}) Events\.txt$")
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")

# Guards against pathological requests: at most this many day-files and
# parsed lines per query. Truncation is reported, never silent.
MAX_FILES_PER_QUERY = 14
MAX_LINES_SCANNED = 200_000


@dataclass
class LogEntry:
    """One event-log line (plus any continuation lines)."""

    timestamp: Optional[datetime.datetime]
    type: Optional[str]
    message: str
    raw: str = field(repr=False, default="")

    def as_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "type": self.type,
            "message": self.message,
        }


def _parse_timestamp(text: str) -> Optional[datetime.datetime]:
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def parse_log_line(line: str) -> Optional[LogEntry]:
    """Parse one line; None means it is a continuation of the previous line."""
    if not TIMESTAMP_RE.match(line):
        return None
    parts = line.rstrip("\n").split("\t", 2)
    timestamp = _parse_timestamp(parts[0].strip())
    if len(parts) == 3:
        return LogEntry(timestamp=timestamp, type=parts[1].strip(), message=parts[2], raw=line)
    if len(parts) == 2:
        return LogEntry(timestamp=timestamp, type=None, message=parts[1], raw=line)
    return LogEntry(timestamp=timestamp, type=None, message=line.rstrip("\n"), raw=line)


class EventLogReader:
    """Reads and filters entries from the daily Events.txt files."""

    def __init__(
        self,
        logs_folder_supplier: Callable[[], Optional[str]],
        logger: Optional[logging.Logger] = None,
    ):
        self._logs_folder_supplier = logs_folder_supplier
        self.logger = logger or logging.getLogger("Plugin")

    # ------------------------------------------------------------------

    def list_log_files(self) -> List[Any]:
        """(date, path) for every day-file, oldest first."""
        try:
            folder = self._logs_folder_supplier()
        except Exception as e:
            self.logger.debug(f"Logs folder lookup failed: {e}")
            return []
        if not folder or not os.path.isdir(folder):
            return []

        files = []
        for name in os.listdir(folder):
            match = LOG_FILE_RE.match(name)
            if not match:
                continue
            try:
                file_date = datetime.date.fromisoformat(match.group(1))
            except ValueError:
                continue
            files.append((file_date, os.path.join(folder, name)))
        files.sort()
        return files

    def read_day(self, path: str) -> List[LogEntry]:
        """All entries of one day-file, in file (chronological) order."""
        entries: List[LogEntry] = []
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    entry = parse_log_line(line)
                    if entry is not None:
                        entries.append(entry)
                    elif entries:
                        entries[-1].message += "\n" + line.rstrip("\n")
                    elif line.strip():
                        entries.append(
                            LogEntry(timestamp=None, type=None, message=line.rstrip("\n"), raw=line)
                        )
        except OSError as e:
            self.logger.debug(f"Could not read log file {path}: {e}")
        return entries

    # ------------------------------------------------------------------

    def search(
        self,
        query: Optional[str] = None,
        regex: bool = False,
        types: Optional[List[str]] = None,
        start_time: Optional[datetime.datetime] = None,
        end_time: Optional[datetime.datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        Search entries newest-first. Returns matches plus scan metadata.
        """
        matcher = None
        if query:
            if regex:
                try:
                    pattern = re.compile(query, re.IGNORECASE)
                except re.error as e:
                    return {"error": f"Invalid regex: {e}"}
                matcher = lambda text: bool(pattern.search(text))  # noqa: E731
            else:
                needle = query.lower()
                matcher = lambda text: needle in text.lower()  # noqa: E731

        type_set = {t.lower() for t in types} if types else None

        files = self.list_log_files()
        if start_time or end_time:
            start_date = start_time.date() if start_time else datetime.date.min
            end_date = end_time.date() if end_time else datetime.date.max
            files = [f for f in files if start_date <= f[0] <= end_date]

        files_truncated = len(files) > MAX_FILES_PER_QUERY
        # Newest files first; within the cap keep the most recent ones.
        files = files[-MAX_FILES_PER_QUERY:][::-1]

        matches: List[LogEntry] = []
        lines_scanned = 0
        lines_truncated = False
        wanted = offset + limit

        for _, path in files:
            day_entries = self.read_day(path)
            lines_scanned += len(day_entries)
            for entry in reversed(day_entries):  # newest first within the day
                if start_time and entry.timestamp and entry.timestamp < start_time:
                    continue
                if end_time and entry.timestamp and entry.timestamp > end_time:
                    continue
                if type_set is not None and (entry.type or "").lower() not in type_set:
                    continue
                if matcher is not None and not (
                    matcher(entry.message) or (entry.type and matcher(entry.type))
                ):
                    continue
                matches.append(entry)
                if len(matches) >= wanted:
                    break
            if len(matches) >= wanted:
                break
            if lines_scanned >= MAX_LINES_SCANNED:
                lines_truncated = True
                break

        page = matches[offset:offset + limit]
        return {
            "entries": [entry.as_dict() for entry in page],
            "count": len(page),
            "files_scanned": len(files),
            "truncated": lines_truncated
            or files_truncated
            or len(matches) >= wanted,
        }

    def entries_around(
        self,
        center: datetime.datetime,
        lookback_seconds: int,
        lookahead_seconds: int,
        types: Optional[List[str]] = None,
    ) -> List[LogEntry]:
        """
        Entries within [center - lookback, center + lookahead], chronological.
        """
        window_start = center - datetime.timedelta(seconds=lookback_seconds)
        window_end = center + datetime.timedelta(seconds=lookahead_seconds)
        type_set = {t.lower() for t in types} if types else None

        results: List[LogEntry] = []
        for file_date, path in self.list_log_files():
            if file_date < window_start.date() or file_date > window_end.date():
                continue
            for entry in self.read_day(path):
                if entry.timestamp is None:
                    continue
                if not (window_start <= entry.timestamp <= window_end):
                    continue
                if type_set is not None and (entry.type or "").lower() not in type_set:
                    continue
                results.append(entry)
        results.sort(key=lambda entry: entry.timestamp)
        return results
