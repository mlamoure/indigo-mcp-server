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
    
    def test_search_device_specific(self, search_handler, populated_real_vector_store):
        """Test device-specific searches."""
        search_handler.vector_store = populated_real_vector_store
        
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
    
    def test_search_integration_with_result_formatter(self, search_handler, populated_real_vector_store):
        """Test integration between search handler and result formatter."""
        search_handler.vector_store = populated_real_vector_store
        
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


class TestSearchEntitiesHandlerEnhancedFeatures:
    """Test cases for the enhanced SearchEntitiesHandler features."""
    
    def test_search_with_device_types_parameter(self, search_handler_with_mocks, populated_mock_vector_store):
        """Test search with device_types parameter."""
        search_handler_with_mocks.vector_store = populated_mock_vector_store
        
        # Test filtering by dimmer devices only
        result = search_handler_with_mocks.search("light", device_types=["dimmer"])
        
        assert result["query"] == "light"
        assert "total_count" in result
        assert "results" in result
        
        # Should have proper structure
        assert "devices" in result["results"]
        assert "variables" in result["results"]
        assert "actions" in result["results"]
    
    def test_search_with_entity_types_parameter(self, search_handler_with_mocks, populated_mock_vector_store):
        """Test search with entity_types parameter."""
        search_handler_with_mocks.vector_store = populated_mock_vector_store
        
        # Test searching only devices
        result = search_handler_with_mocks.search("test", entity_types=["device"])
        
        assert result["query"] == "test"
        assert "total_count" in result
        assert "results" in result
    
    def test_search_with_both_parameters(self, search_handler_with_mocks, populated_mock_vector_store):
        """Test search with both device_types and entity_types parameters."""
        search_handler_with_mocks.vector_store = populated_mock_vector_store
        
        result = search_handler_with_mocks.search(
            "test", 
            device_types=["sensor"],
            entity_types=["device"]
        )
        
        assert result["query"] == "test"
        assert "total_count" in result
        assert "results" in result
    
    def test_filter_devices_by_type_basic(self, search_handler_with_mocks):
        """Test basic device type filtering."""
        # Create test data with different device types
        test_results = [
            {"_entity_type": "device", "deviceTypeId": "dimmer", "name": "Living Room Dimmer", "id": 1},
            {"_entity_type": "device", "deviceTypeId": "sensor", "name": "Temperature Sensor", "id": 2},
            {"_entity_type": "device", "deviceTypeId": "relay", "name": "Kitchen Light", "id": 3},
            {"_entity_type": "variable", "name": "House Mode", "id": 101},
            {"_entity_type": "action", "name": "Good Night", "id": 201}
        ]
        
        # Filter for dimmer devices only
        filtered = search_handler_with_mocks._filter_devices_by_type(test_results, ["dimmer"])
        
        # Should have 1 dimmer device + 1 variable + 1 action (non-devices pass through)
        assert len(filtered) == 3
        
        # Check that only the dimmer device remains from devices
        device_results = [r for r in filtered if r.get("_entity_type") == "device"]
        assert len(device_results) == 1
        assert device_results[0]["deviceTypeId"] == "dimmer"
        assert device_results[0]["name"] == "Living Room Dimmer"
        
        # Check that non-device entities pass through unchanged
        variable_results = [r for r in filtered if r.get("_entity_type") == "variable"]
        action_results = [r for r in filtered if r.get("_entity_type") == "action"]
        assert len(variable_results) == 1
        assert len(action_results) == 1
    
    def test_filter_devices_by_multiple_types(self, search_handler_with_mocks):
        """Test filtering by multiple device types."""
        test_results = [
            {"_entity_type": "device", "deviceTypeId": "dimmer", "name": "Living Room Dimmer", "id": 1},
            {"_entity_type": "device", "deviceTypeId": "sensor", "name": "Temperature Sensor", "id": 2},
            {"_entity_type": "device", "deviceTypeId": "relay", "name": "Kitchen Light", "id": 3},
            {"_entity_type": "device", "deviceTypeId": "thermostat", "name": "Main Thermostat", "id": 4},
        ]
        
        # Filter for dimmer and sensor devices
        filtered = search_handler_with_mocks._filter_devices_by_type(test_results, ["dimmer", "sensor"])
        
        assert len(filtered) == 2
        device_types = {r["deviceTypeId"] for r in filtered}
        assert device_types == {"dimmer", "sensor"}
    
    def test_filter_devices_by_type_no_matches(self, search_handler_with_mocks):
        """Test filtering when no devices match the type."""
        test_results = [
            {"_entity_type": "device", "deviceTypeId": "dimmer", "name": "Living Room Dimmer", "id": 1},
            {"_entity_type": "device", "deviceTypeId": "sensor", "name": "Temperature Sensor", "id": 2},
            {"_entity_type": "variable", "name": "House Mode", "id": 101},
        ]
        
        # Filter for a device type that doesn't exist
        filtered = search_handler_with_mocks._filter_devices_by_type(test_results, ["thermostat"])
        
        # Should only have the variable (non-device entities pass through)
        assert len(filtered) == 1
        assert filtered[0]["_entity_type"] == "variable"
    
    def test_filter_devices_by_type_missing_device_type_id(self, search_handler_with_mocks):
        """Test filtering with devices that don't have deviceTypeId field."""
        test_results = [
            {"_entity_type": "device", "deviceTypeId": "dimmer", "name": "Valid Dimmer", "id": 1},
            {"_entity_type": "device", "name": "Missing DeviceTypeId", "id": 2},  # No deviceTypeId
            {"_entity_type": "variable", "name": "House Mode", "id": 101},
        ]
        
        filtered = search_handler_with_mocks._filter_devices_by_type(test_results, ["dimmer"])
        
        # Should have 1 dimmer device + 1 variable (device without deviceTypeId is filtered out)
        assert len(filtered) == 2
        device_results = [r for r in filtered if r.get("_entity_type") == "device"]
        assert len(device_results) == 1
        assert device_results[0]["deviceTypeId"] == "dimmer"
    
    def test_filter_devices_by_type_empty_device_types(self, search_handler_with_mocks):
        """Test filtering with empty device types list."""
        test_results = [
            {"_entity_type": "device", "deviceTypeId": "dimmer", "name": "Living Room Dimmer", "id": 1},
            {"_entity_type": "variable", "name": "House Mode", "id": 101},
        ]
        
        # Empty device types should return only non-device entities
        filtered = search_handler_with_mocks._filter_devices_by_type(test_results, [])
        
        assert len(filtered) == 1
        assert filtered[0]["_entity_type"] == "variable"
    
    def test_filter_devices_by_type_no_devices_in_results(self, search_handler_with_mocks):
        """Test filtering when results contain no device entities."""
        test_results = [
            {"_entity_type": "variable", "name": "House Mode", "id": 101},
            {"_entity_type": "action", "name": "Good Night", "id": 201}
        ]
        
        filtered = search_handler_with_mocks._filter_devices_by_type(test_results, ["dimmer"])
        
        # Should return all results unchanged (no devices to filter)
        assert len(filtered) == 2
        assert filtered == test_results
    
    def test_search_integration_with_device_filtering(self, search_handler_with_mocks):
        """Test that device filtering is properly integrated into search workflow."""
        # Create a mock vector store that returns predictable results
        class PredictableVectorStore:
            def search(self, query, entity_types=None, top_k=10, similarity_threshold=0.7):
                return [
                    {"_entity_type": "device", "deviceTypeId": "dimmer", "name": "Living Room Dimmer", "id": 1, "_similarity_score": 0.9},
                    {"_entity_type": "device", "deviceTypeId": "sensor", "name": "Temperature Sensor", "id": 2, "_similarity_score": 0.8},
                    {"_entity_type": "variable", "name": "House Mode", "id": 101, "_similarity_score": 0.7}
                ]
        
        search_handler_with_mocks.vector_store = PredictableVectorStore()
        
        # Search with device type filtering
        result = search_handler_with_mocks.search("test", device_types=["dimmer"])
        
        # Should have filtered out the sensor device but kept the variable
        devices = result["results"]["devices"]
        variables = result["results"]["variables"]
        
        # Should have 1 device (dimmer) and 1 variable
        assert len(devices) == 1
        assert len(variables) == 1
        assert devices[0]["name"] == "Living Room Dimmer"
        assert variables[0]["name"] == "House Mode"
    
    def test_log_search_results_method(self, search_handler_with_mocks, caplog):
        """Test the _log_search_results method."""
        import logging
        caplog.set_level(logging.INFO)
        
        grouped_results = {
            "devices": [
                {"name": "Device 1", "id": 1},
                {"name": "Device 2", "id": 2}
            ],
            "variables": [
                {"name": "Variable 1", "id": 101}
            ],
            "actions": []  # Empty list should not be logged
        }
        
        search_handler_with_mocks._log_search_results(grouped_results)
        
        # Check that appropriate log messages were created
        log_messages = [record.message for record in caplog.records if record.levelname == "INFO"]
        
        # Should have logs for devices and variables but not actions (empty)
        device_log = [msg for msg in log_messages if "Found 2 devices" in msg]
        variable_log = [msg for msg in log_messages if "Found 1 variables" in msg]
        action_log = [msg for msg in log_messages if "actions" in msg]
        
        assert len(device_log) == 1
        assert len(variable_log) == 1
        assert len(action_log) == 0  # No log for empty actions list
        
        # Check that device names are included in the log
        assert "Device 1, Device 2" in device_log[0]
        assert "Variable 1" in variable_log[0]
    
    def test_log_search_results_with_many_items(self, search_handler_with_mocks, caplog):
        """Test logging with more than 10 items (should show 'and X more' message)."""
        import logging
        caplog.set_level(logging.INFO)
        
        # Create 15 devices to test the "and X more" functionality
        devices = [{"name": f"Device {i}", "id": i} for i in range(1, 16)]
        
        grouped_results = {"devices": devices, "variables": [], "actions": []}
        
        search_handler_with_mocks._log_search_results(grouped_results)
        
        log_messages = [record.message for record in caplog.records if record.levelname == "INFO"]
        device_log = [msg for msg in log_messages if "Found 15 devices" in msg][0]
        
        # Should show first 10 devices and "and 5 more"
        assert "Device 1, Device 2" in device_log  # First few devices
        assert "Device 10" in device_log  # 10th device
        assert "Device 11" not in device_log  # 11th device should not be shown
        assert "and 5 more" in device_log  # Should show "and X more" message
    
    def test_search_backward_compatibility(self, search_handler_with_mocks, populated_mock_vector_store):
        """Test that existing search functionality still works without new parameters."""
        search_handler_with_mocks.vector_store = populated_mock_vector_store
        
        # Test original search method signature
        result = search_handler_with_mocks.search("light")
        
        # Should work exactly as before
        assert result["query"] == "light"
        assert "total_count" in result
        assert "results" in result
        assert "devices" in result["results"]
        assert "variables" in result["results"]
        assert "actions" in result["results"]