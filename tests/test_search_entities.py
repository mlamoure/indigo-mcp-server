"""
Tests for the search entities handler.
"""

import pytest
from mcp_server.tools.search_entities import SearchEntitiesHandler
from tests.fixtures.sample_data import SampleData, TEST_QUERIES


class TestSearchEntitiesHandler:
    """Test cases for the SearchEntitiesHandler class."""
    
    def test_initialization(self, mock_data_provider, mock_vector_store):
        """Test handler initialization."""
        handler = SearchEntitiesHandler(mock_data_provider, mock_vector_store)
        
        assert handler.data_provider == mock_data_provider
        assert handler.vector_store == mock_vector_store
        assert handler.query_parser is not None
        assert handler.result_formatter is not None
    
    def test_search_basic(self, search_handler, populated_mock_vector_store):
        """Test basic search functionality."""
        # Replace the vector store with populated one
        search_handler.vector_store = populated_mock_vector_store
        
        result = search_handler.search("light")
        
        assert "query" in result
        assert "summary" in result
        assert "total_count" in result
        assert "results" in result
        assert result["query"] == "light"
        assert isinstance(result["total_count"], int)
        assert result["total_count"] >= 0
    
    def test_search_device_specific(self, search_handler, populated_mock_vector_store):
        """Test device-specific searches."""
        search_handler.vector_store = populated_mock_vector_store
        
        # Test light search (should match "Living Room Light")
        result = search_handler.search("find all light")
        assert result["total_count"] > 0
        
        # Should have device results
        if result["total_count"] > 0:
            assert len(result["results"]["devices"]) > 0
            
            # Check device result format
            device = result["results"]["devices"][0]
            assert "id" in device
            assert "name" in device
            assert "relevance_score" in device
            assert "type" in device
    
    def test_search_variable_specific(self, search_handler, populated_mock_vector_store):
        """Test variable-specific searches."""
        search_handler.vector_store = populated_mock_vector_store
        
        result = search_handler.search("house mode variable")
        
        # Should search only variables based on query parsing
        # Check that result structure is correct
        assert "variables" in result["results"]
        assert isinstance(result["results"]["variables"], list)
    
    def test_search_action_specific(self, search_handler, populated_mock_vector_store):
        """Test action-specific searches."""
        search_handler.vector_store = populated_mock_vector_store
        
        result = search_handler.search("good night scene")
        
        # Should search only actions based on query parsing
        assert "actions" in result["results"]
        assert isinstance(result["results"]["actions"], list)
    
    def test_search_with_various_queries(self, search_handler, populated_mock_vector_store):
        """Test search with various query types."""
        search_handler.vector_store = populated_mock_vector_store
        
        # Test different query patterns
        queries = [
            "temperature",
            "bedroom",
            "security",
            "all devices",
            "few variables",
            "exact match for lock"
        ]
        
        for query in queries:
            result = search_handler.search(query)
            
            # Basic structure validation
            assert "query" in result
            assert "total_count" in result
            assert "results" in result
            assert result["query"] == query
            assert isinstance(result["total_count"], int)
            
            # Results should have all entity types
            assert "devices" in result["results"]
            assert "variables" in result["results"]
            assert "actions" in result["results"]
    
    def test_search_error_handling(self, mock_data_provider):
        """Test error handling in search."""
        # Create a mock vector store that raises an exception
        class FailingVectorStore:
            def search(self, *args, **kwargs):
                raise Exception("Vector store error")
        
        failing_store = FailingVectorStore()
        handler = SearchEntitiesHandler(mock_data_provider, failing_store)
        
        result = handler.search("test query")
        
        # Should return error response
        assert "error" in result
        assert result["query"] == "test query"
        assert result["total_count"] == 0
        assert result["summary"] == "Search failed"
        
        # Should have empty results
        assert len(result["results"]["devices"]) == 0
        assert len(result["results"]["variables"]) == 0
        assert len(result["results"]["actions"]) == 0
    
    def test_search_empty_query(self, search_handler, populated_mock_vector_store):
        """Test search with empty query."""
        search_handler.vector_store = populated_mock_vector_store
        
        result = search_handler.search("")
        
        # Should handle empty query gracefully
        assert result["query"] == ""
        assert "total_count" in result
        assert isinstance(result["total_count"], int)
    
    def test_search_special_characters(self, search_handler, populated_mock_vector_store):
        """Test search with special characters."""
        search_handler.vector_store = populated_mock_vector_store
        
        queries_with_special_chars = [
            "device-name",
            "test_variable",
            "action.group",
            "name with spaces",
            "123 numeric"
        ]
        
        for query in queries_with_special_chars:
            result = search_handler.search(query)
            
            # Should not crash and return valid structure
            assert "query" in result
            assert result["query"] == query
            assert "total_count" in result
    
    def test_search_result_relevance_scores(self, search_handler, populated_mock_vector_store):
        """Test that search results include relevance scores."""
        search_handler.vector_store = populated_mock_vector_store
        
        result = search_handler.search("light")
        
        # Check that devices have relevance scores
        for device in result["results"]["devices"]:
            assert "relevance_score" in device
            score = device["relevance_score"]
            assert isinstance(score, (int, float))
            assert 0.0 <= score <= 1.0
    
    def test_search_integration_with_query_parser(self, search_handler, populated_mock_vector_store):
        """Test integration between search handler and query parser."""
        search_handler.vector_store = populated_mock_vector_store
        
        # Test that query parser parameters are correctly used
        result = search_handler.search("show few exact devices like lights")
        
        # The query parser should extract:
        # - entity_types: ["devices"]
        # - top_k: 5 (few)
        # - threshold: 0.7 (exact)
        
        # We can't directly test the internal parameters, but we can test
        # that the search completes successfully
        assert result["query"] == "show few exact devices like lights"
        assert "total_count" in result
    
    def test_search_integration_with_result_formatter(self, search_handler, populated_mock_vector_store):
        """Test integration between search handler and result formatter."""
        search_handler.vector_store = populated_mock_vector_store
        
        result = search_handler.search("temperature")
        
        # Test that result formatter produces expected structure
        assert "summary" in result
        assert "Found" in result["summary"]
        assert "entities" in result["summary"]
        
        # Test that individual results are properly formatted
        all_results = []
        for entity_type in ["devices", "variables", "actions"]:
            all_results.extend(result["results"][entity_type])
        
        for entity in all_results:
            assert "id" in entity
            assert "name" in entity
            assert "relevance_score" in entity
            # Should not contain internal fields
            assert "_similarity_score" not in entity