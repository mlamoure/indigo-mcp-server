"""
Optimized IndigoQueryAgent with improved performance, modularity, and maintainability.
Uses specialized components for caching, search strategies, and item processing.
"""

import asyncio
import os
import threading
from typing import List, Optional, Dict, Any

from pydantic import BaseModel

from hello_indigo_api.agents.common.agent_base import BaseAgent
from hello_indigo_api.agents.common.agent_decorator import agent
from hello_indigo_api.agents.common.agent_types import (
    AgentGraphState,
    IndigoItems,
    IndigoChatQuestion,
)
from hello_indigo_api.agents.common.openai_client import (
    perform_completion,
    select_optimal_model,
)
from hello_indigo_api.agents.common.prompting import AllItemsMode
# Import MemoryAgent for memory search integration
from hello_indigo_api.agents.utility_agents.memory_agent.main import MemoryAgent
from hello_indigo_api.lance_database import LanceDBManager
# Import optimized components
from .cache_manager import IndigoItemsCache
from .exceptions import (
    CacheInitializationError,
    ItemDetailsFetchError,
    DatabaseError,
)
from ...tools.tools_indigo import (
    KEYS_TO_KEEP_MINIMAL_DEVICES,
)


class RecommendRelevantItemsResponse(BaseModel):
    """Response model for LLM recommendations of additional relevant items."""
    recommended_device_ids: List[str] = []
    recommended_variable_ids: List[str] = []
    recommended_action_ids: List[str] = []
    reasoning: str


@agent
class IndigoQueryAgent(BaseAgent):
    """
    Optimized agent for gathering home automation data relevant to the user's question.

    Key optimizations:
    - High-performance caching with indexed lookups
    - Modular search strategies (device class, vector search, LLM recommendations)
    - Unified item processing to eliminate code duplication
    - Parallel API calls and concurrent search execution
    - Comprehensive metrics and monitoring

    SUPERVISOR GUIDELINES:
    - Call this agent to gather home automation data (devices, variables, actions) from the Indigo system
    - This should typically be called after inspect_question_agent has analyzed the question
    - This agent collects all home automation inventory and finds relevant items based on the question
    - Typical workflow: inspect_question_agent → indigo_query_agent → data_sufficiency_agent → final_answer_agent
    - This agent is essential for questions that require device information or status
    """

    # Class-level cache instance (shared across all instances)
    _cache: Optional[IndigoItemsCache] = None
    _cache_lock = threading.RLock()

    def __init__(self, name: str = "Indigo Query Agent", logger_name: str = "Plugin"):
        super().__init__(name, logger_name)

        # Initialize optimized components
        # Note: ItemProcessor functionality is now integrated into this class

        # Initialize MemoryAgent for memory search integration
        self.memory_agent = MemoryAgent(name="memory_utility", logger_name=logger_name)

        # Initialize vector database
        self._lance_db = self._init_lance_db()

        # Initialize shared cache before property map creation
        # WHY: Property map depends on cached items for initialization
        self._init_shared_cache()

        # Property map management (per instance)
        # Property map management for efficient property name compression
        # WHY: Reduces payload size by replacing long property names with short IDs
        self._property_map_lock = threading.RLock()
        self._property_map = self._create_property_map()
        # Reverse map for O(1) property name to ID lookups
        self._reverse_property_map = {v: k for k, v in self._property_map.items()}
        self._next_property_id = len(self._property_map) + 1

    def _init_lance_db(self) -> Optional[LanceDBManager]:
        """Initialize LanceDB with graceful error handling."""
        lance_db_path = os.environ.get(
            "LANCE_DATABASE_LOCATION", os.environ.get("VECTOR_DB_FILE")
        )
        if not lance_db_path:
            # Vector DB is optional - agent can still function with API-only mode
            self.logger.warning(
                "⚠️ LANCE_DATABASE_LOCATION or VECTOR_DB_FILE not set - vector search disabled"
            )
            return None

        try:
            lance_db = LanceDBManager.get_instance(lance_db_path)
            return lance_db
        except Exception as e:
            # Non-critical failure - agent can operate without vector search
            self.logger.warning(
                f"⚠️ Vector database setup failed: {str(e)} - continuing without vector search"
            )
            return None

    def _init_shared_cache(self) -> None:
        """Initialize shared cache instance."""
        with self._cache_lock:
            if self._cache is None:
                try:
                    self._cache = IndigoItemsCache(
                        refresh_interval=300,  # 5 minutes - balances freshness vs API load
                        logger_name=self.logger.name,
                        lance_db=self._lance_db,
                    )
                except Exception as e:
                    self.logger.error(f"❌ Cache initialization failed: {str(e)}")
                    raise CacheInitializationError(
                        f"Failed to initialize cache: {str(e)}"
                    ) from e

    @classmethod
    def shutdown_cache(cls) -> None:
        """Shutdown shared cache (useful for cleanup)."""
        with cls._cache_lock:
            if cls._cache:
                cls._cache.shutdown()
                cls._cache = None

    async def search_by_device_type(self, question: IndigoChatQuestion) -> IndigoItems:
        all_items = self._cache.get_items()

        device_class = question.question_properties.question_device_class

        # Handle special cases
        if device_class == "none":
            self.logger.debug("🔍 Device class 'none' - returning empty results")
            return IndigoItems(devices=[], variables=[], actions=[])

        if device_class == "all":
            self.logger.debug("🔍 Device class 'all' - returning all devices")
            return IndigoItems(devices=all_items.devices, variables=[], actions=[])

        # Convert device class to list for consistent processing
        if hasattr(device_class, "value"):  # Enum type
            device_classes = [device_class.value]
        elif isinstance(device_class, list):
            device_classes = [
                dc.value if hasattr(dc, "value") else dc for dc in device_class
            ]
        elif isinstance(device_class, str):
            device_classes = [device_class]
        else:
            self.logger.warning(f"❌ Invalid device_class type: {type(device_class)}")
            return IndigoItems(devices=[], variables=[], actions=[])

        # Filter devices by class
        filtered_devices = self._filter_by_device_class(
            all_items.devices, device_classes
        )

        # Add logging for filtered devices
        device_count = len(filtered_devices)
        if device_count > 0:
            # Get device names for logging
            device_names = [
                d.get("name", d.get("id", "unknown")) for d in filtered_devices
            ]

            # Info log: count + up to 10 device names
            names_for_info = device_names[:10]
            more_text = f" (and {device_count - 10} more)" if device_count > 10 else ""
            self.info_update(
                f"🔍 Found {device_count} devices matching class '{', '.join(device_classes)}': {', '.join(names_for_info)}{more_text}"
            )

            # Debug log: all device names
            self._debug_log(
                f"🔍 All {device_count} devices matching class '{', '.join(device_classes)}': {', '.join(device_names)}"
            )
        else:
            self.info_update(
                f"🔍 No devices found matching class '{', '.join(device_classes)}'"
            )

        result_items = IndigoItems(devices=filtered_devices, variables=[], actions=[])

        return result_items

    async def search_by_name(
        self,
        question: IndigoChatQuestion,
    ) -> IndigoItems:
        self.logger.debug("🔍 Starting search_by_name function")

        # Check if database is available
        if not self._lance_db or not self._lance_db.is_available():
            # Vector search is optional - return empty results gracefully
            self.logger.warning("⚠️ Vector database not available for semantic search")
            self.logger.debug(
                "search_by_name returning empty results - database unavailable"
            )
            return IndigoItems(devices=[], variables=[], actions=[])

        # Use question keywords if available, otherwise fall back to question text
        if question.question_properties.question_keywords:
            # Combine keywords into a search string
            search_text = " ".join(question.question_properties.question_keywords)
            self.logger.debug(
                f"🔍 Using keywords for search: {question.question_properties.question_keywords}"
            )
        else:
            search_text = question.question_text
            self.logger.debug(
                f"🔍 No keywords found, using question text: '{search_text}'"
            )

        # Low similarity threshold to catch potentially relevant items
        # WHY: 0.15 allows fuzzy matches while filtering obvious non-matches
        similarity_threshold = 0.15
        # Limit results to prevent overwhelming downstream processing
        top_k = 20
        self.logger.debug(
            f"🔍 Search parameters - threshold: {similarity_threshold}, top_k: {top_k}"
        )

        search_results = {"devices": [], "variables": [], "actions": []}
        total_items = 0

        for field in ["devices", "variables", "actions"]:
            self.logger.debug(f"🔍 Searching in collection: {field}")

            try:
                # Get best matches for debugging (threshold=0 shows all similarities)
                all_matches = self._lance_db.search_home_automation_items(
                    query_text=search_text,
                    collection_name=field,
                    top_k=top_k,
                    similarity_threshold=0.0,
                )
            except Exception as e:
                self.logger.error(f"❌ Vector search failed for {field}: {e}")
                continue  # Skip this collection on error

            # Log top matches for debugging (regardless of threshold)
            if all_matches:
                self.logger.debug(
                    f"🔍 Top {min(5, len(all_matches))} nearest matches in {field} (regardless of threshold):"
                )
                for i, item in enumerate(all_matches[:5]):
                    score = item.get("similarity_score", "N/A")
                    name = item.get("name", "Unknown")
                    self.logger.debug(f"🔍   {field}[{i}]: '{name}' score={score}")
            else:
                self.logger.debug(f"🔍 No items found in {field} collection")

            try:
                # Now get items that meet the threshold
                similar_items = self._lance_db.search_home_automation_items(
                    query_text=search_text,
                    collection_name=field,
                    top_k=top_k,
                    similarity_threshold=similarity_threshold,
                )
            except Exception as e:
                self.logger.error(
                    f"❌ Vector search with threshold failed for {field}: {e}"
                )
                continue  # Skip this collection on error

            self.logger.debug(
                f"🔍 Raw search results for {field}: {len(similar_items)} items above threshold {similarity_threshold}"
            )

            # Convert to expected format
            search_results[field] = [
                {
                    "id": item["id"],
                    "name": item["name"],
                    "text": item["text"],
                }
                for item in similar_items
            ]

            field_count = len(search_results[field])
            total_items += field_count
            self.logger.debug(
                f"🔍 Converted {field_count} {field} items to expected format"
            )

        result_items = IndigoItems(**search_results)

        self.logger.debug(
            f"🔍 search_by_name complete - returning {len(result_items.devices)} devices, {len(result_items.variables)} variables, {len(result_items.actions)} actions"
        )
        self._debug_log(
            f"🔍 Vector search found {total_items} items "
            f"(threshold: {similarity_threshold}, top_k: {top_k})"
        )

        # Log if keywords were used
        if question.question_properties.question_keywords:
            self.info_update(
                f"🔍 Search using keywords found {total_items} items "
                f"(keywords: {', '.join(question.question_properties.question_keywords[:5])}...)"
            )

        return result_items

    async def _get_llm_recommendations(
        self,
        state: AgentGraphState,
        data_sufficiency_analysis: dict,
    ) -> IndigoItems:
        """
        Get LLM recommendations for additional relevant items based on data sufficiency analysis.
        
        Args:
            state: Current agent graph state
            data_sufficiency_analysis: Analysis from data sufficiency agent
            
        Returns:
            IndigoItems containing recommended items to fetch
        """
        try:
            # Build messages using standardized prompting with insufficiency info
            prompt_messages = self.build_standardized_messages(
                state=state,
                instructions_template="recommend_relevant_items_instructions.jinja2",
                agent_role="recommend additional home automation items to collect based on data sufficiency analysis",
                all_items_mode=AllItemsMode.SAMPLE,  # Use sample mode to reduce token count
                current_task="Recommend additional relevant items to address data insufficiency",
                insufficiency_info=data_sufficiency_analysis,
            )

            # Select optimal model based on token count
            optimal_model = select_optimal_model(prompt_messages)

            self.info_update(
                f"Getting LLM recommendations for additional relevant items ({optimal_model})"
            )

            # Request recommendations from LLM
            response = perform_completion(
                messages=prompt_messages,
                response_model=RecommendRelevantItemsResponse,
                model=optimal_model,
                config=self.get_current_config(),
            )

            # Convert response to IndigoItems
            recommended_items = IndigoItems(
                devices=[{"id": device_id} for device_id in response.recommended_device_ids],
                variables=[{"id": var_id} for var_id in response.recommended_variable_ids],
                actions=[{"id": action_id} for action_id in response.recommended_action_ids],
            )

            # Log recommendations
            total_recommendations = (
                len(response.recommended_device_ids)
                + len(response.recommended_variable_ids)
                + len(response.recommended_action_ids)
            )
            
            if total_recommendations > 0:
                self.info_update(
                    f"LLM recommended {len(response.recommended_device_ids)} devices, "
                    f"{len(response.recommended_variable_ids)} variables, "
                    f"{len(response.recommended_action_ids)} actions. "
                    f"Reason: {response.reasoning}"
                )
            else:
                self.info_update("LLM did not recommend any additional items")

            return recommended_items

        except Exception as e:
            # LLM recommendations are optional - log error and continue
            self.logger.warning(f"⚠️ Failed to get LLM recommendations: {e}")
            return IndigoItems(devices=[], variables=[], actions=[])

    async def _fetch_fresh_item_data(self, items: IndigoItems) -> IndigoItems:
        """Fetch fresh data for items using cache manager's optimized refresh"""
        # Extract item IDs
        device_ids = [device.get("id") for device in items.devices if device.get("id")]
        variable_ids = [
            variable.get("id") for variable in items.variables if variable.get("id")
        ]
        action_ids = [action.get("id") for action in items.actions if action.get("id")]

        # Trigger cache refresh to get latest data from Indigo API
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, self._cache.refresh_now
            )
        except Exception as e:
            # Cache refresh failure is non-critical - return stale data
            self.logger.warning(f"⚠️ Cache refresh failed, using stale data: {e}")
            return items

        # Use cache's optimized batch lookups to get fresh data
        fresh_items = IndigoItems(devices=[], variables=[], actions=[])

        if device_ids:
            fresh_items.devices = self._cache.get_devices_by_ids(device_ids)

        if variable_ids:
            fresh_items.variables = self._cache.get_variables_by_ids(variable_ids)

        if action_ids:
            fresh_items.actions = self._cache.get_actions_by_ids(action_ids)

        # Process device properties for fresh devices
        if fresh_items.devices:
            fresh_items.devices = self._process_device_properties(fresh_items.devices)

        # Deduplicate items (cache should already provide unique items, but keep for safety)
        fresh_items.devices = self._deduplicate_items(fresh_items.devices)
        fresh_items.variables = self._deduplicate_items(fresh_items.variables)
        fresh_items.actions = self._deduplicate_items(fresh_items.actions)

        return fresh_items

    async def __call__(self, state: AgentGraphState) -> AgentGraphState:
        """
        Process user question and gather complete details for all relevant home automation items.

        Simplified approach:
        1. If data_sufficiency_analysis exists and indicates insufficient data, get LLM recommendations
        2. Extract items needing fresh data (minimal properties only)
        3. Search for additional relevant items based on question scope
        4. Fetch fresh data directly from Indigo API (devices, variables, actions)
        5. Update relevant_items with complete, up-to-date information
        """
        if not state or "user_question" not in state:
            self.logger.warning("⚠️ Empty state or missing user_question")
            return state

        question = state["user_question"]

        all_items = self._cache.get_items()
        existing_relevant_items = question.relevant_items

        # Step 1: Check if we need LLM recommendations based on data sufficiency
        llm_recommended_items = IndigoItems(devices=[], variables=[], actions=[])
        data_sufficiency_analysis = state.get("data_sufficiency_analysis", {})
        
        if data_sufficiency_analysis and not data_sufficiency_analysis.get("is_sufficient", True):
            # Data is insufficient - get LLM recommendations
            llm_recommended_items = await self._get_llm_recommendations(
                state, data_sufficiency_analysis
            )

        # Step 2: Search for additional relevant items
        if question.question_properties.question_scope.value == "wide":
            search_results = await self.search_by_device_type(question)
        else:
            search_results = await self.search_by_name(question)

        # Step 3: Combine ALL relevant items (existing + LLM recommendations + search results)
        all_relevant_items = IndigoItems(devices=[], variables=[], actions=[])

        # Add existing relevant items
        if (
            existing_relevant_items.devices
            or existing_relevant_items.variables
            or existing_relevant_items.actions
        ):
            self._merge_into_collection(all_relevant_items, existing_relevant_items)

        # Add LLM recommended items
        if llm_recommended_items:
            self._merge_into_collection(all_relevant_items, llm_recommended_items)

        # Add search results
        if search_results:
            self._merge_into_collection(all_relevant_items, search_results)

        # Step 4: Fetch fresh data for ALL relevant items
        new_relevant_items = IndigoItems(devices=[], variables=[], actions=[])
        if (
            all_relevant_items.devices
            or all_relevant_items.variables
            or all_relevant_items.actions
        ):
            new_relevant_items = await self._fetch_fresh_item_data(all_relevant_items)

            # Log summary of relevant items
            total_count = (
                len(new_relevant_items.devices)
                + len(new_relevant_items.variables)
                + len(new_relevant_items.actions)
            )
            if total_count > 0:
                self.info_update(
                    f"Fetched fresh data for {len(new_relevant_items.devices)} devices, "
                    f"{len(new_relevant_items.variables)} variables, "
                    f"{len(new_relevant_items.actions)} actions"
                )

        # Step 5: Fetch memory items
        relevant_memory = []
        try:
            relevant_memory = self.memory_agent.search_relevant_memory(
                user_question=question.question_text, relevant_items=new_relevant_items
            )
        except Exception as e:
            # Memory search is optional - continue without it
            self.logger.warning(f"⚠️ Memory search failed (non-critical): {e}")

        # Step 6: Filter the relevant items out of all items
        filtered_all_items = self._create_filtered_all_items(
            all_items, new_relevant_items
        )

        question.relevant_items = new_relevant_items

        state["user_question"] = question
        state["all_home_automation_items"] = filtered_all_items
        state["device_property_map"] = self._property_map
        state["relevant_memory"] = relevant_memory

        return state

    @staticmethod
    def _create_filtered_all_items(
        all_items: IndigoItems, relevant_items: IndigoItems
    ) -> IndigoItems:
        """Create filtered all_items excluding relevant items (optimized)."""
        # Create sets of relevant IDs for fast lookup
        relevant_device_ids = {d.get("id") for d in relevant_items.devices}
        relevant_variable_ids = {v.get("id") for v in relevant_items.variables}
        relevant_action_ids = {a.get("id") for a in relevant_items.actions}

        # Filter out relevant items from all items
        filtered_devices = [
            d for d in all_items.devices if d.get("id") not in relevant_device_ids
        ]
        filtered_variables = [
            v for v in all_items.variables if v.get("id") not in relevant_variable_ids
        ]
        filtered_actions = [
            a for a in all_items.actions if a.get("id") not in relevant_action_ids
        ]

        return IndigoItems(
            devices=filtered_devices,
            variables=filtered_variables,
            actions=filtered_actions,
        )

    def _process_device_properties(self, devices: List[dict]) -> List[dict]:
        """Process device properties and update contains_properties for the given devices."""
        processed_devices = []

        with self._property_map_lock:
            for device in devices:
                device_id = device.get("id")
                if not device_id:
                    continue

                # Create processed device copy
                processed_device = device.copy()

                # Extract properties efficiently - skip standard fields defined in KEYS_TO_KEEP_MINIMAL_DEVICES
                device_props = [
                    self._get_or_create_property_id(key)
                    for key in device.keys()
                    if key not in KEYS_TO_KEEP_MINIMAL_DEVICES
                ]

                # Store properties directly in device dict
                processed_device["contains_properties"] = device_props
                processed_devices.append(processed_device)

        return processed_devices

    def _get_or_create_property_id(self, property_name: str) -> str:
        """Get existing property ID or create new one.

        WHY: Compresses property names to reduce message size when passing
        device data between agents. "brightnessLevel" -> "p1" saves bytes.
        """
        # Fast path: check reverse lookup cache first
        if property_name in self._reverse_property_map:
            return self._reverse_property_map[property_name]

        # Slow path: scan property map (shouldn't happen after warmup)
        for prop_id, existing_name in self._property_map.items():
            if existing_name == property_name:
                # Update reverse cache for next time
                self._reverse_property_map[property_name] = prop_id
                return prop_id

        # Create new property ID atomically
        prop_id = f"p{self._next_property_id}"
        self._property_map[prop_id] = property_name
        self._reverse_property_map[property_name] = prop_id
        self._next_property_id += 1
        return prop_id

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics for monitoring and debugging."""
        if self._cache:
            # Return basic cache info
            items = self._cache.get_items()
            return {
                "devices_count": len(items.devices),
                "variables_count": len(items.variables),
                "actions_count": len(items.actions),
                "cache_available": True,
            }
        return {"error": "cache_not_initialized"}

    def force_cache_refresh(self) -> None:
        """Force immediate cache refresh."""
        if self._cache:
            # Trigger cache refresh by reinitializing the cache
            try:
                self._cache.shutdown()
                with self._cache_lock:
                    self._cache = IndigoItemsCache(
                        refresh_interval=300,
                        logger_name=self.logger.name,
                        lance_db=self._lance_db,
                    )
                self.info_update("🔄 Manual cache refresh completed")
            except Exception as e:
                self.logger.error(f"❌ Failed to refresh cache: {e}")
                raise ItemDetailsFetchError(f"Cache refresh failed: {e}") from e
        else:
            self.logger.warning("⚠️ Cache not initialized, cannot refresh")

    def __del__(self):
        """Cleanup resources on deletion."""
        # WHY: Shared cache is class-level, not instance-level
        # Other instances may still need it, so cleanup happens via shutdown_cache()
        pass

    def _create_property_map(self) -> Dict[str, str]:
        """Create a mapping of property IDs to property names from all cached devices."""
        device_property_map = {}

        # Check if cache is available
        if not self._cache:
            self.logger.warning("⚠️ Cache not initialized, returning empty property map")
            return device_property_map

        try:
            # Get all devices from cache
            all_items = self._cache.get_items()
            all_devices = all_items.devices

            # Track unique properties across all devices
            unique_properties = set()

            # Collect all unique property names across devices
            # WHY: Pre-building the map avoids thread contention during request processing
            for device in all_devices:
                for key in device.keys():
                    # Skip standard fields present in all devices
                    if key not in KEYS_TO_KEEP_MINIMAL_DEVICES:
                        unique_properties.add(key)

            # Sort properties for deterministic ID assignment across restarts
            # WHY: Consistent IDs help with debugging and log analysis
            property_id = 1
            for prop_name in sorted(unique_properties):
                device_property_map[f"p{property_id}"] = prop_name
                property_id += 1

            self._debug_log(
                f"📋 Created property map with {len(device_property_map)} properties"
            )

        except Exception as e:
            # Property map is critical for operation
            self.logger.error(f"❌ Error creating property map: {str(e)}")
            raise DatabaseError(f"Failed to create property map: {e}") from e

        return device_property_map

    @staticmethod
    def _filter_by_device_class(
        devices: List[dict], device_classes: List[str]
    ) -> List[dict]:
        """Filter devices by device class."""
        if "all" in device_classes:
            return devices
        if "none" in device_classes:
            return []

        filtered = []
        for device in devices:
            device_type = device.get("class", "")
            if device_type in device_classes:
                filtered.append(device)
        return filtered

    @staticmethod
    def _deduplicate_items(items: List[dict]) -> List[dict]:
        """Remove duplicate items based on ID."""
        seen_ids = set()
        deduplicated = []
        for item in items:
            item_id = item.get("id")
            if item_id and item_id not in seen_ids:
                seen_ids.add(item_id)
                deduplicated.append(item)
        return deduplicated

    @staticmethod
    def _merge_into_collection(target: IndigoItems, source: IndigoItems) -> None:
        """Merge source items into target collection, avoiding duplicates."""
        # Get existing IDs
        existing_device_ids = {d.get("id") for d in target.devices}
        existing_variable_ids = {v.get("id") for v in target.variables}
        existing_action_ids = {a.get("id") for a in target.actions}

        # Add non-duplicate items
        for device in source.devices:
            if device.get("id") not in existing_device_ids:
                target.devices.append(device)

        for variable in source.variables:
            if variable.get("id") not in existing_variable_ids:
                target.variables.append(variable)

        for action in source.actions:
            if action.get("id") not in existing_action_ids:
                target.actions.append(action)

    # NOTE: _fetch_item_details method removed - functionality moved to cache manager
    # All item details are now fetched via cache refresh for better performance
