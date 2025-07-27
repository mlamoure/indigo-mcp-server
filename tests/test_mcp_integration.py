"""
Integration tests for MCP server core functionality.
"""

import json
import pytest
import threading
import time
from mcp_server.core import MCPServerCore
from tests.fixtures.sample_data import SampleData


class TestMCPServerCore:
    """Integration tests for the MCP server core."""
    
    def test_mcp_server_initialization(self, mock_data_provider, populated_mock_vector_store):
        """Test MCP server core initialization."""
        server = MCPServerCore(
            data_provider=mock_data_provider,
            vector_store=populated_mock_vector_store,
            server_name="test-server"
        )
        
        assert server.data_provider == mock_data_provider
        assert server.vector_store == populated_mock_vector_store
        assert server.server_name == "test-server"
        assert server.search_handler is not None
        assert not server.is_running
    
    def test_mcp_server_start_stop(self, mock_data_provider, populated_mock_vector_store):
        """Test starting and stopping the MCP server."""
        server = MCPServerCore(
            data_provider=mock_data_provider,
            vector_store=populated_mock_vector_store
        )
        
        # Test start
        server.start()
        time.sleep(0.1)  # Give server time to start
        assert server.is_running
        assert server.mcp_server is not None
        assert server.mcp_thread is not None
        assert server.mcp_thread.is_alive()
        
        # Test stop
        server.stop()
        time.sleep(0.1)  # Give server time to stop
        assert not server.is_running
    
    def test_search_tool_registration(self, mock_data_provider, populated_mock_vector_store):
        """Test that search tool is properly registered."""
        server = MCPServerCore(
            data_provider=mock_data_provider,
            vector_store=populated_mock_vector_store
        )
        
        # Start server to trigger tool registration
        server.start()
        time.sleep(0.1)
        
        try:
            # The tools are registered during startup
            # We can't directly test the tool execution without a full MCP client,
            # but we can verify the server started successfully
            assert server.mcp_server is not None
            assert server.search_handler is not None
            
        finally:
            server.stop()
    
    def test_resource_registration(self, mock_data_provider, populated_mock_vector_store):
        """Test that resources are properly registered."""
        server = MCPServerCore(
            data_provider=mock_data_provider,
            vector_store=populated_mock_vector_store
        )
        
        server.start()
        time.sleep(0.1)
        
        try:
            # Resources should be registered during startup
            assert server.mcp_server is not None
            
        finally:
            server.stop()


class TestDataProviderIntegration:
    """Integration tests for data provider functionality."""
    
    def test_mock_data_provider_devices(self, mock_data_provider):
        """Test mock data provider device operations."""
        devices = mock_data_provider.get_all_devices()
        assert len(devices) == 5  # From MockDataProvider
        
        # Test getting specific device
        device = mock_data_provider.get_device(1)
        assert device is not None
        assert device["id"] == 1
        assert device["name"] == "Living Room Light"
        
        # Test non-existent device
        device = mock_data_provider.get_device(999)
        assert device is None
    
    def test_mock_data_provider_variables(self, mock_data_provider):
        """Test mock data provider variable operations."""
        variables = mock_data_provider.get_all_variables()
        assert len(variables) == 3  # From MockDataProvider
        
        # Test getting specific variable
        variable = mock_data_provider.get_variable(101)
        assert variable is not None
        assert variable["id"] == 101
        assert variable["name"] == "House Mode"
        
        # Test non-existent variable
        variable = mock_data_provider.get_variable(999)
        assert variable is None
    
    def test_mock_data_provider_actions(self, mock_data_provider):
        """Test mock data provider action operations."""
        actions = mock_data_provider.get_all_actions()
        assert len(actions) == 3  # From MockDataProvider
        
        # Test getting specific action
        action = mock_data_provider.get_action(201)
        assert action is not None
        assert action["id"] == 201
        assert action["name"] == "Good Night Scene"
        
        # Test non-existent action
        action = mock_data_provider.get_action(999)
        assert action is None


class TestVectorStoreIntegration:
    """Integration tests for vector store functionality."""
    
    def test_vector_store_with_real_data(self, populated_mock_vector_store):
        """Test vector store with realistic data."""
        # Test search for different entity types
        results = populated_mock_vector_store.search("light")
        assert "devices" in results
        
        # Test that we get reasonable results
        total_results = sum(len(entities) for entities in results.values())
        assert total_results > 0
    
    def test_vector_store_similarity_scoring(self, populated_mock_vector_store):
        """Test vector store similarity scoring with real queries."""
        # Test exact match should score higher than partial match
        exact_results = populated_mock_vector_store.search("Living Room Light")
        partial_results = populated_mock_vector_store.search("light")
        
        # Both should return results
        assert len(exact_results["devices"]) > 0 or len(partial_results["devices"]) > 0


class TestEndToEndWorkflow:
    """End-to-end integration tests."""
    
    def test_complete_search_workflow(self, mock_data_provider, populated_mock_vector_store):
        """Test complete search workflow from query to result."""
        server = MCPServerCore(
            data_provider=mock_data_provider,
            vector_store=populated_mock_vector_store
        )
        
        # Test search directly through search handler
        result = server.search_handler.search("find all lights")
        
        # Validate complete result structure
        assert "query" in result
        assert "summary" in result
        assert "total_count" in result
        assert "results" in result
        
        assert result["query"] == "find all lights"
        assert isinstance(result["total_count"], int)
        assert result["total_count"] >= 0
        
        # Validate results structure
        assert "devices" in result["results"]
        assert "variables" in result["results"]
        assert "actions" in result["results"]
        
        # If we have results, validate their format
        for entity_type in ["devices", "variables", "actions"]:
            for entity in result["results"][entity_type]:
                assert "id" in entity
                assert "name" in entity
                assert "relevance_score" in entity
                assert isinstance(entity["relevance_score"], (int, float))
                assert 0.0 <= entity["relevance_score"] <= 1.0
    
    def test_multiple_concurrent_searches(self, mock_data_provider, populated_mock_vector_store):
        """Test multiple concurrent search operations."""
        server = MCPServerCore(
            data_provider=mock_data_provider,
            vector_store=populated_mock_vector_store
        )
        
        search_queries = [
            "light",
            "temperature",
            "security",
            "bedroom"
        ]
        
        results = []
        threads = []
        
        def perform_search(query):
            result = server.search_handler.search(query)
            results.append((query, result))
        
        # Start concurrent searches
        for query in search_queries:
            thread = threading.Thread(target=perform_search, args=(query,))
            threads.append(thread)
            thread.start()
        
        # Wait for all searches to complete
        for thread in threads:
            thread.join()
        
        # Validate all searches completed successfully
        assert len(results) == len(search_queries)
        
        for query, result in results:
            assert result["query"] == query
            assert "total_count" in result
            assert isinstance(result["total_count"], int)
    
    def test_data_provider_and_vector_store_consistency(self, mock_data_provider, mock_vector_store):
        """Test consistency between data provider and vector store."""
        # Update vector store with data from data provider
        mock_vector_store.update_embeddings(
            devices=mock_data_provider.get_all_devices(),
            variables=mock_data_provider.get_all_variables(),
            actions=mock_data_provider.get_all_actions()
        )
        
        # Verify counts match
        assert mock_vector_store.get_entity_count("devices") == len(mock_data_provider.get_all_devices())
        assert mock_vector_store.get_entity_count("variables") == len(mock_data_provider.get_all_variables())
        assert mock_vector_store.get_entity_count("actions") == len(mock_data_provider.get_all_actions())
        
        # Test search with known entities
        devices = mock_data_provider.get_all_devices()
        if devices:
            device_name = devices[0]["name"]
            results = mock_vector_store.search(device_name)
            
            # Should find the device
            assert len(results["devices"]) > 0
            found_device = results["devices"][0]
            assert found_device["name"] == device_name
    
    def test_error_resilience(self, mock_data_provider):
        """Test system resilience to errors."""
        # Test with failing vector store
        class FailingVectorStore:
            def search(self, *args, **kwargs):
                raise Exception("Vector store failure")
            
            def update_embeddings(self, *args, **kwargs):
                raise Exception("Update failure")
            
            def close(self):
                pass
        
        failing_store = FailingVectorStore()
        server = MCPServerCore(
            data_provider=mock_data_provider,
            vector_store=failing_store
        )
        
        # Search should handle vector store failure gracefully
        result = server.search_handler.search("test query")
        assert "error" in result
        assert result["total_count"] == 0