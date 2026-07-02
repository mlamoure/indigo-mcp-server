"""
Event-log investigation tools: historical search over the daily Events.txt
files and cause correlation ("what made this device change?").
"""

from .event_log_reader import EventLogReader, LogEntry
from .log_search_handler import LogSearchHandler

__all__ = ["EventLogReader", "LogEntry", "LogSearchHandler"]
