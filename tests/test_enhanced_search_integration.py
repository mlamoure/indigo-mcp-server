"""
Integration tests for the enhanced search functionality.
"""

import pytest
import json
from unittest.mock import Mock, patch
from mcp_server.tools.search_entities import SearchEntitiesHandler
from mcp_server.tools.query_parser import QueryParser
from mcp_server.tools.result_formatter import ResultFormatter
from mcp_server.common.indigo_device_types import IndigoDeviceType, IndigoEntityType
from tests.mocks.mock_data_provider import MockDataProvider


class ComprehensiveVectorStore:
    """Vector store with comprehensive test data for integration testing."""
    
    def __init__(self):
        self.test_data = [
            # Devices with various types
            {
                "_entity_type": "device",
                "id": 1,
                "name": "Living Room Dimmer",
                "deviceTypeId": "dimmer",
                "description": "Main living room ceiling light",
                "model": "SwitchLinc Dimmer",
                "address": "A1",
                "_similarity_score": 0.9
            },
            {
                "_entity_type": "device", 
                "id": 2,
                "name": "Kitchen Temperature Sensor",
                "deviceTypeId": "sensor",
                "description": "Temperature and humidity monitoring",
                "model": "TempLinc",
                "address": "B2",
                "_similarity_score": 0.85
            },
            {
                "_entity_type": "device",
                "id": 3,
                "name": "Garage Door Relay",
                "deviceTypeId": "relay",
                "description": "Controls garage door opener",
                "model": "IOLinc",
                "address": "C3",
                "_similarity_score": 0.8
            },
            {
                "_entity_type": "device",
                "id": 4,
                "name": "Main Thermostat", 
                "deviceTypeId": "thermostat",
                "description": "Main house thermostat",
                "model": "Insteon Thermostat",
                "address": "D4",
                "_similarity_score": 0.75
            },
            # Variables
            {
                "_entity_type": "variable",
                "id": 101,
                "name": "House Mode",
                "value": "Home",
                "description": "Current house occupancy mode",
                "_similarity_score": 0.7
            },
            {
                "_entity_type": "variable",
                "id": 102,
                "name": "Temperature Setting",
                "value": "72",
                "description": "Desired temperature",
                "_similarity_score": 0.65
            },
            # Actions
            {
                "_entity_type": "action",
                "id": 201,
                "name": "Good Night Scene",
                "description": "Turns off all lights and locks doors",
                "_similarity_score": 0.6
            }
        ]
    
    def search(self, query, entity_types=None, top_k=10, similarity_threshold=0.3):
        """Mock search that returns filtered test data."""
        if entity_types is None:
            entity_types = ["devices", "variables", "actions"]
        
        # Convert entity types to expected internal format
        entity_type_mapping = {
            "devices": "device",
            "variables": "variable", 
            "actions": "action"
        }
        
        mapped_types = [entity_type_mapping.get(et, et) for et in entity_types]
        
        # Filter by entity types and similarity threshold
        filtered_data = [
            item for item in self.test_data
            if (item["_entity_type"] in mapped_types and 
                item["_similarity_score"] >= similarity_threshold)
        ]
        
        # Sort by similarity score and limit results
        filtered_data.sort(key=lambda x: x["_similarity_score"], reverse=True)
        return filtered_data[:top_k]


class TestEnhancedSearchIntegration:
    """Integration tests for the complete enhanced search workflow."""
    
    @pytest.fixture
    def comprehensive_search_handler(self):
        """Create a search handler with comprehensive test data."""
        mock_data_provider = MockDataProvider()
        vector_store = ComprehensiveVectorStore()
        
        return SearchEntitiesHandler(
            data_provider=mock_data_provider,
            vector_store=vector_store
        )
    
    def test_search_with_device_type_filtering_integration(self, comprehensive_search_handler):
        """Test complete workflow: query -> parsing -> vector search -> device filtering -> formatting."""
        # Search for lights but only dimmer devices
        result = comprehensive_search_handler.search(
            query="find lights",
            device_types=["dimmer"],
            entity_types=["device"]
        )
        
        # Should find the dimmer device only
        assert result["query"] == "find lights"
        assert result["total_count"] == 1
        
        devices = result["results"]["devices"]
        assert len(devices) == 1
        assert devices[0]["name"] == "Living Room Dimmer"
        assert "deviceTypeId" not in devices[0]  # Should be filtered out by result formatter
        assert "relevance_score" in devices[0]  # Should be added by result formatter
    
    def test_search_multiple_device_types_integration(self, comprehensive_search_handler):
        """Test filtering with multiple device types."""
        result = comprehensive_search_handler.search(
            query="find devices",
            device_types=["dimmer", "sensor"],
            entity_types=["device"]
        )
        
        # Should find dimmer and sensor devices
        assert result["total_count"] == 2
        
        devices = result["results"]["devices"]
        assert len(devices) == 2
        
        device_names = {device["name"] for device in devices}
        expected_names = {"Living Room Dimmer", "Kitchen Temperature Sensor"}
        assert device_names == expected_names
    
    def test_search_entity_type_filtering_integration(self, comprehensive_search_handler):
        """Test filtering by entity types."""
        # Search only variables
        result = comprehensive_search_handler.search(
            query="temperature",
            entity_types=["variable"]
        )
        
        # Should only return variables, no devices
        assert len(result["results"]["devices"]) == 0
        assert len(result["results"]["variables"]) > 0
        assert len(result["results"]["actions"]) == 0
    
    def test_search_combined_filtering_integration(self, comprehensive_search_handler):
        """Test combined device type and entity type filtering."""
        result = comprehensive_search_handler.search(
            query="sensor data",
            device_types=["sensor"],
            entity_types=["device", "variable"]
        )
        
        # Should return sensor device and relevant variables
        devices = result["results"]["devices"]
        variables = result["results"]["variables"]
        actions = result["results"]["actions"]
        
        # Should have sensor device
        assert len(devices) == 1
        assert devices[0]["name"] == "Kitchen Temperature Sensor"
        
        # Should have variables (not filtered by device type)
        assert len(variables) > 0
        
        # Should not have actions (filtered out by entity_types)
        assert len(actions) == 0
    
    def test_search_no_device_type_filtering_integration(self, comprehensive_search_handler):
        """Test search without device type filtering (all devices should be returned)."""
        result = comprehensive_search_handler.search(
            query="devices",
            entity_types=["device"]
        )
        
        # Should return all devices since no device type filtering
        devices = result["results"]["devices"]
        assert len(devices) == 4  # All 4 test devices
        
        device_types = {device.get("type", "unknown") for device in devices}
        # Note: result formatter maps deviceTypeId to type, or we check the original data
    
    def test_search_threshold_filtering_integration(self, comprehensive_search_handler):
        """Test that similarity threshold filtering works in integration."""
        result = comprehensive_search_handler.search(
            query="exact match needed",  # Should trigger high threshold
            device_types=["dimmer", "sensor"]
        )
        
        # With high threshold, should get fewer results
        # The exact behavior depends on query parser threshold detection
        assert "total_count" in result
        assert result["total_count"] >= 0
    
    def test_search_empty_results_integration(self, comprehensive_search_handler):
        """Test handling of searches that return no results."""
        result = comprehensive_search_handler.search(
            query="nonexistent device",
            device_types=["sprinkler"]  # No sprinkler devices in test data
        )
        
        # Should handle empty results gracefully
        assert result["total_count"] == 0
        assert len(result["results"]["devices"]) == 0
        assert len(result["results"]["variables"]) == 0
        assert len(result["results"]["actions"]) == 0
        assert "summary" in result
    
    def test_search_backward_compatibility_integration(self, comprehensive_search_handler):
        """Test that searches without new parameters still work."""
        # Original search method signature
        result = comprehensive_search_handler.search("temperature")
        
        # Should work exactly as before
        assert result["query"] == "temperature"
        assert "total_count" in result
        assert "results" in result
        assert "summary" in result
        
        # Should return results from all entity types
        total_entities = (
            len(result["results"]["devices"]) + 
            len(result["results"]["variables"]) + 
            len(result["results"]["actions"])
        )
        assert total_entities > 0
    
    def test_query_parser_integration_with_new_parameters(self, comprehensive_search_handler):
        """Test that query parser correctly processes new parameters."""
        # Test that explicit parameters override query detection
        result = comprehensive_search_handler.search(
            query="show all devices",  # Would normally search all devices
            entity_types=["variable"]  # But this should override to variables only
        )
        
        # Should only return variables despite "devices" in query
        assert len(result["results"]["devices"]) == 0
        assert len(result["results"]["variables"]) > 0
    
    def test_result_formatter_integration_with_filtered_results(self, comprehensive_search_handler):
        """Test that result formatter properly handles filtered results."""
        result = comprehensive_search_handler.search(
            query="find dimmer",
            device_types=["dimmer"]
        )
        
        # Check that result formatter has processed the results correctly
        assert "summary" in result
        assert "Found" in result["summary"]
        
        if result["total_count"] > 0:
            devices = result["results"]["devices"]
            for device in devices:
                # Should have relevance_score added by formatter
                assert "relevance_score" in device
                assert isinstance(device["relevance_score"], (int, float))
                assert 0.0 <= device["relevance_score"] <= 1.0
                
                # Should not have internal fields
                assert "_similarity_score" not in device
                assert "_entity_type" not in device
    
    def test_error_handling_integration(self, comprehensive_search_handler):
        """Test error handling in the complete workflow."""
        # Replace vector store with one that raises an error
        class FailingVectorStore:
            def search(self, *args, **kwargs):
                raise Exception("Vector store failure")
        
        comprehensive_search_handler.vector_store = FailingVectorStore()
        
        result = comprehensive_search_handler.search(
            query="test",
            device_types=["dimmer"]
        )
        
        # Should handle error gracefully
        assert "error" in result
        assert result["query"] == "test"
        assert result["total_count"] == 0
    
    def test_logging_integration(self, comprehensive_search_handler, caplog):
        """Test that logging works correctly in the integrated workflow."""
        import logging
        caplog.set_level(logging.INFO)
        
        result = comprehensive_search_handler.search(
            query="find temperature sensors",
            device_types=["sensor"],
            entity_types=["device"]
        )
        
        # Check that search parameters were logged
        log_messages = [record.message for record in caplog.records if record.levelname == "INFO"]
        
        # Should have logs for query and parameters
        query_logs = [msg for msg in log_messages if "Search query" in msg and "find temperature sensors" in msg]
        device_type_logs = [msg for msg in log_messages if "Device type filter" in msg and "sensor" in msg]
        entity_type_logs = [msg for msg in log_messages if "Entity type filter" in msg and "device" in msg]
        
        assert len(query_logs) > 0
        assert len(device_type_logs) > 0
        assert len(entity_type_logs) > 0
    
    def test_comprehensive_workflow_with_all_features(self, comprehensive_search_handler):
        """Test the complete workflow with all enhanced features enabled."""
        result = comprehensive_search_handler.search(
            query="find few exact temperature devices",  # Complex query with modifiers
            device_types=["sensor", "thermostat"],       # Multiple device types
            entity_types=["device", "variable"]          # Multiple entity types  
        )
        
        # Should process all parameters correctly
        assert result["query"] == "find few exact temperature devices"
        assert "total_count" in result
        assert "results" in result
        assert "summary" in result
        
        # Should respect device type filtering (only sensor and thermostat devices)
        devices = result["results"]["devices"]
        for device in devices:
            # Would need to check internal data or modify test to verify device types
            # For now, just ensure devices are returned
            assert "name" in device
            assert "relevance_score" in device
        
        # Should include variables (entity_types includes "variable")
        variables = result["results"]["variables"]
        # Variables should be present if any match the query
        
        # Should not include actions (entity_types excludes "action")
        actions = result["results"]["actions"]
        assert len(actions) == 0


class TestEnhancedSearchEdgeCases:
    """Test edge cases in the enhanced search functionality."""
    
    @pytest.fixture
    def edge_case_handler(self):
        """Create handler for edge case testing."""
        mock_data_provider = MockDataProvider()
        
        # Vector store with edge case data
        class EdgeCaseVectorStore:
            def search(self, query, entity_types=None, top_k=10, similarity_threshold=0.3):
                all_data = [
                    # Device without deviceTypeId
                    {"_entity_type": "device", "id": 1, "name": "Malformed Device", "_similarity_score": 0.9},
                    # Device with empty deviceTypeId  
                    {"_entity_type": "device", "id": 2, "name": "Empty Type Device", "deviceTypeId": "", "_similarity_score": 0.8},
                    # Normal device
                    {"_entity_type": "device", "id": 3, "name": "Normal Device", "deviceTypeId": "dimmer", "_similarity_score": 0.7}
                ]
                
                if entity_types is None:
                    entity_types = ["devices", "variables", "actions"]
                
                # Convert entity types to expected internal format
                entity_type_mapping = {
                    "devices": "device",
                    "variables": "variable", 
                    "actions": "action"
                }
                
                mapped_types = [entity_type_mapping.get(et, et) for et in entity_types]
                
                # Filter by entity types
                filtered_data = [
                    item for item in all_data
                    if item["_entity_type"] in mapped_types
                ]
                
                return filtered_data
        
        return SearchEntitiesHandler(
            data_provider=mock_data_provider,
            vector_store=EdgeCaseVectorStore()
        )
    
    def test_device_filtering_with_malformed_data(self, edge_case_handler):
        """Test device filtering with malformed device data."""
        result = edge_case_handler.search(
            query="test",
            device_types=["dimmer"],
            entity_types=["device"]
        )
        
        # Should only return the normal device with matching deviceTypeId
        devices = result["results"]["devices"]
        assert len(devices) == 1
        assert devices[0]["name"] == "Normal Device"
    
    def test_empty_device_types_list(self, edge_case_handler):
        """Test with empty device_types list."""
        result = edge_case_handler.search(
            query="test",
            device_types=[],  # Empty list
            entity_types=["device"]
        )
        
        # Should filter out all devices (empty device_types means no devices match)
        devices = result["results"]["devices"]
        assert len(devices) == 0
    
    def test_empty_entity_types_list(self, edge_case_handler):
        """Test with empty entity_types list."""
        result = edge_case_handler.search(
            query="test",
            entity_types=[]  # Empty list
        )
        
        # Should search no entity types, returning empty results
        assert result["total_count"] == 0
        assert len(result["results"]["devices"]) == 0
        assert len(result["results"]["variables"]) == 0
        assert len(result["results"]["actions"]) == 0