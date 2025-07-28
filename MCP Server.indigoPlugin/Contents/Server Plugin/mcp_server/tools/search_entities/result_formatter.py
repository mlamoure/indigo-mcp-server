"""
Result formatter for search results.
"""

from typing import Dict, Any, List


class ResultFormatter:
    """Formats search results for different output requirements."""
    
    def format_search_results(self, results: Dict[str, List[Dict]], query: str) -> Dict[str, Any]:
        """
        Format search results for output.
        
        Args:
            results: Raw search results from vector store
            query: Original search query
            
        Returns:
            Formatted results dictionary
        """
        # Count total results
        total_count = sum(len(entities) for entities in results.values())
        
        # Create summary
        summary = self._create_summary(results, total_count)
        
        # Format individual results
        formatted = {
            "query": query,
            "summary": summary,
            "total_count": total_count,
            "results": {}
        }
        
        # Add results for each entity type
        for entity_type, entities in results.items():
            formatted["results"][entity_type] = self._format_entity_list(entity_type, entities)
        
        return formatted
    
    def _create_summary(self, results: Dict[str, List[Dict]], total_count: int) -> str:
        """Create a summary text for the search results."""
        summary = []
        for entity_type, entities in results.items():
            if entities:
                summary.append(f"{len(entities)} {entity_type}")
        
        summary_text = f"Found {total_count} entities"
        if summary:
            summary_text += f" ({', '.join(summary)})"
        
        return summary_text
    
    def _format_entity_list(self, entity_type: str, entities: List[Dict]) -> List[Dict[str, Any]]:
        """Format a list of entities for a specific type."""
        formatted_entities = []
        
        for entity in entities:
            # Extract similarity score
            score = entity.pop("_similarity_score", 0.0)
            
            # Create base formatted entry
            formatted_entry = {
                "id": entity.get("id"),
                "name": entity.get("name", "Unknown"),
                "relevance_score": round(score, 3)
            }
            
            # Add type-specific fields
            if entity_type == "devices":
                formatted_entry.update(self._format_device_fields(entity))
            elif entity_type == "variables":
                formatted_entry.update(self._format_variable_fields(entity))
            elif entity_type == "actions":
                formatted_entry.update(self._format_action_fields(entity))
            
            formatted_entities.append(formatted_entry)
        
        return formatted_entities
    
    def _format_device_fields(self, device: Dict[str, Any]) -> Dict[str, Any]:
        """Format device-specific fields."""
        return {
            "type": device.get("type", ""),
            "model": device.get("model", ""),
            "address": device.get("address", ""),
            "enabled": device.get("enabled", True)
        }
    
    def _format_variable_fields(self, variable: Dict[str, Any]) -> Dict[str, Any]:
        """Format variable-specific fields."""
        return {
            "value": variable.get("value", ""),
            "folder_id": variable.get("folderId", 0),
            "read_only": variable.get("readOnly", False)
        }
    
    def _format_action_fields(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Format action-specific fields."""
        return {
            "folder_id": action.get("folderId", 0),
            "description": action.get("description", "")
        }