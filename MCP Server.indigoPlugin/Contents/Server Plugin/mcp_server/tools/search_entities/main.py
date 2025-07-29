"""
Search entities handler for natural language search of Indigo entities.
"""

import logging
from typing import Dict, List, Any, Optional, Set

from ...adapters.data_provider import DataProvider
from ...adapters.vector_store_interface import VectorStoreInterface
from ...common.indigo_device_types import DeviceClassifier
from ..base_handler import BaseToolHandler
from .query_parser import QueryParser
from .result_formatter import ResultFormatter


class SearchEntitiesHandler(BaseToolHandler):
    """Handler for searching Indigo entities with semantic search."""
    
    def __init__(
        self, 
        data_provider: DataProvider,
        vector_store: VectorStoreInterface,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize the search entities handler.
        
        Args:
            data_provider: Data provider for accessing entity data
            vector_store: Vector store instance for semantic search
            logger: Optional logger instance
        """
        super().__init__(tool_name="search_entities", logger=logger)
        self.data_provider = data_provider
        self.vector_store = vector_store
        self.query_parser = QueryParser()
        self.result_formatter = ResultFormatter()
    
    def search(
        self, 
        query: str,
        device_types: Optional[List[str]] = None,
        entity_types: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Search for Indigo entities using natural language with optional filtering.
        
        Args:
            query: Natural language search query
            device_types: Optional list of device types to filter by
            entity_types: Optional list of entity types to search
            
        Returns:
            Dictionary with formatted search results
        """
        try:
            # Log query and parameters
            self.info_log(f"Search query: '{query}'")
            if device_types:
                self.info_log(f"Device type filter: {device_types}")
            if entity_types:
                self.info_log(f"Entity type filter: {entity_types}")
            
            # Parse query to determine search parameters
            search_params = self.query_parser.parse(query, device_types, entity_types)
            self.debug_log(f"Search parameters: {search_params}")
            
            # Perform vector search
            raw_results = self.vector_store.search(
                query=query,
                entity_types=search_params["entity_types"],
                top_k=search_params["top_k"],
                similarity_threshold=search_params["threshold"]
            )
            
            # Apply device type filtering if specified
            if device_types is not None and "devices" in search_params["entity_types"]:
                raw_results = self._filter_devices_by_type(raw_results, device_types)
            
            # Group results by entity type
            grouped_results = self._group_results_by_type(raw_results)
            
            # Log result counts
            self._log_search_results(grouped_results)
            
            # Format results
            formatted_results = self.result_formatter.format_search_results(grouped_results, query)
            
            self.info_log(f"Total results returned: {formatted_results['total_count']}")
            return formatted_results
            
        except Exception as e:
            return self.handle_exception(e, f"searching for '{query}'")
    
    def _group_results_by_type(self, raw_results: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Group search results by entity type.
        
        Args:
            raw_results: Flat list of search results from vector store
            
        Returns:
            Dictionary with entity types as keys and lists of entities as values
        """
        grouped = {
            "devices": [],
            "variables": [],
            "actions": []
        }
        
        for result in raw_results:
            # Extract entity type from result
            entity_type = result.pop("_entity_type", "")
            
            # Map singular to plural
            if entity_type == "device":
                grouped["devices"].append(result)
            elif entity_type == "variable":
                grouped["variables"].append(result)
            elif entity_type == "action":
                grouped["actions"].append(result)
            else:
                # Log unknown entity type but don't fail
                self.warning_log(f"Unknown entity type: {entity_type}")
        
        return grouped
    
    def _filter_devices_by_type(self, raw_results: List[Dict[str, Any]], device_types: List[str]) -> List[Dict[str, Any]]:
        """
        Filter device results by device type.
        
        Args:
            raw_results: Raw search results from vector store
            device_types: List of device types to filter by
            
        Returns:
            Filtered results containing only devices matching the specified types
        """
        filtered_results = []
        device_type_set = set(device_types)
        
        for result in raw_results:
            # Only filter device entities
            if result.get("_entity_type") == "device":
                # Use the classifier to determine the logical device type
                classified_type = DeviceClassifier.classify_device(result)
                if classified_type in device_type_set:
                    filtered_results.append(result)
            else:
                # Keep non-device entities unchanged
                filtered_results.append(result)
        
        return filtered_results
    
    def _log_search_results(self, grouped_results: Dict[str, List[Dict[str, Any]]]) -> None:
        """
        Log search result counts by entity type.
        
        Args:
            grouped_results: Results grouped by entity type
        """
        for entity_type, entities in grouped_results.items():
            count = len(entities)
            if count > 0:
                # Get entity names for logging (up to 10)
                names = [entity.get("name", entity.get("id", "unknown")) for entity in entities]
                names_for_log = names[:10]
                more_text = f" (and {count - 10} more)" if count > 10 else ""
                
                self.info_log(f"Found {count} {entity_type}: {', '.join(names_for_log)}{more_text}")
