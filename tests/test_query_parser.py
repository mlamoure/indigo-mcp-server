"""
Tests for the query parser.
"""

import pytest
from mcp_server.tools.search_entities.query_parser import QueryParser


class TestQueryParser:
    """Test cases for the QueryParser class."""
    
    def test_parse_device_query(self, query_parser):
        """Test parsing device-specific queries now searches all entity types."""
        result = query_parser.parse("find all lights")
        assert result["entity_types"] == ["devices", "variables", "actions"]
        assert result["top_k"] == 50  # "all" keyword
        
        result = query_parser.parse("show me switches")
        assert result["entity_types"] == ["devices", "variables", "actions"]
        
        result = query_parser.parse("dimmer in living room")
        assert result["entity_types"] == ["devices", "variables", "actions"]
    
    def test_parse_variable_query(self, query_parser):
        """Test parsing variable-specific queries now searches all entity types."""
        result = query_parser.parse("house mode variable")
        assert result["entity_types"] == ["devices", "variables", "actions"]
        
        result = query_parser.parse("show all vars")
        assert result["entity_types"] == ["devices", "variables", "actions"]
        assert result["top_k"] == 50  # "all" keyword
    
    def test_parse_action_query(self, query_parser):
        """Test parsing action-specific queries now searches all entity types."""
        result = query_parser.parse("good night scene")
        assert result["entity_types"] == ["devices", "variables", "actions"]
        
        result = query_parser.parse("list all actions")
        assert result["entity_types"] == ["devices", "variables", "actions"]
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
        assert result["threshold"] == 0.15
    
    def test_combined_keywords(self, query_parser):
        """Test queries with multiple keywords."""
        result = query_parser.parse("show all exact devices like switches")
        assert result["entity_types"] == ["devices", "variables", "actions"]
        assert result["top_k"] == 50  # "all" takes precedence
        assert result["threshold"] == 0.7  # "exact" takes precedence over "like"
    
    def test_case_insensitive_parsing(self, query_parser):
        """Test that parsing is case insensitive."""
        result1 = query_parser.parse("FIND ALL LIGHTS")
        result2 = query_parser.parse("find all lights")
        
        assert result1["entity_types"] == result2["entity_types"]
        assert result1["top_k"] == result2["top_k"]
        assert result1["threshold"] == result2["threshold"]


class TestQueryParserEnhancedFeatures:
    """Test cases for the enhanced QueryParser features."""
    
    def test_parse_with_device_types_parameter(self, query_parser):
        """Test parsing with explicit device_types parameter."""
        result = query_parser.parse("find lights", device_types=["dimmer", "relay"])
        
        assert result["device_types"] == ["dimmer", "relay"]
        assert result["entity_types"] == ["devices"]  # Should detect devices from query
        assert result["top_k"] == 10  # Default
        assert result["threshold"] == 0.15  # Default
    
    def test_parse_with_entity_types_parameter(self, query_parser):
        """Test parsing with explicit entity_types parameter."""
        result = query_parser.parse("search query", entity_types=["device", "variable"])
        
        assert result["entity_types"] == ["devices", "variables"]  # Should convert to plural
        assert result["device_types"] == []  # Default empty
        assert result["top_k"] == 10  # Default
        assert result["threshold"] == 0.15  # Default
    
    def test_parse_with_both_parameters(self, query_parser):
        """Test parsing with both device_types and entity_types parameters."""
        result = query_parser.parse(
            "find stuff", 
            device_types=["sensor", "thermostat"],
            entity_types=["device"]
        )
        
        assert result["device_types"] == ["sensor", "thermostat"]
        assert result["entity_types"] == ["devices"]  # Singular to plural conversion
        assert result["top_k"] == 10  # Default
        assert result["threshold"] == 0.15  # Default
    
    def test_entity_type_singular_to_plural_conversion(self, query_parser):
        """Test conversion of singular entity types to plural."""
        test_cases = [
            (["device"], ["devices"]),
            (["variable"], ["variables"]),
            (["action"], ["actions"]),
            (["device", "variable"], ["devices", "variables"]),
            (["device", "variable", "action"], ["devices", "variables", "actions"])
        ]
        
        for input_types, expected_output in test_cases:
            result = query_parser.parse("test", entity_types=input_types)
            assert result["entity_types"] == expected_output
    
    def test_explicit_entity_types_override_query_parsing(self, query_parser):
        """Test that explicit entity_types parameter overrides query-based detection."""
        # Query contains "devices" keyword but entity_types parameter should override
        result = query_parser.parse("find all devices", entity_types=["variable"])
        
        assert result["entity_types"] == ["variables"]  # Should use parameter, not query detection
        assert result["top_k"] == 50  # Should still detect "all" from query
    
    def test_device_types_parameter_with_empty_list(self, query_parser):
        """Test device_types parameter with empty list."""
        result = query_parser.parse("test query", device_types=[])
        
        assert result["device_types"] == []
        assert result["entity_types"] == ["devices", "variables", "actions"]  # Default
    
    def test_entity_types_parameter_with_empty_list(self, query_parser):
        """Test entity_types parameter with empty list."""
        result = query_parser.parse("test query", entity_types=[])
        
        assert result["entity_types"] == []  # Should use empty list
        assert result["device_types"] == []  # Default
    
    def test_none_parameters_use_defaults(self, query_parser):
        """Test that None parameters use default behavior."""
        result = query_parser.parse("find all lights", device_types=None, entity_types=None)
        
        # Should behave like original parse method
        assert result["device_types"] == []  # Default empty
        assert result["entity_types"] == ["devices", "variables", "actions"]  # Now searches all entity types
        assert result["top_k"] == 50  # Should detect "all" from query
    
    def test_preserve_query_based_parameters_when_not_overridden(self, query_parser):
        """Test that query-based parameter detection still works when not overridden."""
        result = query_parser.parse(
            "show few exact devices", 
            device_types=["dimmer"]  # Only override device_types
        )
        
        assert result["device_types"] == ["dimmer"]  # From parameter
        assert result["entity_types"] == ["devices"]  # From query detection
        assert result["top_k"] == 5  # From query detection ("few")
        assert result["threshold"] == 0.7  # From query detection ("exact")
    
    def test_backward_compatibility(self, query_parser):
        """Test that existing functionality remains unchanged."""
        # Test original method signature
        result_old = query_parser.parse("find all exact lights")
        result_new = query_parser.parse("find all exact lights", device_types=None, entity_types=None)
        
        # Results should be identical
        assert result_old["entity_types"] == result_new["entity_types"]
        assert result_old["top_k"] == result_new["top_k"]
        assert result_old["threshold"] == result_new["threshold"]
        assert result_old["device_types"] == result_new["device_types"]
    
    def test_device_types_parameter_validation_ready(self, query_parser):
        """Test that device_types parameter accepts various formats."""
        # Test single device type
        result = query_parser.parse("test", device_types=["dimmer"])
        assert result["device_types"] == ["dimmer"]
        
        # Test multiple device types
        result = query_parser.parse("test", device_types=["dimmer", "sensor", "relay"])
        assert result["device_types"] == ["dimmer", "sensor", "relay"]
        
        # Test empty list
        result = query_parser.parse("test", device_types=[])
        assert result["device_types"] == []
    
    def test_entity_types_parameter_validation_ready(self, query_parser):
        """Test that entity_types parameter accepts various formats."""
        # Test single entity type
        result = query_parser.parse("test", entity_types=["device"])
        assert result["entity_types"] == ["devices"]
        
        # Test multiple entity types
        result = query_parser.parse("test", entity_types=["device", "variable"])
        assert result["entity_types"] == ["devices", "variables"]
        
        # Test empty list
        result = query_parser.parse("test", entity_types=[])
        assert result["entity_types"] == []
    
    def test_malformed_entity_types_handled_gracefully(self, query_parser):
        """Test that malformed entity types are handled gracefully."""
        # Test unknown entity types (should pass through unchanged)
        result = query_parser.parse("test", entity_types=["unknown", "device"])
        assert result["entity_types"] == ["unknown", "devices"]  # Only device gets converted
        
        # Test already plural entity types (should pass through unchanged)
        result = query_parser.parse("test", entity_types=["devices", "variables"])
        assert result["entity_types"] == ["devices", "variables"]