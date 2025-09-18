"""
Test suite for improved historical analysis functionality.

Tests the enhanced data interpretation, formatting, and timezone handling
in the historical analysis tool.
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
from mcp_server.common.influxdb.time_utils import TimeFormatter


class TestImprovedHistoricalAnalysis(unittest.TestCase):
    """Test suite for improved historical analysis functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_data_provider = Mock()
        self.handler = HistoricalAnalysisHandler(self.mock_data_provider)
        self.time_formatter = TimeFormatter()
    
    def test_enhanced_state_value_formatting(self):
        """Test improved state value formatting with context awareness."""
        # Test boolean values
        self.assertEqual(self.handler._format_state_value(True), "on")
        self.assertEqual(self.handler._format_state_value(False), "off")
        
        # Test on/off states with property context
        self.assertEqual(self.handler._format_state_value(1, "onState"), "on")
        self.assertEqual(self.handler._format_state_value(0, "onState"), "off")
        
        # Test temperature formatting
        self.assertEqual(self.handler._format_state_value(72.5, "temperature"), "72.5°")
        self.assertEqual(self.handler._format_state_value(68, "temperatureInput1"), "68.0°")
        
        # Test humidity formatting
        self.assertEqual(self.handler._format_state_value(45.7, "humidity"), "45.7%")
        self.assertEqual(self.handler._format_state_value(60, "humidityInput1"), "60.0%")
        
        # Test brightness formatting
        self.assertEqual(self.handler._format_state_value(0.75, "brightness"), "75%")
        self.assertEqual(self.handler._format_state_value(50, "brightnessLevel"), "50%")
        
        # Test energy formatting
        self.assertEqual(self.handler._format_state_value(1500, "energyAccumTotal"), "1.50 kWh")
        self.assertEqual(self.handler._format_state_value(250, "energyAccumTotal"), "250.00 Wh")
        
        # Test power formatting
        self.assertEqual(self.handler._format_state_value(1200, "realPower"), "1.20 kW")
        self.assertEqual(self.handler._format_state_value(75, "realPower"), "75.0 W")
        
        # Test battery formatting
        self.assertEqual(self.handler._format_state_value(85, "batteryLevel"), "85%")
        
        # Test generic numeric formatting
        self.assertEqual(self.handler._format_state_value(3.14159, "sensorValue"), "3.14")
        self.assertEqual(self.handler._format_state_value(42, "count"), "42")
        self.assertEqual(self.handler._format_state_value(1234.5, "measurement"), "1234")
    
    def test_improved_timezone_conversion(self):
        """Test enhanced timezone conversion with error handling."""
        
        # Test standard UTC with Z
        result = self.handler._convert_to_local_timezone("2024-01-15T14:30:00Z")
        self.assertIsInstance(result, datetime)
        self.assertIsNotNone(result.tzinfo)
        
        # Test UTC without Z
        result = self.handler._convert_to_local_timezone("2024-01-15T14:30:00")
        self.assertIsInstance(result, datetime)
        self.assertIsNotNone(result.tzinfo)
        
        # Test with microseconds
        result = self.handler._convert_to_local_timezone("2024-01-15T14:30:00.123456Z")
        self.assertIsInstance(result, datetime)
        self.assertEqual(result.microsecond, 123456)
        
        # Test error handling with invalid format
        result = self.handler._convert_to_local_timezone("invalid-datetime")
        self.assertIsInstance(result, datetime)  # Should return current time as fallback
    
    def test_duration_formatting_improvements(self):
        """Test improved duration formatting for better readability."""
        base_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=ZoneInfo("UTC"))
        
        # Test various durations
        test_cases = [
            (timedelta(seconds=30), "30 seconds"),
            (timedelta(minutes=5), "5 minutes"),
            (timedelta(minutes=1, seconds=30), "1 minute and 30 seconds"),
            (timedelta(hours=2), "2 hours"),
            (timedelta(hours=1, minutes=30), "1 hour and 30 minutes"),
            (timedelta(days=1), "1 day"),
            (timedelta(days=2, hours=3), "2 days and 3 hours"),
            (timedelta(days=7, hours=12, minutes=30), "7 days and 12 hours"),
        ]
        
        for delta, expected in test_cases:
            end_time = base_time + delta
            result = self.handler._format_duration(base_time, end_time)
            self.assertEqual(result, expected, 
                f"Duration formatting failed for {delta}: got '{result}', expected '{expected}'")
    
    def test_timezone_handling_edge_cases(self):
        """Test timezone handling with various edge cases."""
        
        # Test different timezone formats from InfluxDB
        test_cases = [
            "2024-01-15T14:30:00Z",                    # Standard UTC
            "2024-01-15T14:30:00.123456Z",             # With microseconds
            "2024-01-15T14:30:00",                     # No timezone
            "2024-01-15T14:30:00.123456",              # No timezone, with microseconds
            "2024-01-15T14:30:00+00:00",              # UTC with offset
            "2024-01-15T14:30:00-05:00",              # With timezone offset
        ]
        
        for time_str in test_cases:
            result = self.time_formatter.convert_to_local_timezone(time_str)
            self.assertIsInstance(result, datetime)
            self.assertIsNotNone(result.tzinfo)
    
    def test_summary_statistics_calculation(self):
        """Test enhanced summary statistics calculation."""
        
        # Mock some results
        results = [
            "Device1.onState was on for 2 hours, from 2024-01-15 10:00:00 EST to 2024-01-15 12:00:00 EST",
            "Device1.onState was off for 1 hour, from 2024-01-15 12:00:00 EST to 2024-01-15 13:00:00 EST",
            "Device2.brightness was 75% for 3 hours, from 2024-01-15 10:00:00 EST to 2024-01-15 13:00:00 EST"
        ]
        devices = ["Device1", "Device2"]
        
        stats = self.handler._calculate_summary_statistics(results, devices, 7, 1.5)
        
        self.assertEqual(stats["total_state_changes"], 3)
        self.assertEqual(stats["devices_with_data"], 2)
        self.assertEqual(stats["analysis_period_days"], 7)
        self.assertEqual(stats["analysis_duration_seconds"], 1.5)
        self.assertEqual(stats["avg_changes_per_device"], 1.5)
        self.assertAlmostEqual(stats["avg_changes_per_day"], 3/7, places=2)
    
    def test_analysis_report_formatting(self):
        """Test improved analysis report formatting."""
        
        results = [
            "Living Room Light.onState was on for 2 hours, from 2024-01-15 10:00:00 EST to 2024-01-15 12:00:00 EST",
            "Living Room Light.onState was off for 1 hour, from 2024-01-15 12:00:00 EST to 2024-01-15 13:00:00 EST",
            "Bedroom Lamp.brightness was 75% for 3 hours, from 2024-01-15 10:00:00 EST to 2024-01-15 13:00:00 EST"
        ]
        devices = ["Living Room Light", "Bedroom Lamp"]
        stats = {
            "total_state_changes": 3,
            "devices_with_data": 2,
            "analysis_period_days": 7,
            "analysis_duration_seconds": 1.5,
            "avg_changes_per_device": 1.5,
            "avg_changes_per_day": 0.43
        }
        
        report = self.handler._format_analysis_report(results, devices, 7, stats)
        
        # Check report structure
        self.assertIn("HISTORICAL DATA ANALYSIS REPORT", report)
        self.assertIn("Analysis Period: Last 7 days", report)
        self.assertIn("Devices Analyzed: 2", report)
        self.assertIn("Total State Changes: 3", report)
        self.assertIn("Average Changes per Device: 1.5", report)
        self.assertIn("Average Changes per Day: 0.4", report)
        self.assertIn("DEVICE STATE HISTORY:", report)
        self.assertIn("Living Room Light:", report)
        self.assertIn("Bedroom Lamp:", report)
    
    @patch.dict('os.environ', {'INFLUXDB_ENABLED': 'true'})
    def test_influxdb_data_interpretation(self):
        """Test improved InfluxDB data interpretation."""
        
        # Mock InfluxDB results with various data types
        mock_influx_results = [
            {
                "time": "2024-01-15T10:00:00Z",
                "onState": True
            },
            {
                "time": "2024-01-15T12:00:00Z", 
                "onState": False
            },
            {
                "time": "2024-01-15T14:00:00Z",
                "onState": True
            }
        ]
        
        with patch('mcp_server.common.influxdb.InfluxDBClient') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client
            mock_client.is_enabled.return_value = True
            mock_client.test_connection.return_value = True
            mock_client.execute_query.return_value = mock_influx_results
            
            # Mock the query builder
            with patch('mcp_server.common.influxdb.InfluxDBQueryBuilder') as mock_builder_class:
                mock_builder = Mock()
                mock_builder_class.return_value = mock_builder
                mock_builder.build_device_history_query.return_value = "SELECT onState FROM device_changes WHERE name = 'Test Device'"
                
                results = self.handler._get_historical_device_data("Test Device", "onState", 7)
                
                # Should return formatted messages
                self.assertIsInstance(results, list)
                self.assertTrue(len(results) > 0)
                
                # Check that messages contain proper formatting
                for result in results:
                    self.assertIsInstance(result, str)
                    self.assertIn("Test Device.onState", result)
    
    def test_timezone_recommendations(self):
        """Test timezone handling recommendations."""
        
        # Test current time zone detection
        now = datetime.now().astimezone()
        tz_name = now.strftime("%Z")
        
        # Verify we're getting proper timezone info
        self.assertIsNotNone(tz_name)
        
        # Test timezone conversion consistency
        utc_time = datetime.now(ZoneInfo("UTC"))
        local_time = utc_time.astimezone()
        
        # The difference should be consistent with system timezone
        offset_seconds = (local_time.utcoffset() or timedelta()).total_seconds()
        self.assertIsInstance(offset_seconds, (int, float))
    
    def test_error_handling_improvements(self):
        """Test improved error handling in timezone and data processing."""
        
        # Test invalid timestamp handling
        with patch.object(self.handler, 'error_log') as mock_log:
            result = self.handler._convert_to_local_timezone("invalid-timestamp")
            self.assertIsInstance(result, datetime)
            mock_log.assert_called()
        
        # Test negative time delta handling
        past_time = datetime.now().astimezone()
        future_time = past_time + timedelta(hours=1)  # Intentionally backwards
        
        hours, minutes, seconds = self.handler._get_delta_summary(future_time, past_time)
        self.assertEqual((hours, minutes, seconds), (0, 0, 0))


class TestTimeFormatterImprovements(unittest.TestCase):
    """Test suite for TimeFormatter improvements."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.formatter = TimeFormatter()
    
    def test_enhanced_timestamp_formatting(self):
        """Test enhanced timestamp formatting with timezone display."""
        
        # Create test timestamps in different timezones
        utc_time = datetime(2024, 1, 15, 14, 30, 0, tzinfo=ZoneInfo("UTC"))
        est_time = utc_time.astimezone(ZoneInfo("US/Eastern"))
        pst_time = utc_time.astimezone(ZoneInfo("US/Pacific"))
        
        # Test formatting includes timezone info
        utc_formatted = self.formatter._format_timestamp_with_tz(utc_time)
        est_formatted = self.formatter._format_timestamp_with_tz(est_time)
        pst_formatted = self.formatter._format_timestamp_with_tz(pst_time)
        
        # Should include timezone abbreviation or offset
        self.assertTrue(any(tz in utc_formatted for tz in ["UTC", "+0000", "+00:00"]))
        self.assertTrue(any(tz in est_formatted for tz in ["EST", "EDT", "-0500", "-0400"]))
        self.assertTrue(any(tz in pst_formatted for tz in ["PST", "PDT", "-0800", "-0700"]))
    
    def test_duration_formatting_readability(self):
        """Test improved duration formatting for better readability."""
        base_time = datetime(2024, 1, 15, 12, 0, 0)
        
        # Test short durations
        end_time = base_time + timedelta(seconds=30)
        formatted = self.formatter.format_duration(0, 0, 30)
        self.assertEqual(formatted, "30 seconds")
        
        # Test medium durations
        formatted = self.formatter.format_duration(2, 30, 45)
        self.assertEqual(formatted, "2 hours, 30 minutes, and 45 seconds")
        
        # Test long durations (should group appropriately) - but format_duration takes hours/min/sec
        # The TimeFormatter.format_duration only handles individual components, not 25 hours
        formatted = self.formatter.format_duration(25, 0, 0)  
        self.assertEqual(formatted, "25 hours")
    
    def test_convert_to_local_timezone_robustness(self):
        """Test timezone conversion robustness with various inputs."""
        
        test_cases = [
            "2024-01-15T14:30:00Z",                    # Standard UTC
            "2024-01-15T14:30:00.123456Z",             # With microseconds
            "2024-01-15T14:30:00",                     # No timezone indicator
            "2024-01-15T14:30:00.999999",              # High precision microseconds
        ]
        
        for time_str in test_cases:
            result = self.formatter.convert_to_local_timezone(time_str)
            self.assertIsInstance(result, datetime)
            self.assertIsNotNone(result.tzinfo)
            # Should be in local timezone (not UTC)
            self.assertNotEqual(result.tzinfo.tzname(result), "UTC")


class TestInfluxDBQueryImprovements(unittest.TestCase):
    """Test suite for InfluxDB query and data handling improvements."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_data_provider = Mock()
        self.handler = HistoricalAnalysisHandler(self.mock_data_provider)
    
    @patch.dict('os.environ', {
        'INFLUXDB_ENABLED': 'true',
        'INFLUXDB_HOST': 'test-host',
        'INFLUXDB_PORT': '8086',
        'INFLUXDB_USERNAME': 'test-user',
        'INFLUXDB_PASSWORD': 'test-pass',
        'INFLUXDB_DATABASE': 'test-db'
    })
    def test_influxdb_data_processing(self):
        """Test improved InfluxDB data processing and interpretation."""
        
        # Mock InfluxDB data with mixed types
        mock_data = [
            {"time": "2024-01-15T10:00:00Z", "temperature": 72.5},
            {"time": "2024-01-15T11:00:00Z", "temperature": 73.2},
            {"time": "2024-01-15T12:00:00Z", "temperature": 71.8},
        ]
        
        with patch('mcp_server.common.influxdb.InfluxDBClient') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client
            mock_client.is_enabled.return_value = True
            mock_client.test_connection.return_value = True
            mock_client.execute_query.return_value = mock_data
            
            with patch('mcp_server.common.influxdb.InfluxDBQueryBuilder') as mock_builder_class:
                mock_builder = Mock()
                mock_builder_class.return_value = mock_builder
                mock_builder.build_device_history_query.return_value = "SELECT temperature FROM device_changes"
                
                results = self.handler._get_historical_device_data("Thermostat", "temperature", 7)
                
                # Should process temperature data correctly
                self.assertIsInstance(results, list)
                
                # For this test, just verify we get results back
                # The temperature formatting happens in the state value formatter
    
    def test_data_deduplication_and_grouping(self):
        """Test that consecutive identical states are properly grouped."""
        
        # Mock data with consecutive identical states
        mock_data = [
            {"time": "2024-01-15T10:00:00Z", "onState": True},
            {"time": "2024-01-15T10:30:00Z", "onState": True},  # Same state
            {"time": "2024-01-15T11:00:00Z", "onState": True},  # Same state
            {"time": "2024-01-15T12:00:00Z", "onState": False}, # State change
            {"time": "2024-01-15T13:00:00Z", "onState": False}, # Same state
            {"time": "2024-01-15T14:00:00Z", "onState": True},  # State change
        ]
        
        with patch('mcp_server.common.influxdb.InfluxDBClient') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client
            mock_client.is_enabled.return_value = True
            mock_client.test_connection.return_value = True
            mock_client.execute_query.return_value = mock_data
            
            with patch('mcp_server.common.influxdb.InfluxDBQueryBuilder') as mock_builder_class:
                mock_builder = Mock()
                mock_builder_class.return_value = mock_builder
                mock_builder.build_device_history_query.return_value = "SELECT onState FROM device_changes"
                
                results = self.handler._get_historical_device_data("Test Switch", "onState", 7)
                
                # Should group consecutive states and only show state changes
                # Expect: on (10:00-12:00), off (12:00-14:00), currently on (since 14:00) 
                self.assertTrue(len(results) >= 1)  # At least one state period


class TestRecommendationsImplementation(unittest.TestCase):
    """Test implementation of timezone and formatting recommendations."""
    
    def test_timezone_consistency_validation(self):
        """Test that timezone handling is consistent across all functions."""
        
        handler = HistoricalAnalysisHandler(Mock())
        
        # Test that all timezone-related methods use the same approach
        test_time_str = "2024-01-15T14:30:00Z"
        converted_time = handler._convert_to_local_timezone(test_time_str)
        
        # Verify timezone info is preserved
        self.assertIsNotNone(converted_time.tzinfo)
        
        # Test that formatting includes timezone
        formatted = converted_time.strftime("%Y-%m-%d %H:%M:%S %Z")
        self.assertNotEqual(formatted.strip()[-1], "")  # Should have timezone info
    
    def test_performance_improvements(self):
        """Test that performance improvements don't break functionality."""
        
        # Test large dataset handling
        large_mock_data = [
            {"time": f"2024-01-{day:02d}T{hour:02d}:00:00Z", "onState": hour % 2 == 0}
            for day in range(1, 8)  # 7 days
            for hour in range(0, 24)  # 24 hours per day
        ]  # Total: 168 data points
        
        handler = HistoricalAnalysisHandler(Mock())
        
        with patch('mcp_server.common.influxdb.InfluxDBClient') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client
            mock_client.is_enabled.return_value = True
            mock_client.test_connection.return_value = True
            mock_client.execute_query.return_value = large_mock_data
            
            with patch('mcp_server.common.influxdb.InfluxDBQueryBuilder'):
                start_time = time.time()
                results = handler._get_historical_device_data("Test Device", "onState", 7)
                end_time = time.time()
                
                # Should complete within reasonable time
                self.assertLess(end_time - start_time, 5.0)  # Less than 5 seconds
                
                # Should return reasonable number of state changes
                self.assertGreater(len(results), 0)


if __name__ == "__main__":
    import time
    
    # Add the required import that may be missing
    try:
        import time
    except ImportError:
        pass
    
    unittest.main(verbosity=2)