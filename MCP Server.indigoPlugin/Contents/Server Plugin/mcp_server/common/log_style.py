"""
Logging style helpers — one place that defines what the user sees.

Style guide
===========

Levels (INFO+ reaches the user-visible Indigo event log):
- INFO    something happened to my home or my plugin that I'd want to know:
          start/ready/stop, an AI changed a device/variable/thermostat,
          subscription created/fired/expired, webhook delivered, one-line
          sync summary, config applied.
- DEBUG   how it happened: sessions, IPs, protocol versions, batch/retry
          counters, tracebacks, full webhook URLs, read-only tool calls
          (unless the user opts in via the "Log AI read activity" pref).
- WARNING degraded but still working; no user action strictly required.
- ERROR   an operation failed; one line, plain language, what + why +
          what to do when known. Exception detail goes to DEBUG, never
          INFO/ERROR. Log each failure ONCE, at the outermost layer that
          knows the user-level action.

Voice: present tense, plain English, entity names in quotes ('Kitchen
Lights'), no bare IDs at INFO, no protocol jargon ("search index", not
"vector store").

Emoji (fixed set, always the first character of the message):
- ✅ lifecycle / success milestone
- ❌ ERROR lines only
- ⚠️ WARNING lines only
- 🔧 an MCP client changed (or read, when opted in) something
- 🔔 event subscriptions & webhook deliveries
- 📊 search-index (vector store) status
- 🌐 connection / endpoint info

Formatting: no leading tabs or spaces (Indigo already prefixes timestamp
and plugin name); no newlines at INFO except explicit menu-action dumps.
"""

import logging
from typing import Optional
from urllib.parse import urlsplit

# Category emojis — import these rather than hardcoding so the set stays fixed.
OK = "✅"
FAIL = "❌"
WARN = "⚠️"
ACTIVITY = "🔧"
EVENT = "🔔"
INDEX = "📊"
ENDPOINT = "🌐"

# Module-level pref: when True, read-only MCP activity is promoted to INFO.
# Set from plugin.startup()/closedPrefsConfigUi(); module-level to avoid
# plumbing the pref through every handler constructor chain.
_verbose_activity = False


def set_verbose_activity(enabled: bool) -> None:
    """Enable/disable INFO-level logging of read-only MCP activity."""
    global _verbose_activity
    _verbose_activity = bool(enabled)


def verbose_activity() -> bool:
    """Whether read-only MCP activity is currently promoted to INFO."""
    return _verbose_activity


def activity(logger: logging.Logger, message: str, write: bool = True) -> None:
    """
    Log MCP client activity.

    Writes (state changes) are always INFO; reads are DEBUG unless the
    user opted in via the "Log AI read activity" pref.
    """
    line = f"{ACTIVITY} {message}"
    if write or _verbose_activity:
        logger.info(line)
    else:
        logger.debug(line)


def fail(logger: logging.Logger, action: str, exc: Exception, hint: str = "") -> None:
    """
    Log a failure once, user-friendly.

    Emits one ERROR line ('❌ {action} failed: {plain reason}') and the
    full exception with traceback at DEBUG.
    """
    reason = plain_reason(exc)
    suffix = f" — {hint}" if hint else ""
    logger.error(f"{FAIL} {action} failed: {reason}{suffix}")
    logger.debug(f"{action} failed", exc_info=exc)


def plain_reason(exc: Exception) -> str:
    """Map an exception to a plain-language reason a home user can act on."""
    import json

    # openai is an optional heavy import; match by name to avoid requiring it
    exc_type = type(exc).__name__

    if isinstance(exc, TimeoutError) or exc_type in ("Timeout", "ReadTimeout", "ConnectTimeout"):
        return "the request timed out"
    if isinstance(exc, ConnectionError) or exc_type in ("URLError", "ConnectionError", "APIConnectionError"):
        return "couldn't connect to the service"
    if exc_type in ("AuthenticationError", "PermissionDeniedError"):
        return "OpenAI rejected the API key (check Plugin Config)"
    if exc_type == "RateLimitError":
        return "OpenAI rate limit reached — try again shortly"
    if isinstance(exc, json.JSONDecodeError):
        return "received an invalid response"
    if isinstance(exc, KeyError):
        return f"not found: {exc.args[0] if exc.args else exc}"
    message = str(exc).strip()
    return message if message else exc_type


def host_only(url: Optional[str]) -> str:
    """
    Reduce a URL to its host for INFO-level logging.

    Webhook URLs can embed tokens/secrets in path or query — only the
    netloc is safe to show; the full URL belongs at DEBUG.
    """
    if not url:
        return "unknown"
    try:
        netloc = urlsplit(url).netloc
        # Strip embedded basic-auth credentials if present
        if "@" in netloc:
            netloc = netloc.rsplit("@", 1)[1]
        return netloc or url
    except (ValueError, AttributeError):
        return "unknown"
