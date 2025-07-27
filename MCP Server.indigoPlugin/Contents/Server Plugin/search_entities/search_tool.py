"""
MCP search tool for finding Indigo entities using natural language queries.
"""

import logging
from typing import Dict, List, Any, Optional


class SearchEntitiesTool:
    """Tool for searching Indigo entities with semantic search."""
    
    def __init__(self, vector_store, logger: Optional[logging.Logger] = None):
        """
        Initialize the search tool.
        
        Args:
            vector_store: Vector store instance for semantic search
            logger: Optional logger instance
        """
        self.vector_store = vector_store
        self.logger = logger or logging.getLogger(__name__)
    
    def search(self, query: str) -> Dict[str, Any]:
        """
        Search for Indigo entities using natural language.
        
        Args:
            query: Natural language search query
            
        Returns:
            Dictionary with search results
        """
        try:
            # Parse query to determine search parameters
            search_params = self._parse_query(query)
            
            # Perform vector search
            results = self.vector_store.search(
                query=query,
                entity_types=search_params["entity_types"],
                top_k=search_params["top_k"],
                similarity_threshold=search_params["threshold"]
            )
            
            # Format results
            formatted_results = self._format_results(results, query)
            
            return formatted_results
            
        except Exception as e:
            self.logger.error(f"Search failed: {e}")
            return {
                "error": str(e),
                "query": query,
                "results": {
                    "devices": [],
                    "variables": [],
                    "actions": []
                }
            }
    
    def _parse_query(self, query: str) -> Dict[str, Any]:
        """
        Parse query to extract search parameters.
        
        Args:
            query: Search query
            
        Returns:
            Dictionary with search parameters
        """
        # Default parameters
        params = {
            "entity_types": ["devices", "variables", "actions"],
            "top_k": 10,
            "threshold": 0.3
        }
        
        # Convert to lowercase for analysis
        query_lower = query.lower()
        
        # Determine entity types to search
        if any(word in query_lower for word in ["device", "devices", "sensor", "switch", "light"]):
            params["entity_types"] = ["devices"]
        elif any(word in query_lower for word in ["variable", "variables", "var"]):
            params["entity_types"] = ["variables"]
        elif any(word in query_lower for word in ["action", "actions", "scene", "scenes"]):
            params["entity_types"] = ["actions"]
        
        # Adjust result count based on query
        if "all" in query_lower:
            params["top_k"] = 50
        elif "many" in query_lower or "list" in query_lower:
            params["top_k"] = 20
        elif "few" in query_lower or "some" in query_lower:
            params["top_k"] = 5
        
        # Adjust threshold for specific queries
        if "exact" in query_lower or "specific" in query_lower:
            params["threshold"] = 0.7
        elif "similar" in query_lower or "like" in query_lower:
            params["threshold"] = 0.2
        
        return params
    
    def _format_results(self, results: Dict[str, List[Dict]], query: str) -> Dict[str, Any]:
        """
        Format search results for output.
        
        Args:
            results: Raw search results
            query: Original query
            
        Returns:
            Formatted results dictionary
        """
        # Count total results
        total_count = sum(len(entities) for entities in results.values())
        
        # Create summary
        summary = []
        for entity_type, entities in results.items():
            if entities:
                summary.append(f"{len(entities)} {entity_type}")
        
        summary_text = f"Found {total_count} entities"
        if summary:
            summary_text += f" ({', '.join(summary)})"
        
        # Format individual results
        formatted = {
            "query": query,
            "summary": summary_text,
            "total_count": total_count,
            "results": {}
        }
        
        # Add results for each entity type
        for entity_type, entities in results.items():
            formatted["results"][entity_type] = []
            
            for entity in entities:
                # Extract similarity score
                score = entity.pop("_similarity_score", 0.0)
                
                # Create formatted entry
                formatted_entry = {
                    "id": entity.get("id"),
                    "name": entity.get("name", "Unknown"),
                    "relevance_score": round(score, 3)
                }
                
                # Add type-specific fields
                if entity_type == "devices":
                    formatted_entry.update({
                        "type": entity.get("type", ""),
                        "model": entity.get("model", ""),
                        "address": entity.get("address", "")
                    })
                elif entity_type == "variables":
                    formatted_entry.update({
                        "value": entity.get("value", ""),
                        "folder_id": entity.get("folderId", 0)
                    })
                elif entity_type == "actions":
                    formatted_entry.update({
                        "folder_id": entity.get("folderId", 0),
                        "description": entity.get("description", "")
                    })
                
                formatted["results"][entity_type].append(formatted_entry)
        
        return formatted