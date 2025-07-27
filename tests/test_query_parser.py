"""
Tests for the query parser.
"""

import pytest
from mcp_server.tools.query_parser import QueryParser


class TestQueryParser:
    """Test cases for the QueryParser class."""
    
    def test_parse_device_query(self, query_parser):
        """Test parsing device-specific queries."""
        result = query_parser.parse("find all lights")
        assert result["entity_types"] == ["devices"]
        assert result["top_k"] == 50  # "all" keyword
        
        result = query_parser.parse("show me switches")
        assert result["entity_types"] == ["devices"]
        
        result = query_parser.parse("dimmer in living room")
        assert result["entity_types"] == ["devices"]
    
    def test_parse_variable_query(self, query_parser):
        """Test parsing variable-specific queries."""
        result = query_parser.parse("house mode variable")
        assert result["entity_types"] == ["variables"]
        
        result = query_parser.parse("show all vars")
        assert result["entity_types"] == ["variables"]
        assert result["top_k"] == 50  # "all" keyword
    
    def test_parse_action_query(self, query_parser):
        """Test parsing action-specific queries."""
        result = query_parser.parse("good night scene")
        assert result["entity_types"] == ["actions"]
        
        result = query_parser.parse("list all actions")
        assert result["entity_types"] == ["actions"]
        assert result["top_k"] == 50  # "all" keyword
    
    def test_parse_general_query(self, query_parser):
        """Test parsing general queries."""
        result = query_parser.parse("bedroom")
        assert result["entity_types"] == ["devices", "variables", "actions"]
        
        result = query_parser.parse("temperature stuff")
        assert result["entity_types"] == ["devices", "variables", "actions"]
    
    def test_result_count_extraction(self, query_parser):
        """Test result count extraction from queries."""
        # Test "all" keyword
        result = query_parser.parse("show all devices")
        assert result["top_k"] == 50
        
        # Test "many" keyword
        result = query_parser.parse("list many lights")
        assert result["top_k"] == 20
        
        # Test "few" keyword
        result = query_parser.parse("show few sensors")
        assert result["top_k"] == 5
        
        # Test "one" keyword
        result = query_parser.parse("find one switch")
        assert result["top_k"] == 1
        
        # Test default
        result = query_parser.parse("bedroom light")
        assert result["top_k"] == 10
    
    def test_similarity_threshold_extraction(self, query_parser):
        """Test similarity threshold extraction from queries."""
        # Test "exact" keyword
        result = query_parser.parse("exact match for light")
        assert result["threshold"] == 0.7
        
        # Test "specific" keyword
        result = query_parser.parse("specific device named bedroom")
        assert result["threshold"] == 0.7
        
        # Test "similar" keyword
        result = query_parser.parse("similar to temperature")
        assert result["threshold"] == 0.2
        
        # Test "like" keyword
        result = query_parser.parse("devices like switch")
        assert result["threshold"] == 0.2
        
        # Test "related" keyword
        result = query_parser.parse("related to security")
        assert result["threshold"] == 0.4
        
        # Test default
        result = query_parser.parse("bedroom light")
        assert result["threshold"] == 0.3
    
    def test_combined_keywords(self, query_parser):
        """Test queries with multiple keywords."""
        result = query_parser.parse("show all exact devices like switches")
        assert result["entity_types"] == ["devices"]
        assert result["top_k"] == 50  # "all" takes precedence
        assert result["threshold"] == 0.7  # "exact" takes precedence over "like"
    
    def test_case_insensitive_parsing(self, query_parser):
        """Test that parsing is case insensitive."""
        result1 = query_parser.parse("FIND ALL LIGHTS")
        result2 = query_parser.parse("find all lights")
        
        assert result1["entity_types"] == result2["entity_types"]
        assert result1["top_k"] == result2["top_k"]
        assert result1["threshold"] == result2["threshold"]