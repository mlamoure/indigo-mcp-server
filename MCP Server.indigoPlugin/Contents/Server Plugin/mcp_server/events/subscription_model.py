"""
Subscription model for event webhook subscriptions.

Each subscription defines: what to watch (entity + conditions),
where to notify (webhook URL + auth), and tracks delivery health.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .event_model import generate_ulid


def _default_stats() -> Dict[str, Any]:
    """Default delivery health stats for a new subscription."""
    return {
        "fires": 0,
        "last_fired_at": None,
        "last_success_at": None,
        "last_failure_at": None,
        "last_http_status": None,
        "consecutive_failures": 0,
        "errors": 0,
        "last_error": None,
    }


@dataclass
class Subscription:
    """
    A webhook subscription created by an MCP client.

    Defines what entity/state conditions to watch and where to POST events.
    """

    # Identity
    subscription_id: str = field(default_factory=generate_ulid)

    # Webhook target
    webhook_url: str = ""
    auth_mode: str = "none"  # "none", "bearer", "hmac"
    auth_token: str = ""
    verify_ssl: bool = True

    # What to watch
    entity_type: str = ""  # "device" or "variable"
    entity_id: Optional[int] = None  # Specific entity, or None for all of type
    conditions: Dict[str, Any] = field(default_factory=dict)  # StateFilter-compatible

    # Dwell-time (optional)
    duration_seconds: Optional[int] = None  # If set, condition must hold for this long

    # Metadata
    description: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # Delivery health
    stats: Dict[str, Any] = field(default_factory=_default_stats)

    def to_dict(self, include_token: bool = False) -> Dict[str, Any]:
        """
        Serialize to a plain dict.

        Args:
            include_token: If False, redacts auth_token for safe display.
        """
        if include_token:
            token_value = self.auth_token
        elif self.auth_token:
            token_value = "***"
        else:
            token_value = ""

        result = {
            "subscription_id": self.subscription_id,
            "webhook_url": self.webhook_url,
            "auth_mode": self.auth_mode,
            "auth_token": token_value,
            "verify_ssl": self.verify_ssl,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "conditions": self.conditions,
            "duration_seconds": self.duration_seconds,
            "description": self.description,
            "created_at": self.created_at,
            "stats": dict(self.stats),
        }
        return result

    def record_success(self, http_status: int) -> None:
        """Record a successful webhook delivery."""
        now = datetime.now(timezone.utc).isoformat()
        self.stats["fires"] += 1
        self.stats["last_fired_at"] = now
        self.stats["last_success_at"] = now
        self.stats["last_http_status"] = http_status
        self.stats["consecutive_failures"] = 0

    def record_failure(self, error: str, http_status: Optional[int] = None) -> None:
        """Record a failed webhook delivery."""
        now = datetime.now(timezone.utc).isoformat()
        self.stats["fires"] += 1
        self.stats["last_fired_at"] = now
        self.stats["last_failure_at"] = now
        self.stats["errors"] += 1
        self.stats["consecutive_failures"] += 1
        self.stats["last_error"] = error
        if http_status is not None:
            self.stats["last_http_status"] = http_status
