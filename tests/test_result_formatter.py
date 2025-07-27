"""
Tests for the result formatter.
"""

import pytest
from mcp_server.tools.result_formatter import ResultFormatter


class TestResultFormatter:
    """Test cases for the ResultFormatter class."""
    
    def test_format_search_results_basic(self, result_formatter, sample_search_results):
        """Test basic result formatting."""
        formatted = result_formatter.format_search_results(sample_search_results, "test query")
        
        assert formatted["query"] == "test query"
        assert formatted["total_count"] == 3  # 2 devices + 1 variable
        assert "Found 3 entities" in formatted["summary"]
        assert "2 devices" in formatted["summary"]
        assert "1 variables" in formatted["summary"]
        
        assert "devices" in formatted["results"]
        assert "variables" in formatted["results"]
        assert "actions" in formatted["results"]
    
    def test_format_device_results(self, result_formatter):
        """Test formatting of device results."""
        results = {
            "devices": [
                {
                    "id": 1,
                    "name": "Living Room Light",
                    "type": "dimmer",
                    "model": "Dimmer Switch",
                    "address": "A1",
                    "enabled": True,
                    "_similarity_score": 0.9
                }
            ],
            "variables": [],
            "actions": []
        }
        
        formatted = result_formatter.format_search_results(results, "light")
        device = formatted["results"]["devices"][0]
        
        assert device["id"] == 1
        assert device["name"] == "Living Room Light"
        assert device["relevance_score"] == 0.9
        assert device["type"] == "dimmer"
        assert device["model"] == "Dimmer Switch"
        assert device["address"] == "A1"
        assert device["enabled"] == True
        assert "_similarity_score" not in device  # Should be removed
    
    def test_format_variable_results(self, result_formatter):
        """Test formatting of variable results."""
        results = {
            "devices": [],
            "variables": [
                {
                    "id": 101,
                    "name": "House Mode",
                    "value": "Home",
                    "folderId": 1,
                    "readOnly": False,
                    "_similarity_score": 0.8
                }
            ],
            "actions": []
        }
        
        formatted = result_formatter.format_search_results(results, "mode")
        variable = formatted["results"]["variables"][0]
        
        assert variable["id"] == 101
        assert variable["name"] == "House Mode"
        assert variable["relevance_score"] == 0.8
        assert variable["value"] == "Home"
        assert variable["folder_id"] == 1
        assert variable["read_only"] == False
    
    def test_format_action_results(self, result_formatter):
        """Test formatting of action results."""
        results = {
            "devices": [],
            "variables": [],
            "actions": [
                {
                    "id": 201,
                    "name": "Good Night Scene",
                    "folderId": 1,
                    "description": "Turn off lights and lock doors",
                    "_similarity_score": 0.95
                }
            ]
        }
        
        formatted = result_formatter.format_search_results(results, "scene")
        action = formatted["results"]["actions"][0]
        
        assert action["id"] == 201
        assert action["name"] == "Good Night Scene"
        assert action["relevance_score"] == 0.95
        assert action["folder_id"] == 1
        assert action["description"] == "Turn off lights and lock doors"
    
    def test_empty_results(self, result_formatter):
        """Test formatting of empty results."""
        results = {"devices": [], "variables": [], "actions": []}
        
        formatted = result_formatter.format_search_results(results, "nonexistent")
        
        assert formatted["total_count"] == 0
        assert formatted["summary"] == "Found 0 entities"
        assert len(formatted["results"]["devices"]) == 0
        assert len(formatted["results"]["variables"]) == 0
        assert len(formatted["results"]["actions"]) == 0
    
    def test_create_summary(self, result_formatter):
        """Test summary creation."""
        # Test with mixed results
        results = {
            "devices": [{"id": 1}, {"id": 2}],
            "variables": [{"id": 101}],
            "actions": []
        }
        summary = result_formatter._create_summary(results, 3)
        assert summary == "Found 3 entities (2 devices, 1 variables)"
        
        # Test with only one type
        results = {"devices": [{"id": 1}], "variables": [], "actions": []}
        summary = result_formatter._create_summary(results, 1)
        assert summary == "Found 1 entities (1 devices)"
        
        # Test with no results
        results = {"devices": [], "variables": [], "actions": []}
        summary = result_formatter._create_summary(results, 0)
        assert summary == "Found 0 entities"
    
    def test_missing_fields_handling(self, result_formatter):
        """Test handling of missing fields in entities."""
        results = {
            "devices": [
                {
                    "id": 1,
                    # Missing name, type, model, etc.
                    "_similarity_score": 0.7
                }
            ],
            "variables": [],
            "actions": []
        }
        
        formatted = result_formatter.format_search_results(results, "test")
        device = formatted["results"]["devices"][0]
        
        assert device["name"] == "Unknown"  # Default for missing name
        assert device["type"] == ""  # Default for missing type
        assert device["model"] == ""  # Default for missing model
        assert device["enabled"] == True  # Default for missing enabled
    
    def test_score_rounding(self, result_formatter):
        """Test that similarity scores are properly rounded."""
        results = {
            "devices": [
                {
                    "id": 1,
                    "name": "Test Device",
                    "_similarity_score": 0.123456789
                }
            ],
            "variables": [],
            "actions": []
        }
        
        formatted = result_formatter.format_search_results(results, "test")
        device = formatted["results"]["devices"][0]
        
        assert device["relevance_score"] == 0.123  # Rounded to 3 decimal places