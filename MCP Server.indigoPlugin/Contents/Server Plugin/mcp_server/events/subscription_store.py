"""
On-disk persistence for event subscriptions.

Subscriptions otherwise live only in memory and are lost on every plugin
restart. This store saves them to an atomic JSON file and reloads them on
startup so they survive restarts, crashes, and Indigo upgrades.

Pure, stdlib-only (`json`/`os`/`tempfile`) — no Indigo imports — so it is
unit-testable in isolation. The file contains webhook auth tokens (it must, or
authenticated webhooks could not re-authenticate after a restart), so it is
written with `0600` permissions inside Indigo's protected app-support directory.
"""

import json
import logging
import os
import tempfile
from typing import List, Optional

from .subscription_model import Subscription

# Bump when the on-disk schema changes in a non-backward-compatible way.
SCHEMA_VERSION = 1


class SubscriptionStore:
    """Loads/saves subscriptions to a single JSON file (atomic, 0600)."""

    def __init__(self, path: str, logger: Optional[logging.Logger] = None):
        self._path = path
        self._logger = logger or logging.getLogger(__name__)

    def load(self) -> List[Subscription]:
        """
        Load persisted subscriptions.

        Returns an empty list if the file does not exist. A corrupt/unreadable
        file is backed up to ``<path>.corrupt`` and an empty list is returned —
        a bad file must never prevent the plugin from starting.
        """
        if not os.path.exists(self._path):
            return []

        try:
            with open(self._path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, ValueError) as e:
            self._logger.error(
                f"❌ Event subscriptions file is unreadable ({e}) — "
                f"backed it up and starting with none"
            )
            self._backup_corrupt()
            return []

        version = payload.get("version")
        if version != SCHEMA_VERSION:
            self._logger.warning(
                f"⚠️ Event subscriptions file is from a different plugin version "
                f"({version!r} vs {SCHEMA_VERSION}) — loading best-effort"
            )

        subscriptions = []
        for record in payload.get("subscriptions", []):
            try:
                subscriptions.append(Subscription.from_dict(record))
            except Exception as e:
                self._logger.error(f"❌ Skipping an unreadable event subscription record: {e}")
        return subscriptions

    def save(self, subscriptions: List[Subscription]) -> None:
        """
        Atomically persist the given subscriptions (tokens included).

        Writes to a temp file in the same directory, chmods it 0600, then
        os.replace()s it into place so a reader never sees a partial file.
        """
        directory = os.path.dirname(self._path) or "."
        os.makedirs(directory, exist_ok=True)

        payload = {
            "version": SCHEMA_VERSION,
            "subscriptions": [s.to_dict(include_token=True) for s in subscriptions],
        }

        fd, tmp_path = tempfile.mkstemp(
            prefix=".subscriptions-", suffix=".tmp", dir=directory
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            os.chmod(tmp_path, 0o600)
            os.replace(tmp_path, self._path)
        except Exception:
            # Don't leave a stray temp file behind on failure.
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise

    def _backup_corrupt(self) -> None:
        """Rename a corrupt file to <path>.corrupt so the next save starts clean."""
        try:
            os.replace(self._path, self._path + ".corrupt")
        except OSError as e:
            self._logger.error(f"❌ Could not back up the corrupt subscriptions file: {e}")
