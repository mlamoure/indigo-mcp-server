"""
MCP tool handler for event subscription CRUD operations.

Provides create_subscription, list_subscriptions, and delete_subscription
tools for MCP clients to manage webhook event subscriptions.
"""

import logging
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from ..tools.base_handler import BaseToolHandler
from .subscription_manager import SubscriptionManager
from .webhook_dispatcher import WebhookDispatcher


VALID_AUTH_MODES = ("none", "bearer", "hmac")
VALID_ENTITY_TYPES = ("device", "variable")


class SubscriptionHandler(BaseToolHandler):
    """MCP tool handler for event subscription management."""

    def __init__(
        self,
        subscription_manager: SubscriptionManager,
        webhook_dispatcher: WebhookDispatcher,
        logger: Optional[logging.Logger] = None,
    ):
        super().__init__(tool_name="event_subscription", logger=logger)
        self.subscription_manager = subscription_manager
        self.webhook_dispatcher = webhook_dispatcher

    # ------------------------------------------------------------------
    # create_event_subscription
    # ------------------------------------------------------------------

    def create_subscription(self, **kwargs) -> Dict[str, Any]:
        """
        Create a new event subscription.

        Required: webhook_url, entity_type, conditions
        Optional: auth, entity_id, duration_seconds, description
        """
        try:
            # Validate required params
            validation = self.validate_required_params(
                kwargs, ["webhook_url", "entity_type", "conditions"]
            )
            if validation:
                return validation

            webhook_url = kwargs["webhook_url"]
            entity_type = kwargs["entity_type"]
            conditions = kwargs["conditions"]

            # Validate webhook URL
            url_error = self._validate_url(webhook_url)
            if url_error:
                return {"error": url_error, "success": False}

            # Validate entity type
            if entity_type not in VALID_ENTITY_TYPES:
                return {
                    "error": f"Invalid entity_type '{entity_type}'. "
                             f"Must be one of: {', '.join(VALID_ENTITY_TYPES)}",
                    "success": False,
                }

            # Validate conditions is a dict
            if not isinstance(conditions, dict) or not conditions:
                return {
                    "error": "conditions must be a non-empty dictionary of state conditions",
                    "success": False,
                }

            # Parse auth config
            auth = kwargs.get("auth", {}) or {}
            auth_mode = auth.get("mode", "none") if isinstance(auth, dict) else "none"
            auth_token = auth.get("token", "") if isinstance(auth, dict) else ""
            verify_ssl = auth.get("verify_ssl", True) if isinstance(auth, dict) else True

            if auth_mode not in VALID_AUTH_MODES:
                return {
                    "error": f"Invalid auth mode '{auth_mode}'. "
                             f"Must be one of: {', '.join(VALID_AUTH_MODES)}",
                    "success": False,
                }

            if auth_mode in ("bearer", "hmac") and not auth_token:
                return {
                    "error": f"Auth mode '{auth_mode}' requires a token",
                    "success": False,
                }

            # Optional params
            entity_id = kwargs.get("entity_id")
            if entity_id is not None:
                entity_id = int(entity_id)

            duration_seconds = kwargs.get("duration_seconds")
            if duration_seconds is not None:
                duration_seconds = int(duration_seconds)
                if duration_seconds < 1:
                    return {
                        "error": "duration_seconds must be at least 1",
                        "success": False,
                    }

            description = kwargs.get("description", "")

            # Create the subscription
            sub = self.subscription_manager.create(
                webhook_url=webhook_url,
                entity_type=entity_type,
                conditions=conditions,
                auth_mode=auth_mode,
                auth_token=auth_token,
                verify_ssl=verify_ssl,
                entity_id=entity_id,
                duration_seconds=duration_seconds,
                description=description,
            )

            return self.create_success_response(
                data=sub.to_dict(),
                message=f"Subscription {sub.subscription_id} created",
            )

        except Exception as e:
            return self.handle_exception(e, "create_subscription")

    # ------------------------------------------------------------------
    # list_event_subscriptions
    # ------------------------------------------------------------------

    def list_subscriptions(self, **kwargs) -> Dict[str, Any]:
        """
        List all active subscriptions, or get a single one by ID.

        Optional: subscription_id
        """
        try:
            subscription_id = kwargs.get("subscription_id")

            if subscription_id:
                sub = self.subscription_manager.get(subscription_id)
                if sub is None:
                    return {
                        "error": f"Subscription '{subscription_id}' not found",
                        "success": False,
                    }
                return self.create_success_response(
                    data=sub.to_dict(),
                    message=f"Subscription {subscription_id}",
                )

            # List all
            subs = self.subscription_manager.list_all()
            dispatcher_stats = self.webhook_dispatcher.get_stats()

            return self.create_success_response(
                data={
                    "subscriptions": [s.to_dict() for s in subs],
                    "count": len(subs),
                    "dispatcher": dispatcher_stats,
                },
                message=f"{len(subs)} active subscription(s)",
            )

        except Exception as e:
            return self.handle_exception(e, "list_subscriptions")

    # ------------------------------------------------------------------
    # delete_event_subscription
    # ------------------------------------------------------------------

    def delete_subscription(self, **kwargs) -> Dict[str, Any]:
        """
        Delete a subscription by ID.

        Required: subscription_id
        """
        try:
            validation = self.validate_required_params(
                kwargs, ["subscription_id"]
            )
            if validation:
                return validation

            subscription_id = kwargs["subscription_id"]
            deleted = self.subscription_manager.delete(subscription_id)

            if not deleted:
                return {
                    "error": f"Subscription '{subscription_id}' not found",
                    "success": False,
                }

            return self.create_success_response(
                data={"subscription_id": subscription_id, "deleted": True},
                message=f"Subscription {subscription_id} deleted",
            )

        except Exception as e:
            return self.handle_exception(e, "delete_subscription")

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_url(url: str) -> Optional[str]:
        """Validate a webhook URL. Returns error string or None."""
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return f"Invalid URL scheme '{parsed.scheme}'. Must be http or https."
            if not parsed.netloc:
                return "Invalid URL: missing hostname"
            return None
        except Exception:
            return f"Invalid URL: {url}"
