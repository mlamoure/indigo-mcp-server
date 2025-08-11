"""
Integration tests for semantic keyword generation with structured outputs.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import List, Dict, Any

# Import the module under test
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'MCP Server.indigoPlugin', 'Contents', 'Server Plugin'))

from mcp_server.common.vector_store.semantic_keywords import (
    BatchKeywordsResponse, 
    DeviceKeywords,
    _generate_llm_keywords_batch
)


class TestSemanticKeywordsIntegration:
    """Integration tests for semantic keyword generation."""

    def test_batch_keywords_response_model_structure(self):
        """Test that BatchKeywordsResponse model has correct structure."""
        # Create a valid response
        device_keywords = DeviceKeywords(device_number=1, keywords=["light", "dimmer", "bedroom"])
        batch_response = BatchKeywordsResponse(devices=[device_keywords])
        
        assert len(batch_response.devices) == 1
        assert batch_response.devices[0].device_number == 1
        assert batch_response.devices[0].keywords == ["light", "dimmer", "bedroom"]

    @patch('mcp_server.common.vector_store.semantic_keywords.perform_completion')
    def test_batch_llm_keywords_success(self, mock_completion):
        """Test successful batch LLM keyword generation with structured output."""
        # Mock successful structured response
        mock_completion.return_value = '{"devices": [{"device_number": 1, "keywords": ["light", "switch"]}]}'
        
        entities = [
            {"id": "123", "name": "Bedroom Light", "deviceTypeId": "dimmer"}
        ]
        entity_ids = ["123"]
        cache_keys = ["bedroom_light_dimmer"]
        
        result = _generate_llm_keywords_batch(entities, entity_ids, cache_keys)
        
        # Verify perform_completion was called with BatchKeywordsResponse model
        mock_completion.assert_called_once()
        call_args = mock_completion.call_args
        assert call_args[1]['response_model'] == BatchKeywordsResponse
        assert call_args[1]['model'] == 'gpt-5-mini'  # Small model for keywords
        
        # Verify result structure
        assert "123" in result
        assert result["123"] == ["light", "switch"]

    @patch('mcp_server.common.vector_store.semantic_keywords.perform_completion')
    def test_batch_llm_keywords_fallback_parsing(self, mock_completion):
        """Test batch LLM keywords with fallback response parsing."""
        # Mock fallback response (non-structured)
        mock_completion.return_value = '''
        Device 1 keywords: light, switch, bedroom
        Device 2 keywords: sensor, temperature
        '''
        
        entities = [
            {"id": "123", "name": "Bedroom Light", "deviceTypeId": "dimmer"},
            {"id": "456", "name": "Temp Sensor", "deviceTypeId": "sensor"}
        ]
        entity_ids = ["123", "456"]
        cache_keys = ["bedroom_light_dimmer", "temp_sensor_sensor"]
        
        result = _generate_llm_keywords_batch(entities, entity_ids, cache_keys)
        
        # Should attempt structured output first
        mock_completion.assert_called_once()
        call_args = mock_completion.call_args
        assert call_args[1]['response_model'] == BatchKeywordsResponse

    @patch('mcp_server.common.vector_store.semantic_keywords.perform_completion')
    def test_batch_llm_keywords_empty_response(self, mock_completion):
        """Test handling of empty response from LLM."""
        mock_completion.return_value = ""
        
        entities = [{"id": "123", "name": "Test Device", "deviceTypeId": "relay"}]
        entity_ids = ["123"]
        cache_keys = ["test_device_relay"]
        
        result = _generate_llm_keywords_batch(entities, entity_ids, cache_keys)
        
        assert result == {}

    @patch('mcp_server.common.vector_store.semantic_keywords.perform_completion')
    def test_batch_llm_keywords_exception_handling(self, mock_completion):
        """Test exception handling in batch keyword generation."""
        mock_completion.side_effect = Exception("OpenAI API error")
        
        entities = [{"id": "123", "name": "Test Device", "deviceTypeId": "relay"}]
        entity_ids = ["123"]
        cache_keys = ["test_device_relay"]
        
        result = _generate_llm_keywords_batch(entities, entity_ids, cache_keys)
        
        # Should handle exception gracefully
        assert result == {}

    def test_device_keywords_validation(self):
        """Test DeviceKeywords model validation."""
        # Valid case
        valid_keywords = DeviceKeywords(device_number=1, keywords=["test"])
        assert valid_keywords.device_number == 1
        assert valid_keywords.keywords == ["test"]
        
        # Test with empty keywords (should be valid)
        empty_keywords = DeviceKeywords(device_number=2, keywords=[])
        assert empty_keywords.keywords == []
        
        # Test with multiple keywords
        multi_keywords = DeviceKeywords(
            device_number=3, 
            keywords=["light", "dimmer", "bedroom", "main"]
        )
        assert len(multi_keywords.keywords) == 4

    def test_batch_keywords_response_validation(self):
        """Test BatchKeywordsResponse model validation."""
        # Valid case with multiple devices
        devices = [
            DeviceKeywords(device_number=1, keywords=["light", "switch"]),
            DeviceKeywords(device_number=2, keywords=["sensor", "temperature"]),
        ]
        batch_response = BatchKeywordsResponse(devices=devices)
        assert len(batch_response.devices) == 2
        
        # Valid case with empty devices list
        empty_batch = BatchKeywordsResponse(devices=[])
        assert len(empty_batch.devices) == 0

    @patch('mcp_server.common.vector_store.semantic_keywords.perform_completion')
    def test_real_world_scenario_simulation(self, mock_completion):
        """Test simulation of real-world scenario that caused the original error."""
        # Simulate the exact error scenario: structured output with BaseModel
        mock_completion.return_value = '{"devices": [{"device_number": 1, "keywords": ["bedroom", "light", "dimmer", "main"]}]}'
        
        # Real device data structure
        entities = [{
            "id": "987654321",
            "name": "Bedroom - Main Light", 
            "deviceTypeId": "dimmer",
            "folderId": "bedroom_folder",
            "address": "12.34.56",
            "enabled": True,
            "configured": True
        }]
        entity_ids = ["987654321"]
        cache_keys = ["bedroom_main_light_dimmer_12.34.56"]
        
        result = _generate_llm_keywords_batch(entities, entity_ids, cache_keys)
        
        # Verify the fix works - should call with structured output
        mock_completion.assert_called_once()
        call_args = mock_completion.call_args
        
        # Key assertion: should use BatchKeywordsResponse for structured output
        assert call_args[1]['response_model'] == BatchKeywordsResponse
        assert call_args[1]['response_token_reserve'] == 500
        
        # Verify result
        assert "987654321" in result
        assert result["987654321"] == ["bedroom", "light", "dimmer", "main"]

    @patch('mcp_server.common.vector_store.semantic_keywords.perform_completion')
    @patch('mcp_server.common.vector_store.semantic_keywords.logger')
    def test_error_logging_with_structured_output_failure(self, mock_logger, mock_completion):
        """Test that proper error logging occurs when structured output fails."""
        # Simulate the exact error from the logs
        mock_completion.side_effect = Exception("You tried to pass a `BaseModel` class to `chat.completions.create()`; You must use `chat.completions.parse()` instead")
        
        entities = [{"id": "123", "name": "Test Device", "deviceTypeId": "relay"}]
        entity_ids = ["123"]
        cache_keys = ["test_device"]
        
        result = _generate_llm_keywords_batch(entities, entity_ids, cache_keys)
        
        # Should log the error
        mock_logger.error.assert_called_once()
        error_call = mock_logger.error.call_args[0][0]
        assert "Error in batch LLM keyword generation" in error_call
        
        # Should return empty dict on error
        assert result == {}