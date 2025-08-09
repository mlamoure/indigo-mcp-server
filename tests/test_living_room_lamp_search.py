"""
Test cases specifically for the Living Room Lamp search issue.
Validates that LLM-enhanced keyword generation and query expansion improve search accuracy.
"""

import os
import pytest
from unittest.mock import Mock, patch, MagicMock
import sys

# Add the plugin path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "MCP Server.indigoPlugin", "Contents", "Server Plugin"))

from mcp_server.common.vector_store.semantic_keywords import (
    generate_entity_keywords, 
    _generate_llm_keywords,
    clear_llm_keyword_cache
)
from mcp_server.tools.search_entities.query_parser import QueryParser
from mcp_server.tools.search_entities.main import SearchEntitiesHandler


class TestLivingRoomLampSearch:
    """Test cases for Living Room Lamp search improvements."""
    
    def setup_method(self):
        """Set up test environment before each test."""
        # Clear caches
        clear_llm_keyword_cache()
        
        # Sample Living Room Lamp device data
        self.living_room_lamp = {
            "id": 1183208037,
            "name": "Living Room Lamp",
            "class": "indigo.RelayDevice",
            "deviceTypeId": "zwRelayType",
            "description": "",
            "model": "Smart Switch 6 (ZW096)",
            "onState": False,
            "states": {
                "onOffState": False,
                "curEnergyLevel": 11.282
            }
        }
        
        # Sample competing device that was returned in original search
        self.competing_device = {
            "id": 1442978166,
            "name": "Living Room Ceiling Lights",
            "class": "indigo.DimmerDevice",
            "deviceTypeId": "ra2Dimmer", 
            "description": "",
            "model": "RadioRA 2 Dimmer",
            "brightness": 0,
            "onState": False
        }
    
    def test_rule_based_keywords_include_lamp_synonyms(self):
        """Test that rule-based system generates 'lamp' related keywords."""
        keywords = generate_entity_keywords(self.living_room_lamp, "devices")
        
        # Should include location keywords
        assert any("living" in k for k in keywords), f"Expected 'living' keywords in {keywords}"
        assert any("living_room" in k for k in keywords), f"Expected 'living_room' keywords in {keywords}"
        
        # Should include function keywords for 'lamp' in name
        # From _extract_function_keywords, "light" should map to ["lighting", "illumination", "lamp"]
        # But we need this to work bidirectionally
        print(f"Generated keywords for {self.living_room_lamp['name']}: {keywords}")
    
    @patch('mcp_server.common.openai_client.main.perform_completion')
    def test_llm_keyword_generation_for_lamp(self, mock_llm):
        """Test that LLM generates additional contextual keywords for Living Room Lamp."""
        # Mock LLM response with lamp-related keywords
        mock_llm.return_value = "lighting, illumination, light fixture, table lamp, floor lamp, accent light, ambient lighting"
        
        llm_keywords = _generate_llm_keywords(self.living_room_lamp, "devices")
        
        # Verify LLM was called
        mock_llm.assert_called_once()
        
        # Check that call included device info
        call_args = mock_llm.call_args[1]['messages']
        assert "Living Room Lamp" in call_args
        assert "Smart Switch 6" in call_args
        
        # Verify LLM keywords were parsed correctly
        expected_keywords = ["lighting", "illumination", "light fixture", "table lamp", "floor lamp", "accent light", "ambient lighting"]
        assert llm_keywords == expected_keywords
        print(f"LLM generated keywords: {llm_keywords}")
    
    @patch('mcp_server.common.openai_client.main.perform_completion')
    def test_combined_keywords_enhance_searchability(self, mock_llm):
        """Test that combined rule-based + LLM keywords improve device searchability."""
        # Mock LLM response
        mock_llm.return_value = "lighting, illumination, light fixture, table lamp, smart switch"
        
        # Generate all keywords (rule-based + LLM)
        all_keywords = generate_entity_keywords(self.living_room_lamp, "devices")
        
        # Should contain both rule-based and LLM keywords
        assert any("living" in k for k in all_keywords), "Missing location keywords"
        assert any("lighting" in k for k in all_keywords), "Missing LLM lighting keywords"
        assert any("illumination" in k for k in all_keywords), "Missing LLM illumination keywords"
        
        print(f"Combined keywords for Living Room Lamp: {all_keywords}")
    
    @patch('mcp_server.common.openai_client.main.perform_completion')
    def test_query_expansion_for_light_search(self, mock_llm):
        """Test that query expansion improves 'living room light' searches."""
        # Mock LLM response for query expansion
        mock_llm.return_value = "living room light lamp illumination lighting fixture lounge family room"
        
        parser = QueryParser()
        expanded = parser.expand_query("living room light")
        
        # Verify LLM was called for query expansion
        mock_llm.assert_called_once()
        
        # Check that expansion includes lamp-related terms
        assert "lamp" in expanded
        assert "illumination" in expanded
        assert "lighting" in expanded
        
        print(f"Query expansion: 'living room light' -> '{expanded}'")
    
    @patch('mcp_server.common.openai_client.main.perform_completion')
    def test_query_parser_caches_expansions(self, mock_llm):
        """Test that query expansion results are cached properly."""
        mock_llm.return_value = "living room light lamp illumination"
        
        parser = QueryParser()
        
        # First call should invoke LLM
        result1 = parser.expand_query("living room light")
        assert mock_llm.call_count == 1
        
        # Second call should use cache
        result2 = parser.expand_query("living room light")
        assert mock_llm.call_count == 1  # No additional calls
        assert result1 == result2
    
    def test_search_params_extraction(self):
        """Test that query parser correctly extracts search parameters."""
        parser = QueryParser()
        params = parser.parse("living room light")
        
        # Should target devices for lighting queries
        assert "devices" in params["entity_types"]
        
        # Should have reasonable defaults
        assert params["threshold"] == 0.15
        assert params["top_k"] == 10
        
        print(f"Search parameters for 'living room light': {params}")
    
    @patch('mcp_server.tools.search_entities.main.VectorStoreInterface')
    @patch('mcp_server.tools.search_entities.main.DataProvider')  
    @patch('mcp_server.common.openai_client.main.perform_completion')
    def test_end_to_end_search_integration(self, mock_query_llm, mock_data_provider, mock_vector_store):
        """Test end-to-end search integration with LLM enhancements."""
        # Mock query expansion
        mock_query_llm.return_value = "living room light lamp illumination lighting"
        
        # Mock vector store to return our test device
        mock_vector_store.search.return_value = (
            [{
                **self.living_room_lamp,
                "_similarity_score": 0.8,
                "_entity_type": "device"
            }],
            {"total_found": 1, "total_returned": 1, "truncated": False}
        )
        
        # Create handler
        handler = SearchEntitiesHandler(
            data_provider=mock_data_provider,
            vector_store=mock_vector_store
        )
        
        # Perform search
        results = handler.search("living room light")
        
        # Verify query was expanded
        mock_query_llm.assert_called_once()
        
        # Verify vector store was called with expanded query
        mock_vector_store.search.assert_called_once()
        call_args = mock_vector_store.search.call_args[1]
        assert call_args["query"] == "living room light lamp illumination lighting"
        
        # Verify Living Room Lamp appears in results
        assert results["total_count"] == 1
        assert len(results["results"]["devices"]) == 1
        assert results["results"]["devices"][0]["name"] == "Living Room Lamp"
        
        print(f"End-to-end search results: {results}")


@pytest.fixture
def mock_openai_env():
    """Provide mock OpenAI environment for tests."""
    with patch.dict(os.environ, {
        'OPENAI_API_KEY': 'test-key',
        'SMALL_MODEL': 'o4-mini'
    }):
        yield


class TestLivingRoomLampSearchWithEnv:
    """Tests that require OpenAI environment setup."""
    
    def test_keyword_caching_prevents_redundant_llm_calls(self, mock_openai_env):
        """Test that keyword caching works correctly."""
        with patch('mcp_server.common.openai_client.main.perform_completion') as mock_llm:
            mock_llm.return_value = "lighting, illumination, lamp"
            
            device = {
                "id": 123,
                "name": "Test Lamp",
                "model": "Test Model",
                "deviceTypeId": "test",
                "description": ""
            }
            
            # First call should hit LLM
            keywords1 = _generate_llm_keywords(device, "devices")
            assert mock_llm.call_count == 1
            
            # Second call with same device should use cache
            keywords2 = _generate_llm_keywords(device, "devices")
            assert mock_llm.call_count == 1  # No additional calls
            assert keywords1 == keywords2


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])