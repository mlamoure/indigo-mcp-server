"""
Query parser for natural language search queries.
"""

from typing import Dict, Any, List, Optional


class QueryParser:
    """Parses natural language queries to extract search parameters."""
    
    def parse(
        self, 
        query: str, 
        device_types: Optional[List[str]] = None,
        entity_types: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Parse query to extract search parameters.
        
        Args:
            query: Natural language search query
            device_types: Optional list of device types to filter by
            entity_types: Optional list of entity types to search
            
        Returns:
            Dictionary with search parameters:
            - entity_types: List of entity types to search (plural form for vector store)
            - device_types: List of device types to filter by
            - top_k: Maximum number of results
            - threshold: Similarity threshold
        """
        # Default parameters
        params = {
            "entity_types": ["devices", "variables", "actions"],
            "device_types": device_types or [],
            "top_k": 1000,  # Large number since we filter by similarity threshold
            "threshold": 0.15  # Lower threshold to capture more relevant results
        }
        
        # Convert to lowercase for analysis
        query_lower = query.lower()
        
        # Determine entity types to search
        # If device_types is provided, we only search devices
        if device_types is not None and len(device_types) > 0:
            params["entity_types"] = ["devices"]
        # Otherwise use explicit entity_types parameter if provided
        elif entity_types is not None:
            # Convert singular entity types to plural for vector store compatibility
            plural_mapping = {
                "device": "devices",
                "variable": "variables", 
                "action": "actions"
            }
            params["entity_types"] = [plural_mapping.get(et, et) for et in entity_types]
        # Finally, parse from query if no explicit parameters
        else:
            params["entity_types"] = self._extract_entity_types(query_lower)
        
        # Adjust result count based on query
        params["top_k"] = self._extract_result_count(query_lower)
        
        # Adjust threshold for specific queries
        params["threshold"] = self._extract_similarity_threshold(query_lower)
        
        return params
    
    def _extract_entity_types(self, query_lower: str) -> List[str]:
        """Extract entity types to search from query."""
        # Check for device-specific keywords
        device_keywords = ["device", "devices", "sensor", "switch", "light", "thermostat", "dimmer"]
        if any(word in query_lower for word in device_keywords):
            return ["devices"]
        
        # Check for variable-specific keywords
        variable_keywords = ["variable", "variables", "var"]
        if any(word in query_lower for word in variable_keywords):
            return ["variables"]
        
        # Check for action-specific keywords
        action_keywords = ["action", "actions", "scene", "scenes", "group"]
        if any(word in query_lower for word in action_keywords):
            return ["actions"]
        
        # Default to all entity types
        return ["devices", "variables", "actions"]
    
    def _extract_result_count(self, query_lower: str) -> int:
        """Extract desired result count from query."""
        if "all" in query_lower:
            return 50
        elif "many" in query_lower or "list" in query_lower:
            return 20
        elif "few" in query_lower or "some" in query_lower:
            return 5
        elif "one" in query_lower or "single" in query_lower:
            return 1
        
        # Default result count
        return 10
    
    def _extract_similarity_threshold(self, query_lower: str) -> float:
        """Extract similarity threshold from query."""
        if "exact" in query_lower or "specific" in query_lower:
            return 0.7
        elif "similar" in query_lower or "like" in query_lower:
            return 0.2
        elif "related" in query_lower or "close" in query_lower:
            return 0.4
        
        # Default threshold
        return 0.15