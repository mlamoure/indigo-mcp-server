"""
Search entities handler for natural language search of Indigo entities.
"""

import logging
from typing import Dict, List, Any, Optional

from ..adapters.data_provider import DataProvider
from ..adapters.vector_store_interface import VectorStoreInterface
from .query_parser import QueryParser
from .result_formatter import ResultFormatter


class SearchEntitiesHandler:
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
        self.data_provider = data_provider
        self.vector_store = vector_store
        self.logger = logger or logging.getLogger("Plugin")
        self.query_parser = QueryParser()
        self.result_formatter = ResultFormatter()
    
    def search(self, query: str) -> Dict[str, Any]:
        """
        Search for Indigo entities using natural language.
        
        Args:
            query: Natural language search query
            
        Returns:
            Dictionary with formatted search results
        """
        try:
            self.logger.debug(f"Processing search query: {query}")
            
            # Parse query to determine search parameters
            search_params = self.query_parser.parse(query)
            self.logger.debug(f"Search parameters: {search_params}")
            
            # Perform vector search
            raw_results = self.vector_store.search(
                query=query,
                entity_types=search_params["entity_types"],
                top_k=search_params["top_k"],
                similarity_threshold=search_params["threshold"]
            )
            
            # Group results by entity type
            grouped_results = self._group_results_by_type(raw_results)
            
            # Format results
            formatted_results = self.result_formatter.format_search_results(grouped_results, query)
            
            self.logger.debug(f"Search completed: {formatted_results['total_count']} results")
            return formatted_results
            
        except Exception as e:
            self.logger.error(f"Search failed: {e}")
            return self._create_error_response(query, str(e))
    
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
                self.logger.warning(f"Unknown entity type: {entity_type}")
        
        return grouped
    
    def _create_error_response(self, query: str, error_message: str) -> Dict[str, Any]:
        """Create an error response for failed searches."""
        return {
            "error": error_message,
            "query": query,
            "summary": "Search failed",
            "total_count": 0,
            "results": {
                "devices": [],
                "variables": [],
                "actions": []
            }
        }