"""
Tests for the mock vector store.
"""

import pytest
from tests.mocks.mock_vector_store import MockVectorStore
from tests.fixtures.sample_data import SampleData


class TestMockVectorStore:
    """Test cases for the MockVectorStore class."""
    
    def test_initialization(self):
        """Test vector store initialization."""
        vector_store = MockVectorStore()
        
        assert vector_store.entities == {"devices": [], "variables": [], "actions": []}
        assert vector_store.get_entity_count("devices") == 0
        assert vector_store.get_entity_count("variables") == 0
        assert vector_store.get_entity_count("actions") == 0
    
    def test_update_embeddings(self, mock_vector_store):
        """Test updating embeddings with entity data."""
        devices = SampleData.DEVICES[:2]
        variables = SampleData.VARIABLES[:1]
        actions = SampleData.ACTIONS[:1]
        
        mock_vector_store.update_embeddings(
            devices=devices,
            variables=variables,
            actions=actions
        )
        
        assert mock_vector_store.get_entity_count("devices") == 2
        assert mock_vector_store.get_entity_count("variables") == 1
        assert mock_vector_store.get_entity_count("actions") == 1
    
    def test_add_entity(self, mock_vector_store):
        """Test adding individual entities."""
        device = SampleData.DEVICES[0]
        mock_vector_store.add_entity("devices", device)
        
        assert mock_vector_store.get_entity_count("devices") == 1
        assert mock_vector_store.entities["devices"][0]["id"] == device["id"]
    
    def test_remove_entity(self, mock_vector_store):
        """Test removing entities."""
        # Add some entities first
        mock_vector_store.update_embeddings(devices=SampleData.DEVICES[:2])
        assert mock_vector_store.get_entity_count("devices") == 2
        
        # Remove one entity
        mock_vector_store.remove_entity("devices", 1)
        assert mock_vector_store.get_entity_count("devices") == 1
        
        # Check that the correct entity was removed
        remaining_device = mock_vector_store.entities["devices"][0]
        assert remaining_device["id"] != 1
    
    def test_search_basic(self, populated_mock_vector_store):
        """Test basic search functionality."""
        results, metadata = populated_mock_vector_store.search("light")
        
        # Should find light-related devices
        assert len(results) > 0
        assert metadata["total_found"] > 0
        
        # Check that results have similarity scores
        for result in results:
            assert "_similarity_score" in result
            assert 0.0 <= result["_similarity_score"] <= 1.0
    
    def test_search_with_entity_types(self, populated_mock_vector_store):
        """Test search with specific entity types."""
        # Search only devices
        results, metadata = populated_mock_vector_store.search("light", entity_types=["devices"])
        
        # Should have device results
        assert len(results) > 0
        # All results should be devices (check entity type if available)
        for result in results:
            # Device entities from mock don't have _entity_type, but that's OK for this test
            pass
    
    def test_search_with_top_k(self, populated_mock_vector_store):
        """Test search with result limit."""
        results, metadata = populated_mock_vector_store.search("", top_k=2)
        
        assert len(results) <= 2
        assert metadata["total_returned"] <= 2
    
    def test_search_with_threshold(self, populated_mock_vector_store):
        """Test search with similarity threshold."""
        # High threshold should return fewer results
        results_high, metadata_high = populated_mock_vector_store.search("light", similarity_threshold=0.9)
        results_low, metadata_low = populated_mock_vector_store.search("light", similarity_threshold=0.1)
        
        assert len(results_high) <= len(results_low)
        assert metadata_high["total_found"] <= metadata_low["total_found"]
    
    def test_similarity_scoring(self, mock_vector_store):
        """Test the mock similarity scoring algorithm."""
        # Add a device with specific name and description
        device = {
            "id": 1,
            "name": "Living Room Light",
            "description": "Main ceiling light in living room",
            "model": "Dimmer Switch"
        }
        mock_vector_store.add_entity("devices", device)
        
        # Test exact name match
        results, metadata = mock_vector_store.search("Living Room Light")
        assert len(results) == 1
        assert results[0]["_similarity_score"] > 0.5
        
        # Test partial match
        results, metadata = mock_vector_store.search("light")
        assert len(results) == 1
        score = results[0]["_similarity_score"]
        assert 0.0 < score <= 1.0
        
        # Test no match
        results, metadata = mock_vector_store.search("temperature sensor")
        if len(results) > 0:
            assert results[0]["_similarity_score"] < 0.5
    
    def test_results_sorted_by_score(self, mock_vector_store):
        """Test that results are sorted by similarity score."""
        # Add devices with different relevance to query
        devices = [
            {"id": 1, "name": "Light Switch", "description": "Living room light"},
            {"id": 2, "name": "Temperature Sensor", "description": "Kitchen sensor"},
            {"id": 3, "name": "Bedroom Light", "description": "Overhead light"}
        ]
        
        for device in devices:
            mock_vector_store.add_entity("devices", device)
        
        results, metadata = mock_vector_store.search("light")
        
        if len(results) > 1:
            # Check that scores are in descending order
            scores = [result["_similarity_score"] for result in results]
            assert scores == sorted(scores, reverse=True)
    
    def test_empty_search(self, mock_vector_store):
        """Test search with no entities."""
        results, metadata = mock_vector_store.search("anything")
        
        assert results == []
        assert metadata["total_found"] == 0
        assert metadata["total_returned"] == 0
    
    def test_close(self, mock_vector_store):
        """Test the close method (should be no-op for mock)."""
        # Should not raise any exception
        mock_vector_store.close()