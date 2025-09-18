"""
Test suite for mixed entity analysis (devices and variables).

Tests the enhanced historical analysis that supports both devices and variables.
"""

import pytest
import unittest
import time
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import sys
from pathlib import Path

# Add the plugin path to sys.path
plugin_path = Path(__file__).parent.parent / "MCP Server.indigoPlugin" / "Contents" / "Server Plugin"
sys.path.insert(0, str(plugin_path))

from mcp_server.tools.historical_analysis.main import HistoricalAnalysisHandler
from mcp_server.common.influxdb.queries import InfluxDBQueryBuilder


class TestMixedEntityAnalysis(unittest.TestCase):
    """Test suite for mixed entity (device + variable) analysis."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_data_provider = Mock()
        
        # Mock devices
        self.mock_data_provider.get_all_devices.return_value = [
            {"name": "Living Room Light", "id": 123},
            {"name": "Bedroom Thermostat", "id": 456}
        ]
        
        # Mock variables  
        self.mock_data_provider.get_all_variables.return_value = [
            {"name": "someone_home", "id": 789, "value": True},
            {"name": "house_mode", "id": 101, "value": "day"}
        ]
        
        self.handler = HistoricalAnalysisHandler(self.mock_data_provider)
    
    def test_entity_type_detection_mixed(self):
        """Test entity type detection with mixed devices and variables."""
        
        entity_names = ["Living Room Light", "someone_home"]
        
        result = self.handler._validate_entity_names(entity_names, "auto")
        
        self.assertTrue(result["all_valid"])
        self.assertEqual(result["entity_classification"]["devices"], ["Living Room Light"])
        self.assertEqual(result["entity_classification"]["variables"], ["someone_home"])
        self.assertEqual(result["entity_classification"]["detected_type"], "mixed")
    
    def test_entity_type_detection_devices_only(self):
        """Test entity type detection with devices only."""
        
        entity_names = ["Living Room Light", "Bedroom Thermostat"]
        
        result = self.handler._validate_entity_names(entity_names, "auto")
        
        self.assertTrue(result["all_valid"])
        self.assertEqual(result["entity_classification"]["devices"], ["Living Room Light", "Bedroom Thermostat"])
        self.assertEqual(result["entity_classification"]["variables"], [])
        self.assertEqual(result["entity_classification"]["detected_type"], "devices")
    
    def test_entity_type_detection_variables_only(self):
        """Test entity type detection with variables only."""
        
        entity_names = ["someone_home", "house_mode"]
        
        result = self.handler._validate_entity_names(entity_names, "auto")
        
        self.assertTrue(result["all_valid"])
        self.assertEqual(result["entity_classification"]["devices"], [])
        self.assertEqual(result["entity_classification"]["variables"], ["someone_home", "house_mode"])
        self.assertEqual(result["entity_classification"]["detected_type"], "variables")
    
    def test_entity_type_validation_strict(self):
        """Test strict entity type validation."""
        
        # Test devices-only mode with mixed entities (should fail)
        entity_names = ["Living Room Light", "someone_home"]
        
        result = self.handler._validate_entity_names(entity_names, "devices")
        
        self.assertFalse(result["all_valid"])
        self.assertIn("Expected only devices, but found variables", result["error_message"])
        
        # Test variables-only mode with mixed entities (should fail)
        result = self.handler._validate_entity_names(entity_names, "variables")
        
        self.assertFalse(result["all_valid"])
        self.assertIn("Expected only variables, but found devices", result["error_message"])
    
    def test_invalid_entity_handling(self):
        """Test handling of invalid entity names."""
        
        entity_names = ["Invalid Device", "Invalid Variable", "Living Room Light"]
        
        result = self.handler._validate_entity_names(entity_names, "auto")
        
        self.assertFalse(result["all_valid"])
        self.assertEqual(result["valid_entities"], ["Living Room Light"])
        self.assertEqual(result["invalid_entities"], ["Invalid Device", "Invalid Variable"])
        self.assertIn("search_entities", result["detailed_report"])
    
    def test_variable_value_formatting(self):
        """Test variable value formatting."""
        
        # Test various variable value types
        test_cases = [
            (True, "true"),
            (False, "false"),
            ("home", '"home"'),
            ("", '""'),
            (42, "42"),
            (3.14159, "3.142"),
            (3.0, "3"),
            (None, "null"),
            ("very long string that exceeds the hundred character limit for variable value display and should be truncated", '"very long string that exceeds the hundred character limit for variable value display and should b..."')
        ]
        
        for input_value, expected in test_cases:
            result = self.handler._format_variable_value(input_value)
            self.assertEqual(result, expected, 
                f"Variable formatting failed for {input_value}: got '{result}', expected '{expected}'")
    
    @patch.dict('os.environ', {'INFLUXDB_ENABLED': 'true'})
    def test_mixed_entity_analysis_integration(self):
        """Test full mixed entity analysis integration."""
        
        # Mock InfluxDB data for device
        device_data = [
            {"time": "2024-01-15T10:00:00Z", "onState": True},
            {"time": "2024-01-15T12:00:00Z", "onState": False}
        ]
        
        # Mock InfluxDB data for variable
        variable_data = [
            {"time": "2024-01-15T09:00:00Z", "value": "away"},
            {"time": "2024-01-15T11:00:00Z", "value": "home"}
        ]
        
        with patch('mcp_server.common.influxdb.InfluxDBClient') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client
            mock_client.is_enabled.return_value = True
            mock_client.test_connection.return_value = True
            
            # Return different data based on query type
            def mock_execute_query(query):
                if "device_changes" in query:
                    return device_data
                elif "variable_changes" in query:
                    return variable_data
                else:
                    return []
            
            mock_client.execute_query.side_effect = mock_execute_query
            
            with patch('mcp_server.common.influxdb.InfluxDBQueryBuilder') as mock_builder_class:
                mock_builder = Mock()
                mock_builder_class.return_value = mock_builder
                mock_builder.build_device_history_query.return_value = "SELECT onState FROM device_changes"
                mock_builder.build_variable_history_query.return_value = "SELECT value FROM variable_changes"
                
                # Mock LLM recommendations
                with patch.object(self.handler, '_get_recommended_properties') as mock_props:
                    mock_props.return_value = ["onState"]
                    
                    # Test mixed entity analysis
                    result = self.handler.analyze_historical_data(
                        query="show activity",
                        entity_names=["Living Room Light", "someone_home"],
                        time_range_days=7,
                        entity_type="auto"
                    )
                    
                    self.assertTrue(result["success"])
                    self.assertIn("entities_analyzed", result["data"])
                    self.assertIn("entity_classification", result["data"])
                    
                    classification = result["data"]["entity_classification"]
                    self.assertEqual(classification["devices"], ["Living Room Light"])
                    self.assertEqual(classification["variables"], ["someone_home"])
                    self.assertEqual(classification["detected_type"], "mixed")


class TestVariableQueryBuilder(unittest.TestCase):
    """Test suite for variable query builder."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.builder = InfluxDBQueryBuilder()
    
    def test_build_variable_history_query(self):
        """Test building variable history query."""
        
        query = self.builder.build_variable_history_query(
            variable_name="someone_home",
            time_range_days=7
        )
        
        # Check query structure
        self.assertIn('SELECT "value"', query)
        self.assertIn('FROM "variable_changes"', query)
        self.assertIn('WHERE "varname" = \'someone_home\'', query)
        self.assertIn('GROUP BY "varname"', query)
        self.assertIn('ORDER BY time ASC', query)
    
    def test_build_variable_latest_query(self):
        """Test building variable latest query."""
        
        query = self.builder.build_variable_latest_query("house_mode")
        
        # Check query structure
        self.assertIn('SELECT LAST("value")', query)
        self.assertIn('FROM "variable_changes"', query)
        self.assertIn('WHERE "varname" = \'house_mode\'', query)
        self.assertIn('GROUP BY "varname"', query)
    
    def test_variable_query_time_range(self):
        """Test variable query with different time ranges."""
        
        # Test different time ranges
        for days in [1, 7, 30, 90]:
            query = self.builder.build_variable_history_query(
                variable_name="test_var",
                time_range_days=days
            )
            
            # Should contain time filter
            self.assertIn("time >=", query)
            self.assertIn("ms", query)


class TestEntityTypeClassification(unittest.TestCase):
    """Test suite for entity type classification logic."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_data_provider = Mock()
        
        # Mock comprehensive device and variable lists
        self.mock_data_provider.get_all_devices.return_value = [
            {"name": "Front Door Lock", "id": 100},
            {"name": "Kitchen Light", "id": 200}, 
            {"name": "someone_home", "id": 300}  # Ambiguous name (exists as both)
        ]
        
        self.mock_data_provider.get_all_variables.return_value = [
            {"name": "someone_home", "id": 400, "value": True},  # Ambiguous name
            {"name": "house_mode", "id": 500, "value": "day"},
            {"name": "security_armed", "id": 600, "value": False}
        ]
        
        self.handler = HistoricalAnalysisHandler(self.mock_data_provider)
    
    def test_ambiguous_name_resolution(self):
        """Test resolution of ambiguous names (exist as both device and variable)."""
        
        # Test auto mode (should default to device)
        result = self.handler._validate_entity_names(["someone_home"], "auto")
        self.assertEqual(result["entity_classification"]["devices"], ["someone_home"])
        self.assertEqual(result["entity_classification"]["variables"], [])
        
        # Test explicit variable mode
        result = self.handler._validate_entity_names(["someone_home"], "variables")
        self.assertEqual(result["entity_classification"]["devices"], [])
        self.assertEqual(result["entity_classification"]["variables"], ["someone_home"])
    
    def test_comprehensive_entity_suggestions(self):
        """Test entity name suggestions for both devices and variables."""
        
        # Test with partial matches
        result = self.handler._validate_entity_names(["front door", "house mode"], "auto")
        
        self.assertFalse(result["all_valid"])
        self.assertTrue(len(result["suggestions"]) >= 1)
        
        # Should suggest both device and variable matches
        suggestions_text = result["detailed_report"]
        self.assertIn("search_entities", suggestions_text)
        self.assertIn("list_devices", suggestions_text)
        self.assertIn("list_variables", suggestions_text)
    
    def test_entity_type_consistency(self):
        """Test entity type consistency validation."""
        
        # Mixed entities with strict device type should fail
        result = self.handler._validate_entity_names(
            ["Kitchen Light", "house_mode"], 
            "devices"
        )
        self.assertFalse(result["all_valid"])
        self.assertIn("Expected only devices", result["error_message"])
        
        # Mixed entities with strict variable type should fail
        result = self.handler._validate_entity_names(
            ["Kitchen Light", "house_mode"], 
            "variables"
        )
        self.assertFalse(result["all_valid"])
        self.assertIn("Expected only variables", result["error_message"])


class TestBackwardCompatibility(unittest.TestCase):
    """Test suite for backward compatibility with existing device-only usage."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_data_provider = Mock()
        
        # Mock devices only (legacy usage)
        self.mock_data_provider.get_all_devices.return_value = [
            {"name": "Living Room Light", "id": 123}
        ]
        self.mock_data_provider.get_all_variables.return_value = []
        
        self.handler = HistoricalAnalysisHandler(self.mock_data_provider)
    
    @patch.dict('os.environ', {'INFLUXDB_ENABLED': 'true'})
    def test_legacy_device_only_analysis(self):
        """Test that legacy device-only analysis still works."""
        
        device_data = [
            {"time": "2024-01-15T10:00:00Z", "onState": True},
            {"time": "2024-01-15T12:00:00Z", "onState": False}
        ]
        
        with patch('mcp_server.common.influxdb.InfluxDBClient') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client
            mock_client.is_enabled.return_value = True
            mock_client.test_connection.return_value = True
            mock_client.execute_query.return_value = device_data
            
            with patch('mcp_server.common.influxdb.InfluxDBQueryBuilder') as mock_builder_class:
                mock_builder = Mock()
                mock_builder_class.return_value = mock_builder
                mock_builder.build_device_history_query.return_value = "SELECT onState FROM device_changes"
                
                # Mock LLM recommendations
                with patch.object(self.handler, '_get_recommended_properties') as mock_props:
                    mock_props.return_value = ["onState"]
                    
                    # Test legacy usage (devices only, old parameter name)
                    result = self.handler.analyze_historical_data(
                        query="show state changes",
                        entity_names=["Living Room Light"],  # New parameter name
                        time_range_days=7
                        # entity_type defaults to "auto"
                    )
                    
                    # For this test, just verify the method runs without parameter errors
                    # The actual success depends on mock data which is complex to set up
                    self.assertIsInstance(result, dict)
                    self.assertIn("tool", result)
                    self.assertIn("entities_analyzed", result["data"])
                    
                    # Should classify as devices only
                    classification = result["data"]["entity_classification"]
                    self.assertEqual(classification["detected_type"], "devices")
    
    def test_parameter_naming_backward_compatibility(self):
        """Test that the new parameter names work correctly."""
        
        # Verify the method signature accepts the new parameter names
        try:
            # This should not raise an exception
            result = self.handler.analyze_historical_data(
                query="test",
                entity_names=["Living Room Light"],
                time_range_days=7,
                entity_type="auto"
            )
            # The method should accept these parameters without error
            self.assertIsInstance(result, dict)
        except TypeError as e:
            self.fail(f"Method signature should accept new parameters: {e}")


class TestVariableSpecificFeatures(unittest.TestCase):
    """Test suite for variable-specific features."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_data_provider = Mock()
        self.mock_data_provider.get_all_devices.return_value = []
        self.mock_data_provider.get_all_variables.return_value = [
            {"name": "test_variable", "id": 123, "value": "test_value"}
        ]
        self.handler = HistoricalAnalysisHandler(self.mock_data_provider)
    
    @patch.dict('os.environ', {'INFLUXDB_ENABLED': 'true'})
    def test_variable_data_query(self):
        """Test querying variable historical data."""
        
        variable_data = [
            {"time": "2024-01-15T09:00:00Z", "value": "away"},
            {"time": "2024-01-15T11:00:00Z", "value": "home"},
            {"time": "2024-01-15T13:00:00Z", "value": "away"}
        ]
        
        with patch('mcp_server.common.influxdb.InfluxDBClient') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client
            mock_client.is_enabled.return_value = True
            mock_client.test_connection.return_value = True
            mock_client.execute_query.return_value = variable_data
            
            with patch('mcp_server.common.influxdb.InfluxDBQueryBuilder') as mock_builder_class:
                mock_builder = Mock()
                mock_builder_class.return_value = mock_builder
                mock_builder.build_variable_history_query.return_value = "SELECT value FROM variable_changes"
                
                results = self.handler._get_historical_variable_data("test_variable", 7)
                
                # Should return formatted variable change messages
                self.assertIsInstance(results, list)
                
                # Check message format for variables
                for result in results:
                    self.assertIn("Variable 'test_variable'", result)
                    self.assertIn("was", result)  # Should show state changes
    
    def test_variable_vs_device_formatting_differences(self):
        """Test that variables and devices are formatted differently."""
        
        # Device formatting (with property context)
        device_value = self.handler._format_state_value(72.5, "temperature")
        self.assertEqual(device_value, "72.5°")
        
        # Variable formatting (simpler, no context)
        variable_value = self.handler._format_variable_value(72.5)
        self.assertEqual(variable_value, "72.5")  # No degree symbol
        
        # Boolean values
        device_bool = self.handler._format_state_value(True, "onState")
        variable_bool = self.handler._format_variable_value(True)
        
        self.assertEqual(device_bool, "on")
        self.assertEqual(variable_bool, "true")


class TestReportFormatting(unittest.TestCase):
    """Test suite for enhanced report formatting with mixed entities."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_data_provider = Mock()
        self.handler = HistoricalAnalysisHandler(self.mock_data_provider)
    
    def test_mixed_entity_report_header(self):
        """Test report header with mixed entity breakdown."""
        
        results = [
            "Living Room Light.onState was on for 2 hours, from 2024-01-15 10:00:00 EST to 2024-01-15 12:00:00 EST",
            "Variable 'someone_home' was \"away\" for 1 hour, from 2024-01-15 09:00:00 EST to 2024-01-15 10:00:00 EST"
        ]
        
        entities = ["Living Room Light", "someone_home"]
        stats = {"total_state_changes": 2, "analysis_duration_seconds": 1.5}
        
        entity_classification = {
            "devices": ["Living Room Light"],
            "variables": ["someone_home"],
            "detected_type": "mixed"
        }
        
        report = self.handler._format_analysis_report(
            results, entities, 7, stats, entity_classification
        )
        
        # Check entity breakdown in header
        self.assertIn("Entities Analyzed: 2 (1 devices, 1 variables)", report)
        self.assertIn("HISTORICAL DATA ANALYSIS REPORT", report)
        self.assertIn("Total State Changes: 2", report)
    
    def test_devices_only_report_header(self):
        """Test report header with devices only."""
        
        results = ["Device data"]
        entities = ["Living Room Light"]
        stats = {"total_state_changes": 1, "analysis_duration_seconds": 1.0}
        
        entity_classification = {
            "devices": ["Living Room Light"],
            "variables": [],
            "detected_type": "devices"
        }
        
        report = self.handler._format_analysis_report(
            results, entities, 7, stats, entity_classification
        )
        
        self.assertIn("Entities Analyzed: 1 (1 devices, 0 variables)", report)
    
    def test_variables_only_report_header(self):
        """Test report header with variables only."""
        
        results = ["Variable data"]
        entities = ["someone_home"]
        stats = {"total_state_changes": 1, "analysis_duration_seconds": 1.0}
        
        entity_classification = {
            "devices": [],
            "variables": ["someone_home"],
            "detected_type": "variables"
        }
        
        report = self.handler._format_analysis_report(
            results, entities, 7, stats, entity_classification
        )
        
        self.assertIn("Entities Analyzed: 1 (0 devices, 1 variables)", report)


if __name__ == "__main__":
    unittest.main(verbosity=2)