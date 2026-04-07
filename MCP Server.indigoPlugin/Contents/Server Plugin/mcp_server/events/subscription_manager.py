"""
Subscription manager — stores active subscriptions and evaluates
Indigo state changes against subscription conditions.

Reuses StateFilter from mcp_server/common/state_filter.py for condition
matching (eq, ne, gt, gte, lt, lte, contains, regex operators).
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..common.state_filter import StateFilter
from .event_model import Event, generate_ulid
from .subscription_model import Subscription
from .dwell_timer import DwellTimerQueue


class SubscriptionManager:
    """
    Manages event subscriptions and evaluates entity state changes.

    Thread-safe: callbacks write via evaluate_*, MCP tools read/write via CRUD.
    """

    def __init__(
        self,
        dispatch_callback: Optional[Callable[[Subscription, Event], None]] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Args:
            dispatch_callback: Called to dispatch webhook for dwell timer expiry.
                               Set after WebhookDispatcher is created.
            logger: Optional logger instance.
        """
        self._logger = logger or logging.getLogger(__name__)
        self._subscriptions: Dict[str, Subscription] = {}
        self._lock = threading.Lock()

        # Dwell timer queue — callback set to dispatch_callback
        self._dwell_timer: Optional[DwellTimerQueue] = None
        if dispatch_callback:
            self._dwell_timer = DwellTimerQueue(
                callback=dispatch_callback, logger=self._logger
            )

    def set_dispatch_callback(
        self, callback: Callable[[Subscription, Event], None]
    ) -> None:
        """Set the dispatch callback (for deferred initialization)."""
        self._dwell_timer = DwellTimerQueue(callback=callback, logger=self._logger)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(
        self,
        webhook_url: str,
        entity_type: str,
        conditions: Dict[str, Any],
        auth_mode: str = "none",
        auth_token: str = "",
        verify_ssl: bool = True,
        entity_id: Optional[int] = None,
        duration_seconds: Optional[int] = None,
        description: str = "",
    ) -> Subscription:
        """Create a new subscription. Returns the created Subscription."""
        sub = Subscription(
            webhook_url=webhook_url,
            auth_mode=auth_mode,
            auth_token=auth_token,
            verify_ssl=verify_ssl,
            entity_type=entity_type,
            entity_id=entity_id,
            conditions=conditions,
            duration_seconds=duration_seconds,
            description=description,
        )

        with self._lock:
            self._subscriptions[sub.subscription_id] = sub

        self._logger.info(
            f"Subscription created: {sub.subscription_id} "
            f"({sub.entity_type}"
            f"{':' + str(sub.entity_id) if sub.entity_id else ''}) "
            f"→ {sub.webhook_url}"
        )
        return sub

    def delete(self, subscription_id: str) -> bool:
        """Delete a subscription by ID. Returns True if found and deleted."""
        with self._lock:
            sub = self._subscriptions.pop(subscription_id, None)

        if sub is None:
            return False

        # Cancel any pending dwell timers for this subscription
        if self._dwell_timer and sub.entity_id is not None:
            self._dwell_timer.cancel_dwell(subscription_id, sub.entity_id)

        self._logger.info(f"Subscription deleted: {subscription_id}")
        return True

    def list_all(self) -> List[Subscription]:
        """Return all active subscriptions."""
        with self._lock:
            return list(self._subscriptions.values())

    def get(self, subscription_id: str) -> Optional[Subscription]:
        """Get a subscription by ID."""
        with self._lock:
            return self._subscriptions.get(subscription_id)

    def count(self) -> int:
        """Return the number of active subscriptions."""
        with self._lock:
            return len(self._subscriptions)

    # ------------------------------------------------------------------
    # State change evaluation
    # ------------------------------------------------------------------

    def evaluate_device_change(
        self,
        orig_dev: Dict[str, Any],
        new_dev: Dict[str, Any],
    ) -> List[Tuple[Subscription, Event]]:
        """
        Evaluate all device subscriptions against a device state change.

        Uses transition detection: fires only when the NEW state matches
        the condition but the OLD state did NOT (transition INTO match).

        Returns list of (subscription, event) pairs that matched.
        """
        # Quick-reject: no actual state change
        if not self._has_state_changed(orig_dev, new_dev):
            return []

        device_id = new_dev.get("id")
        matches = []

        with self._lock:
            device_subs = [
                s for s in self._subscriptions.values()
                if s.entity_type == "device"
            ]

        for sub in device_subs:
            # Skip if subscription targets a different entity
            if sub.entity_id is not None and sub.entity_id != device_id:
                continue

            # Transition detection: new state matches, old state did NOT
            new_matches = StateFilter.matches_state(new_dev, sub.conditions)
            old_matches = StateFilter.matches_state(orig_dev, sub.conditions)

            if new_matches and not old_matches:
                event = self._build_device_event(orig_dev, new_dev, sub)

                if sub.duration_seconds and self._dwell_timer:
                    # Dwell-time: start timer, don't fire yet
                    self._dwell_timer.start_dwell(
                        sub, event, sub.duration_seconds, device_id
                    )
                else:
                    matches.append((sub, event))

            elif not new_matches and old_matches:
                # Condition reverted — cancel any pending dwell timer
                if sub.duration_seconds and self._dwell_timer:
                    self._dwell_timer.cancel_dwell(
                        sub.subscription_id, device_id
                    )

        return matches

    def evaluate_variable_change(
        self,
        orig_var: Dict[str, Any],
        new_var: Dict[str, Any],
    ) -> List[Tuple[Subscription, Event]]:
        """
        Evaluate all variable subscriptions against a variable change.

        Same transition detection as device evaluation.

        Returns list of (subscription, event) pairs that matched.
        """
        old_value = orig_var.get("value")
        new_value = new_var.get("value")

        # Quick-reject: no value change
        if old_value == new_value:
            return []

        variable_id = new_var.get("id")
        matches = []

        with self._lock:
            var_subs = [
                s for s in self._subscriptions.values()
                if s.entity_type == "variable"
            ]

        for sub in var_subs:
            if sub.entity_id is not None and sub.entity_id != variable_id:
                continue

            new_matches = StateFilter.matches_state(new_var, sub.conditions)
            old_matches = StateFilter.matches_state(orig_var, sub.conditions)

            if new_matches and not old_matches:
                event = self._build_variable_event(orig_var, new_var, sub)

                if sub.duration_seconds and self._dwell_timer:
                    self._dwell_timer.start_dwell(
                        sub, event, sub.duration_seconds, variable_id
                    )
                else:
                    matches.append((sub, event))

            elif not new_matches and old_matches:
                if sub.duration_seconds and self._dwell_timer:
                    self._dwell_timer.cancel_dwell(
                        sub.subscription_id, variable_id
                    )

        return matches

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Cancel all pending dwell timers."""
        if self._dwell_timer:
            self._dwell_timer.cancel_all()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _has_state_changed(
        orig_dev: Dict[str, Any], new_dev: Dict[str, Any]
    ) -> bool:
        """Check if any meaningful state changed between orig and new device."""
        # Indigo's standard top-level state properties (on/off, brightness)
        for key in ("onState", "onOffState", "brightness", "brightnessLevel"):
            if orig_dev.get(key) != new_dev.get(key):
                return True

        # The states dict comparison below catches all custom plugin states
        orig_states = orig_dev.get("states", {})
        new_states = new_dev.get("states", {})
        if orig_states != new_states:
            return True

        return False

    @staticmethod
    def _get_changed_keys(
        orig: Dict[str, Any], new: Dict[str, Any]
    ) -> List[str]:
        """Get list of keys that changed between two entity dicts."""
        changed = []

        # Indigo's standard top-level state properties; the states dict loop below catches custom plugin states
        for key in ("onState", "onOffState", "brightness", "brightnessLevel", "value"):
            if key in new and orig.get(key) != new.get(key):
                changed.append(key)

        # Check states dict
        orig_states = orig.get("states", {})
        new_states = new.get("states", {})
        all_state_keys = set(orig_states.keys()) | set(new_states.keys())
        for key in all_state_keys:
            if orig_states.get(key) != new_states.get(key):
                changed.append(f"states.{key}")

        return changed

    def _build_device_event(
        self,
        orig_dev: Dict[str, Any],
        new_dev: Dict[str, Any],
        sub: Subscription,
    ) -> Event:
        """Build an Event from a device state change that matched a subscription."""
        device_id = new_dev.get("id")
        device_name = new_dev.get("name", "Unknown")
        device_type = new_dev.get("deviceTypeId", "device")
        changed_keys = self._get_changed_keys(orig_dev, new_dev)

        # Build old/new state dicts for changed keys only.
        # Keys from the nested states dict use "states.{key}" naming convention
        # (e.g. "states.sensorValue") to distinguish from top-level properties.
        old_state = {}
        new_state = {}
        for key in changed_keys:
            if key.startswith("states."):
                skey = key[7:]  # strip "states." prefix
                old_state[key] = orig_dev.get("states", {}).get(skey)
                new_state[key] = new_dev.get("states", {}).get(skey)
            else:
                old_state[key] = orig_dev.get(key)
                new_state[key] = new_dev.get(key)

        # Build dedupe key from entity + primary changed state
        primary_key = changed_keys[0] if changed_keys else "unknown"
        primary_val = new_state.get(primary_key, "")
        dedupe_key = f"indigo:device:{device_id}:state:{primary_key}:{primary_val}"

        # Human-readable summary
        summary_parts = []
        for key in changed_keys[:3]:  # Limit to 3 keys for readability
            new_val = new_state.get(key)
            summary_parts.append(f"{key}={new_val}")
        summary_text = ", ".join(summary_parts)

        return Event(
            dedupe_key=dedupe_key,
            event_type="device.state_changed",
            entity={
                "kind": "device",
                "id": device_id,
                "name": device_name,
                "device_type": device_type,
            },
            state={
                "changed_keys": changed_keys,
                "old": old_state,
                "new": new_state,
            },
            trigger={
                "subscription_id": sub.subscription_id,
                "conditions_matched": sub.conditions,
            },
            human={
                "title": f"{device_name} state changed",
                "summary": f"{device_name}: {summary_text}",
            },
        )

    def _build_variable_event(
        self,
        orig_var: Dict[str, Any],
        new_var: Dict[str, Any],
        sub: Subscription,
    ) -> Event:
        """Build an Event from a variable change that matched a subscription."""
        var_id = new_var.get("id")
        var_name = new_var.get("name", "Unknown")
        old_value = orig_var.get("value")
        new_value = new_var.get("value")

        dedupe_key = f"indigo:variable:{var_id}:value:{new_value}"

        return Event(
            dedupe_key=dedupe_key,
            event_type="variable.value_changed",
            entity={
                "kind": "variable",
                "id": var_id,
                "name": var_name,
            },
            state={
                "changed_keys": ["value"],
                "old": {"value": old_value},
                "new": {"value": new_value},
            },
            trigger={
                "subscription_id": sub.subscription_id,
                "conditions_matched": sub.conditions,
            },
            human={
                "title": f"{var_name} value changed",
                "summary": f"{var_name}: {old_value} → {new_value}",
            },
        )
