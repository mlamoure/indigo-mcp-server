"""
Structured event model for webhook notifications.

Defines the Event dataclass (the JSON payload POSTed to subscriber endpoints)
and a lightweight ULID generator for sortable, unique event IDs.
"""

import os
import socket
import struct
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# ULID generator (stdlib only, no external deps)
# ---------------------------------------------------------------------------

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode_crockford(data: bytes, length: int) -> str:
    """Encode bytes as Crockford base32 string of given length."""
    # Convert bytes to an integer
    num = int.from_bytes(data, byteorder="big")
    # Extract 5-bit groups from least-significant end, then reverse
    # to get most-significant-first ordering (required for lexicographic sort)
    chars = []
    for _ in range(length):
        chars.append(_CROCKFORD[num & 0x1F])  # 0x1F = 31 = 5-bit mask
        num >>= 5  # shift right by 5 bits for next character
    chars.reverse()
    return "".join(chars)


def generate_ulid() -> str:
    """
    Generate a ULID-like sortable unique ID.

    Format: 10 chars timestamp (48-bit ms) + 16 chars random (80-bit).
    Total: 26 chars, Crockford base32, lexicographically sortable by time.
    """
    timestamp_ms = int(time.time() * 1000)
    ts_bytes = struct.pack(">Q", timestamp_ms)[-6:]  # 48-bit timestamp
    rand_bytes = os.urandom(10)  # 80-bit random

    ts_str = _encode_crockford(ts_bytes, 10)
    rand_str = _encode_crockford(rand_bytes, 16)
    return ts_str + rand_str


# ---------------------------------------------------------------------------
# Event dataclass
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "1.0"
PLUGIN_ID = "com.vtmikel.mcp_server"


def _get_hostname() -> str:
    """Get hostname, cached after first call."""
    if not hasattr(_get_hostname, "_cached"):
        try:
            _get_hostname._cached = socket.gethostname()
        except Exception:
            _get_hostname._cached = "unknown"
    return _get_hostname._cached


@dataclass
class Event:
    """
    Structured event payload POSTed to webhook subscriber endpoints.

    Delivery semantics: at-least-once. Receivers MUST dedupe by event_id.
    """

    # Identity
    event_id: str = field(default_factory=generate_ulid)
    schema_version: str = field(default=SCHEMA_VERSION)

    # Dedup
    dedupe_key: str = ""

    # Source
    source: Dict[str, str] = field(default_factory=lambda: {
        "system": "indigo",
        "plugin": PLUGIN_ID,
        "host": _get_hostname(),
    })

    # Timing
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Classification
    event_type: str = ""  # e.g. "device.state_changed", "variable.value_changed"

    # Entity
    entity: Dict[str, Any] = field(default_factory=dict)
    # Expected shape: {kind: "device"|"variable", id: int, name: str, device_type: str}

    # State change
    state: Dict[str, Any] = field(default_factory=dict)
    # Expected shape: {changed_keys: [...], old: {key: val}, new: {key: val}}

    # Trigger info (which subscription/conditions fired)
    trigger: Dict[str, Any] = field(default_factory=dict)
    # Expected shape: {subscription_id: str, conditions_matched: {...}}

    # Human-readable
    human: Dict[str, str] = field(default_factory=dict)
    # Expected shape: {title: str, summary: str}

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict suitable for JSON encoding."""
        return asdict(self)
