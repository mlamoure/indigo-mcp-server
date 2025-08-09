"""
Simple integration test for LLM-enhanced search functionality.
Tests actual keyword generation and query expansion without complex mocking.
"""

import os
import sys
from unittest.mock import patch

# Add the plugin path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "MCP Server.indigoPlugin", "Contents", "Server Plugin"))

from mcp_server.common.vector_store.semantic_keywords import (
    generate_entity_keywords,
    _generate_llm_keywords,
    _extract_function_keywords,
    clear_llm_keyword_cache
)
from mcp_server.tools.search_entities.query_parser import QueryParser, clear_query_expansion_cache


class TestLLMIntegrationSimple:
    """Simple tests for LLM integration features."""
    
    def test_rule_based_keywords_baseline(self):
        """Test that rule-based keyword generation works for Living Room Lamp."""
        device = {
            "id": 1183208037,
            "name": "Living Room Lamp", 
            "model": "Smart Switch 6 (ZW096)",
            "deviceTypeId": "zwRelayType",
            "description": ""
        }
        
        # Test function keyword extraction specifically
        function_keywords = _extract_function_keywords(device["name"])
        print(f"Function keywords for 'Living Room Lamp': {function_keywords}")
        
        # Should extract 'lamp' -> ['lighting', 'illumination', 'lamp']
        assert any("lighting" in k for k in function_keywords), f"Expected lighting keywords in {function_keywords}"
        
        # Test full keyword generation (without LLM for baseline)
        with patch('mcp_server.common.vector_store.semantic_keywords._generate_llm_keywords') as mock_llm:
            mock_llm.return_value = []  # Disable LLM for baseline test
            
            all_keywords = generate_entity_keywords(device, "devices")
            print(f"All baseline keywords: {all_keywords}")
            
            # Should have location keywords
            assert any("living" in k.lower() for k in all_keywords), "Missing location keywords"
            # Should have function keywords for lamp
            assert any("lighting" in k for k in all_keywords), "Missing lamp->lighting mapping"
    
    @patch('mcp_server.common.openai_client.main.perform_completion')
    def test_llm_keyword_enhancement(self, mock_llm):
        """Test that LLM enhancement adds valuable keywords."""
        # Mock LLM to return lamp-specific keywords
        mock_llm.return_value = "table lamp, floor lamp, accent lighting, light fixture, illumination device"
        
        device = {
            "id": 1183208037,
            "name": "Living Room Lamp",
            "model": "Smart Switch 6 (ZW096)", 
            "deviceTypeId": "zwRelayType",
            "description": ""
        }
        
        clear_llm_keyword_cache()  # Ensure fresh test
        
        # Generate LLM keywords
        llm_keywords = _generate_llm_keywords(device, "devices")
        print(f"LLM keywords: {llm_keywords}")
        
        # Verify expected keywords were generated
        assert "table lamp" in llm_keywords
        assert "floor lamp" in llm_keywords 
        assert "accent lighting" in llm_keywords
        
        # Test caching works
        mock_llm.reset_mock()
        llm_keywords_cached = _generate_llm_keywords(device, "devices")
        mock_llm.assert_not_called()  # Should not call LLM again
        assert llm_keywords == llm_keywords_cached
    
    @patch('mcp_server.common.openai_client.main.perform_completion')
    def test_query_expansion_improves_matching(self, mock_llm):
        """Test that query expansion helps with light->lamp queries."""
        # Clear cache to ensure fresh test
        clear_query_expansion_cache()
        
        # Mock LLM to return expanded query (different from original)
        mock_llm.return_value = "living room light lamp illumination lighting fixture"
        
        parser = QueryParser()
        expanded = parser.expand_query("living room light")
        
        print(f"Query expansion: 'living room light' -> '{expanded}'")
        print(f"Mock called: {mock_llm.called}")
        print(f"Mock call count: {mock_llm.call_count}")
        
        # Verify LLM was called
        assert mock_llm.called, "LLM should have been called for expansion"
        
        # Verify expansion includes lamp-related terms
        assert "lamp" in expanded, f"Expected 'lamp' in expanded query: {expanded}"
        assert "illumination" in expanded, f"Expected 'illumination' in expanded query: {expanded}"
        assert "lighting" in expanded, f"Expected 'lighting' in expanded query: {expanded}"
    
    def test_search_params_for_lighting_query(self):
        """Test that lighting queries get proper search parameters."""
        parser = QueryParser()
        
        params = parser.parse("living room light")
        print(f"Search params: {params}")
        
        # Should search devices for lighting queries
        assert "devices" in params["entity_types"]
        
        # Should use appropriate threshold and limits
        assert params["threshold"] == 0.15
        assert params["top_k"] == 10
        
        # Test with state detection
        params_with_state = parser.parse("living room lights that are on")
        print(f"Search params with state: {params_with_state}")
        
        # Should detect state and increase limits
        assert params_with_state["state_detected"] == True
        assert params_with_state["top_k"] >= 50  # Should increase for state filtering
    
    def test_device_keyword_coverage(self):
        """Test keyword generation for various device types that might compete with Living Room Lamp."""
        
        test_devices = [
            {
                "name": "Living Room Ceiling Lights",
                "model": "RadioRA 2 Dimmer", 
                "deviceTypeId": "ra2Dimmer"
            },
            {
                "name": "Living Room Lamp",
                "model": "Smart Switch 6 (ZW096)",
                "deviceTypeId": "zwRelayType"
            },
            {
                "name": "Living Room Lamp 2", 
                "model": "Smart Switch 6 (ZW096)",
                "deviceTypeId": "zwRelayType"
            }
        ]
        
        for device in test_devices:
            device["id"] = hash(device["name"]) % 1000000  # Simple ID generation
            device["description"] = ""
            
            # Generate keywords without LLM for comparison
            with patch('mcp_server.common.vector_store.semantic_keywords._generate_llm_keywords') as mock_llm:
                mock_llm.return_value = []
                keywords = generate_entity_keywords(device, "devices")
                
            print(f"\nDevice: {device['name']}")
            print(f"Keywords: {keywords}")
            
            # All should have location keywords
            assert any("living" in k.lower() for k in keywords), f"Missing location keywords for {device['name']}"
            
            # Lamp devices should have lamp->lighting mapping
            if "lamp" in device["name"].lower():
                assert any("lighting" in k for k in keywords), f"Missing lighting keywords for {device['name']}"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "-s"])