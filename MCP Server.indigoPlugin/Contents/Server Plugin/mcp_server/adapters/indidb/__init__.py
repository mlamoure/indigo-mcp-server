"""
Read-only adapter for Indigo's on-disk .indiDb XML database.

The Indigo Object Model (IOM) does not expose the action steps or condition
trees inside triggers, schedules, or action groups. The server's database
file does. This package parses that file (path from
indigo.server.getDbFilePath()) into normalized dictionaries and builds a
reverse-reference index over them.

Pure stdlib — nothing in this package may import `indigo`.
"""

from .parser import ParsedDb, parse_indidb
from .reverse_index import ReverseIndex, build_reverse_index
from .store import IndiDbStructureStore

__all__ = [
    "ParsedDb",
    "parse_indidb",
    "ReverseIndex",
    "build_reverse_index",
    "IndiDbStructureStore",
]
