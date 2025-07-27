"""
High-performance caching system for Indigo home automation items.
Optimized for fast lookups and efficient memory usage.
"""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from hello_indigo_api.agents.common.agent_base import BaseAgent
from hello_indigo_api.agents.common.agent_types import IndigoItems
from .exceptions import CacheRefreshError
from hello_indigo_api.agents.tools.tools_indigo import (
    indigo_get_all_house_devices,
    indigo_get_all_house_variables,
    indigo_get_all_house_action_groups,
)


@dataclass
class IndexedItem:
    """Lightweight item representation for fast lookups.
    
    WHY: Storing minimal index data separately from full item data
    allows O(1) lookups without duplicating large device payloads.
    """

    id: int
    name: str
    type_class: str
    data: dict


class ItemIndex:
    """High-performance indexed container for home automation items."""

    def __init__(self):
        self._items_by_id: Dict[int, IndexedItem] = {}
        self._items_by_name: Dict[str, List[IndexedItem]] = {}
        self._ids: Set[int] = set()

    def add_item(self, item_data: dict) -> None:
        """Add item to index with optimized lookups."""
        item_id = item_data.get("id")
        if item_id is None:
            return

        item = IndexedItem(
            id=item_id,
            name=item_data.get("name", ""),
            type_class=item_data.get("class", item_data.get("type", "")),
            data=item_data,
        )

        # Primary index by ID for O(1) lookups
        self._items_by_id[item_id] = item
        self._ids.add(item_id)

        # Secondary index by name for search functionality
        # WHY: Multiple items can share the same name (e.g., "Motion Sensor")
        name_lower = item.name.lower()
        if name_lower not in self._items_by_name:
            self._items_by_name[name_lower] = []
        self._items_by_name[name_lower].append(item)

    def get_by_id(self, item_id: int) -> Optional[dict]:
        """O(1) lookup by ID."""
        item = self._items_by_id.get(item_id)
        return item.data if item else None

    def get_by_ids(self, item_ids: List[int]) -> List[dict]:
        """Batch lookup by IDs with O(n) complexity where n = len(item_ids).
        
        WHY: Batch operations reduce lock contention in multi-threaded scenarios.
        """
        return [
            item.data
            for item_id in item_ids
            if (item := self._items_by_id.get(item_id)) is not None
        ]

    def contains_id(self, item_id: int) -> bool:
        """O(1) ID existence check."""
        return item_id in self._ids

    def get_all_data(self) -> List[dict]:
        """Get all item data."""
        return [item.data for item in self._items_by_id.values()]

    def clear(self) -> None:
        """Clear all indexes."""
        self._items_by_id.clear()
        self._items_by_name.clear()
        self._ids.clear()

    def __len__(self) -> int:
        return len(self._items_by_id)


class IndigoItemsCache(BaseAgent):
    """Thread-safe, high-performance cache for Indigo home automation items."""

    def __init__(self, refresh_interval: int = 300, logger_name: str = "Plugin", lance_db=None):
        super().__init__("indigo_cache", logger_name)
        self.refresh_interval = refresh_interval
        self._lance_db = lance_db

        # Thread-safe indexes
        self._lock = threading.RLock()
        self._devices = ItemIndex()
        self._variables = ItemIndex()
        self._actions = ItemIndex()

        # Cache metadata
        self._last_refresh_time = 0.0
        self._is_refreshing = False
        self._refresh_count = 0

        # Background refresh thread
        self._refresh_thread: Optional[threading.Thread] = None
        self._stop_refresh = threading.Event()

        # Thread pool for parallel API calls
        # WHY: 3 workers = 1 per API endpoint (devices, variables, actions)
        self._executor = ThreadPoolExecutor(
            max_workers=3, thread_name_prefix="indigo-cache"
        )

        # Initialize cache
        self.refresh_now()
        self._start_background_refresh()

    def _start_background_refresh(self) -> None:
        """Start background refresh thread."""
        if self._refresh_thread is None or not self._refresh_thread.is_alive():
            self._stop_refresh.clear()
            self._refresh_thread = threading.Thread(
                target=self._background_refresh_loop,
                daemon=True,
                name="indigo-cache-refresh",
            )
            self._refresh_thread.start()
            self._debug_log("🔄 Background cache refresh thread started")

    def _background_refresh_loop(self) -> None:
        """Background thread that refreshes cache periodically."""
        while not self._stop_refresh.wait(self.refresh_interval):
            try:
                if self._should_refresh():
                    self.refresh_now()
            except Exception as e:
                self._debug_log(f"❌ Background cache refresh failed: {e}", min_level=logging.ERROR)

    def _should_refresh(self) -> bool:
        """Check if cache should be refreshed.
        
        WHY: Prevents redundant refreshes and API overload by checking
        both time elapsed and current refresh status.
        """
        return (
            time.time() - self._last_refresh_time > self.refresh_interval
            and not self._is_refreshing
        )

    def refresh_now(self) -> None:
        """Immediately refresh the cache."""
        with self._lock:
            if self._is_refreshing:
                return  # Already refreshing
            self._is_refreshing = True

        try:
            start_time = time.time()
            self._debug_log("🔄 Starting cache refresh")

            # Parallel API calls reduce total refresh time from 3x to 1x API latency
            # WHY: These API calls are independent and can execute concurrently
            device_future = self._executor.submit(indigo_get_all_house_devices, None)
            variable_future = self._executor.submit(indigo_get_all_house_variables)
            action_future = self._executor.submit(indigo_get_all_house_action_groups)

            # Collect results
            devices_response = device_future.result(timeout=30)
            variables_response = variable_future.result(timeout=30)
            actions_response = action_future.result(timeout=30)

            # Process results in parallel
            with self._lock:
                self._devices.clear()
                self._variables.clear()
                self._actions.clear()

                # Extract and index items
                devices_list = self._extract_items(devices_response, "devices")
                variables_list = self._extract_items(variables_response, "variables")
                actions_list = self._extract_items(actions_response, "actions")

                for device in devices_list:
                    self._devices.add_item(device)

                for variable in variables_list:
                    self._variables.add_item(variable)

                for action in actions_list:
                    self._actions.add_item(action)

                self._last_refresh_time = time.time()
                self._refresh_count += 1

            elapsed = time.time() - start_time
            self._debug_log(
                f"✅ Cache refreshed in {elapsed:.2f}s: "
                f"{len(self._devices)} devices, {len(self._variables)} variables, "
                f"{len(self._actions)} actions (refresh #{self._refresh_count})"
            )
            
            # Update vector store with fresh data
            self._update_vector_store(devices_response, variables_response, actions_response)

        except Exception as e:
            self._debug_log(f"❌ Cache refresh failed: {e}", min_level=logging.ERROR)
            raise CacheRefreshError(f"Failed to refresh cache: {e}") from e
        finally:
            self._is_refreshing = False

    def _update_vector_store(self, devices_response, variables_response, actions_response):
        """Update the vector store with fresh data from API responses."""
        if not self._lance_db:
            self._debug_log("🔍 No LanceDB instance available, skipping vector store update")
            return
            
        try:
            vector_start_time = time.time()
            
            # Update each collection in the vector store
            collections = [
                ("devices", devices_response),
                ("variables", variables_response), 
                ("actions", actions_response)
            ]
            
            for collection_name, response_data in collections:
                try:
                    self._lance_db.load_embeddings_to_vector_store(response_data, collection_name)
                    self._debug_log(f"✅ Updated {collection_name} vector embeddings")
                except Exception as e:
                    self._debug_log(f"❌ Failed to update {collection_name} vector embeddings: {e}", min_level=logging.ERROR)
            
            vector_elapsed = time.time() - vector_start_time
            self._debug_log(f"🔍 Vector store updated in {vector_elapsed:.2f}s")
            
        except Exception as e:
            self._debug_log(f"❌ Vector store update failed: {e}", min_level=logging.ERROR)

    def _extract_items(self, response: dict, item_type: str) -> List[dict]:
        """Extract items from API response with flexible format handling.
        
        WHY: Indigo API responses vary in structure - sometimes wrapped
        in {"data": [...]} or {"devices": [...]}, sometimes raw lists.
        """
        if isinstance(response, dict):
            # Try common response wrapper keys in priority order
            for key in ["devices", "data", "variables", "actionGroups"]:
                if key in response and isinstance(response[key], list):
                    return response[key]
            return []
        elif isinstance(response, list):
            return response
        return []

    def get_items(self) -> IndigoItems:
        """Get current cached items as IndigoItems object."""
        with self._lock:
            return IndigoItems(
                devices=self._devices.get_all_data(),
                variables=self._variables.get_all_data(),
                actions=self._actions.get_all_data(),
            )

    def get_device_by_id(self, device_id: int) -> Optional[dict]:
        """Fast O(1) device lookup by ID."""
        with self._lock:
            return self._devices.get_by_id(device_id)

    def get_variable_by_id(self, variable_id: int) -> Optional[dict]:
        """Fast O(1) variable lookup by ID."""
        with self._lock:
            return self._variables.get_by_id(variable_id)

    def get_action_by_id(self, action_id: int) -> Optional[dict]:
        """Fast O(1) action lookup by ID."""
        with self._lock:
            return self._actions.get_by_id(action_id)

    def get_devices_by_ids(self, device_ids: List[int]) -> List[dict]:
        """Fast batch device lookup by IDs."""
        with self._lock:
            return self._devices.get_by_ids(device_ids)

    def get_variables_by_ids(self, variable_ids: List[int]) -> List[dict]:
        """Fast batch variable lookup by IDs."""
        with self._lock:
            return self._variables.get_by_ids(variable_ids)

    def get_actions_by_ids(self, action_ids: List[int]) -> List[dict]:
        """Fast batch action lookup by IDs."""
        with self._lock:
            return self._actions.get_by_ids(action_ids)

    def contains_device_id(self, device_id: int) -> bool:
        """Fast O(1) check if device ID exists."""
        with self._lock:
            return self._devices.contains_id(device_id)

    def contains_variable_id(self, variable_id: int) -> bool:
        """Fast O(1) check if variable ID exists."""
        with self._lock:
            return self._variables.contains_id(variable_id)

    def contains_action_id(self, action_id: int) -> bool:
        """Fast O(1) check if action ID exists."""
        with self._lock:
            return self._actions.contains_id(action_id)

    def shutdown(self) -> None:
        """Shutdown cache and cleanup resources."""
        self._debug_log("🔄 Shutting down cache...")
        self._stop_refresh.set()

        if self._refresh_thread and self._refresh_thread.is_alive():
            self._refresh_thread.join(timeout=2)

        self._executor.shutdown(wait=True)

        with self._lock:
            self._devices.clear()
            self._variables.clear()
            self._actions.clear()

    def __del__(self):
        """Cleanup on deletion."""
        try:
            self.shutdown()
        except:
            # WHY: During interpreter shutdown, logging may be unavailable
            # Suppress errors to avoid confusing error messages at exit
            pass
