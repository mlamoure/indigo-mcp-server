"""
Mock vector store for testing.
"""

import re
from typing import Dict, List, Any, Optional
from interfaces.vector_store_interface import VectorStoreInterface


class MockVectorStore(VectorStoreInterface):
    """Mock vector store for testing without OpenAI dependency."""
    
    def __init__(self):
        """Initialize mock vector store."""
        self.entities = {
            "devices": [],
            "variables": [],
            "actions": []
        }
        
    def search(
        self, 
        query: str, 
        entity_types: Optional[List[str]] = None,
        top_k: int = 10,
        similarity_threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Mock search using simple text matching.
        
        Args:
            query: Search query
            entity_types: Entity types to search
            top_k: Maximum results
            similarity_threshold: Minimum similarity score
            
        Returns:
            List of matching entities with mock similarity scores
        """
        if entity_types is None:
            entity_types = ["devices", "variables", "actions"]
        
        query_lower = query.lower()
        # Always include all entity types in results, even if empty
        results = {"devices": [], "variables": [], "actions": []}
        
        for entity_type in entity_types:
            results[entity_type] = []
            
            for entity in self.entities.get(entity_type, []):
                # Simple text matching for mock
                score = self._calculate_mock_similarity(query_lower, entity)
                
                if score >= similarity_threshold:
                    entity_copy = entity.copy()
                    entity_copy["_similarity_score"] = score
                    results[entity_type].append(entity_copy)
            
            # Sort by similarity score (descending)
            results[entity_type].sort(key=lambda x: x["_similarity_score"], reverse=True)
            
            # Limit results
            results[entity_type] = results[entity_type][:top_k]
        
        return results
    
    def _calculate_mock_similarity(self, query: str, entity: Dict[str, Any]) -> float:
        """Calculate mock similarity score based on text matching."""
        # Create searchable text from entity
        searchable_text = " ".join([
            str(entity.get("name", "")),
            str(entity.get("description", "")),
            str(entity.get("model", "")),
            str(entity.get("type", ""))
        ]).lower()
        
        # Simple scoring based on word matches
        query_words = set(re.findall(r'\w+', query))
        entity_words = set(re.findall(r'\w+', searchable_text))
        
        if not query_words:
            return 0.0
        
        # Calculate word overlap
        overlap = len(query_words.intersection(entity_words))
        max_score = len(query_words)
        
        # Base score from word overlap
        score = overlap / max_score if max_score > 0 else 0.0
        
        # Boost score for exact name matches
        entity_name = entity.get("name", "").lower()
        if query in entity_name:
            score = min(1.0, score + 0.5)
        
        # Boost score for exact matches in description
        entity_desc = entity.get("description", "").lower()
        if query in entity_desc:
            score = min(1.0, score + 0.3)
        
        return score
    
    def update_embeddings(
        self,
        devices: Optional[List[Dict[str, Any]]] = None,
        variables: Optional[List[Dict[str, Any]]] = None,
        actions: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        """Update mock embeddings (just store the data)."""
        if devices is not None:
            self.entities["devices"] = devices
        
        if variables is not None:
            self.entities["variables"] = variables
        
        if actions is not None:
            self.entities["actions"] = actions
    
    def add_entity(self, entity_type: str, entity_data: Dict[str, Any]) -> None:
        """Add a single entity to the mock store."""
        if entity_type in self.entities:
            self.entities[entity_type].append(entity_data)
    
    def remove_entity(self, entity_type: str, entity_id: int) -> None:
        """Remove an entity from the mock store."""
        if entity_type in self.entities:
            self.entities[entity_type] = [
                entity for entity in self.entities[entity_type]
                if entity.get("id") != entity_id
            ]
    
    def close(self) -> None:
        """Close the mock vector store (no-op)."""
        pass
    
    def get_entity_count(self, entity_type: str) -> int:
        """Get count of entities for testing."""
        return len(self.entities.get(entity_type, []))