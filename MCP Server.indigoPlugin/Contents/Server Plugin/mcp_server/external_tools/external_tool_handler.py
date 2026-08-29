"""
Dispatch of plugin-provided tool calls via cross-plugin executeAction.

The provider contract (docs/mcp-provider-manifest.md): the call carries
props {"tool": <bare name>, "arguments": <JSON string>} and the provider
returns a JSON string envelope {"status": "ok", "result": ...} or
{"status": "error", "error": {"type": ..., "message": ..., "details": ...}}.
Arguments and results cross as JSON strings because indigo.Dict cannot hold
None values or $-prefixed keys.

executeAction has no timeout of its own and raises an undifferentiated
Exception on failure, so each call runs in a short-lived thread joined with
the manifest's per-tool deadline. On timeout the orphaned thread is left to
finish on its own (executeAction cannot be cancelled) — an accepted,
bounded leak that is logged loudly.
"""

import json
import threading
from typing import Any, Dict

from ..tools.base_handler import BaseToolHandler

try:
    import indigo
except ImportError:
    indigo = None  # unit tests run outside Indigo


class ExternalToolHandler(BaseToolHandler):
    """Invokes tools contributed by other Indigo plugins."""

    def __init__(self, logger=None):
        super().__init__(tool_name="external_tools", logger=logger)

    def invoke(
        self,
        provider_id: str,
        action_id: str,
        bare_name: str,
        display_name: str,
        arguments: Dict[str, Any],
        timeout_seconds: int,
        write: bool,
    ) -> dict:
        """
        Call one provider tool and return the house-style result dict.
        Ordinary failures come back as {"success": False, ...}; this method
        never raises.
        """
        full_label = f"{display_name}: {bare_name}"

        plugin = indigo.server.getPlugin(provider_id)
        # isRunning(), not isEnabled(): a plugin that hit a fatal error stays
        # enabled but is not running, and executeAction would just raise
        if not plugin.isRunning():
            return {
                "success": False,
                "provider": provider_id,
                "error": (
                    f"The {display_name} plugin is not running, so its tools are "
                    f"unavailable. Enable/restart it in Indigo and try again."
                ),
            }

        props = {"tool": bare_name, "arguments": json.dumps(arguments)}

        result_slot: Dict[str, Any] = {}

        def _run():
            try:
                result_slot["value"] = plugin.executeAction(
                    action_id, props=props, waitUntilDone=True
                )
            except Exception as e:  # undifferentiated by design of the platform
                result_slot["exception"] = e

        worker = threading.Thread(
            target=_run, name=f"ext-tool-{provider_id}-{bare_name}", daemon=True
        )
        worker.start()
        worker.join(timeout_seconds)

        if worker.is_alive():
            self.error_log(
                f"{full_label} timed out after {timeout_seconds}s — the call is "
                f"still running in {display_name} and cannot be cancelled"
            )
            return {
                "success": False,
                "provider": provider_id,
                "error": (
                    f"{full_label} did not reply within {timeout_seconds}s. The "
                    f"provider may be busy or hung; check its plugin.log."
                ),
                "timeout": True,
            }

        if "exception" in result_slot:
            e = result_slot["exception"]
            self.error_log(f"{full_label} raised: {e}")
            return {
                "success": False,
                "provider": provider_id,
                "error": (
                    f"{full_label} failed: {e}. Possible causes: the provider "
                    f"does not define action '{action_id}', it crashed mid-call, "
                    f"or its handler raised — check the provider's plugin.log."
                ),
            }

        reply = self._parse_envelope(result_slot.get("value"), provider_id, full_label)
        if reply.get("success"):
            self.activity_log(full_label, write=write)
        return reply

    def _parse_envelope(
        self, raw: Any, provider_id: str, full_label: str
    ) -> dict:
        """Map the provider's JSON-string envelope to the house result shape."""
        if not isinstance(raw, str):
            self.error_log(
                f"{full_label} returned {type(raw).__name__} instead of a JSON string"
            )
            return {
                "success": False,
                "provider": provider_id,
                "error": (
                    f"{full_label} violated the provider protocol: expected a JSON "
                    f"string reply, got {type(raw).__name__}."
                ),
            }
        try:
            envelope = json.loads(raw)
        except json.JSONDecodeError as e:
            self.error_log(f"{full_label} returned invalid JSON: {e}")
            return {
                "success": False,
                "provider": provider_id,
                "error": f"{full_label} violated the provider protocol: reply is not valid JSON ({e}).",
            }

        status = envelope.get("status") if isinstance(envelope, dict) else None
        if status == "ok":
            return {
                "success": True,
                "provider": provider_id,
                "result": envelope.get("result"),
            }
        if status == "error":
            error = envelope.get("error") or {}
            reply = {
                "success": False,
                "provider": provider_id,
                "error": error.get("message", "unknown provider error"),
                "error_type": error.get("type", "internal"),
            }
            if error.get("details") is not None:
                reply["details"] = error["details"]
            return reply

        self.error_log(f"{full_label} returned an envelope without a valid status")
        return {
            "success": False,
            "provider": provider_id,
            "error": (
                f"{full_label} violated the provider protocol: reply must be "
                f'{{"status": "ok"|"error", ...}}.'
            ),
        }
