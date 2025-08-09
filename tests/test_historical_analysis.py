"""
Tests for historical analysis functionality.
"""

import pytest
import os
from unittest.mock import Mock, patch, MagicMock
from mcp_server.tools.historical_analysis import HistoricalAnalysisHandler


class TestHistoricalAnalysisHandler:
    """Test cases for HistoricalAnalysisHandler."""
    
    def test_initialization(self):
        """Test handler initialization."""
        mock_data_provider = Mock()
        handler = HistoricalAnalysisHandler(mock_data_provider)
        
        assert handler.tool_name == "historical_analysis"
        assert handler.data_provider == mock_data_provider
    
    def test_analyze_historical_data_influxdb_disabled(self):
        """Test analysis when InfluxDB is disabled."""
        mock_data_provider = Mock()
        handler = HistoricalAnalysisHandler(mock_data_provider)
        
        with patch.dict(os.environ, {"INFLUXDB_ENABLED": "false"}):
            result = handler.analyze_historical_data(
                query="Test query",
                device_names=["Device1"],
                time_range_days=7
            )
        
        assert result["success"] is False
        assert "InfluxDB is not enabled" in result["error"]
        assert "Historical analysis requires InfluxDB" in result["report"]
    
    def test_analyze_historical_data_validation_error(self):
        """Test analysis with validation errors."""
        mock_data_provider = Mock()
        handler = HistoricalAnalysisHandler(mock_data_provider)
        
        # Enable InfluxDB to test validation (otherwise InfluxDB check happens first)
        with patch.dict(os.environ, {"INFLUXDB_ENABLED": "true"}):
            # Test missing query (None triggers validation)
            result = handler.analyze_historical_data(
                query=None,
                device_names=["Device1"],
                time_range_days=7
            )
        
        assert result["success"] is False
        assert "Missing required parameters" in result["error"]
    
    def test_analyze_historical_data_empty_devices(self):
        """Test analysis with empty device list."""
        mock_data_provider = Mock()
        handler = HistoricalAnalysisHandler(mock_data_provider)
        
        result = handler.analyze_historical_data(
            query="Test query",
            device_names=[],
            time_range_days=7
        )
        
        assert result["success"] is False
        assert "No device names provided" in result["error"]
    
    def test_analyze_historical_data_invalid_time_range(self):
        """Test analysis with invalid time range."""
        mock_data_provider = Mock()
        handler = HistoricalAnalysisHandler(mock_data_provider)
        
        # Test time range too large
        result = handler.analyze_historical_data(
            query="Test query",
            device_names=["Device1"],
            time_range_days=400
        )
        
        assert result["success"] is False
        assert "Time range must be between 1 and 365 days" in result["error"]
    
    @patch('mcp_server.tools.historical_analysis.main.InfluxDBClient')
    def test_analyze_historical_data_no_data_found(self, mock_influx_client):
        """Test analysis when no historical data is found."""
        # Mock InfluxDB enabled
        with patch.dict(os.environ, {"INFLUXDB_ENABLED": "true"}):
            # Mock client that finds no data
            mock_client_instance = Mock()
            mock_client_instance.is_enabled.return_value = True
            mock_client_instance.test_connection.return_value = True
            mock_client_instance.execute_query.return_value = []
            mock_influx_client.return_value = mock_client_instance
            
            mock_data_provider = Mock()
            handler = HistoricalAnalysisHandler(mock_data_provider)
            
            result = handler.analyze_historical_data(
                query="Test query",
                device_names=["Device1"],
                time_range_days=7
            )
            
            assert result["success"] is False
            assert "No historical data found" in result["error"]
            assert result["summary_stats"]["devices_with_data"] == 0
    
    @patch('mcp_server.tools.historical_analysis.main.InfluxDBQueryBuilder')
    @patch('mcp_server.tools.historical_analysis.main.InfluxDBClient')
    def test_analyze_historical_data_success(self, mock_influx_client, mock_query_builder):
        """Test successful analysis execution."""
        # Mock InfluxDB enabled
        with patch.dict(os.environ, {"INFLUXDB_ENABLED": "true"}):
            # Mock client that returns sample data
            mock_client_instance = Mock()
            mock_client_instance.is_enabled.return_value = True
            mock_client_instance.test_connection.return_value = True
            
            # Sample historical data with state changes
            mock_client_instance.execute_query.return_value = [
                {"time": "2025-01-01T10:00:00Z", "onState": True},
                {"time": "2025-01-01T12:00:00Z", "onState": False},
                {"time": "2025-01-01T14:00:00Z", "onState": True}
            ]
            mock_influx_client.return_value = mock_client_instance
            
            # Mock query builder
            mock_query_builder_instance = Mock()
            mock_query_builder_instance.build_device_history_query.return_value = "SELECT * FROM device_changes"
            mock_query_builder.return_value = mock_query_builder_instance
            
            mock_data_provider = Mock()
            handler = HistoricalAnalysisHandler(mock_data_provider)
            
            result = handler.analyze_historical_data(
                query="How often was Device1 on yesterday?",
                device_names=["Device1"],
                time_range_days=7
            )
            
            assert result["success"] is True
            assert result["data"]["devices_analyzed"] == ["Device1"]
            assert result["data"]["total_data_points"] > 0
            assert "Device1 was on for" in result["data"]["report"]
            assert result["data"]["summary_stats"]["devices_with_data"] == 1
    
    def test_get_available_devices(self):
        """Test getting available devices."""
        mock_devices = [
            {"name": "Device1", "id": 1},
            {"name": "Device2", "id": 2},
            {"name": "", "id": 3},  # Should be filtered out
            {"id": 4}  # No name, should be filtered out
        ]
        
        mock_data_provider = Mock()
        mock_data_provider.get_devices.return_value = mock_devices
        
        handler = HistoricalAnalysisHandler(mock_data_provider)
        devices = handler.get_available_devices()
        
        assert devices == ["Device1", "Device2"]
    
    def test_get_available_devices_error(self):
        """Test handling errors when getting devices."""
        mock_data_provider = Mock()
        mock_data_provider.get_devices.side_effect = Exception("Connection error")
        
        handler = HistoricalAnalysisHandler(mock_data_provider)
        devices = handler.get_available_devices()
        
        assert devices == []
    
    def test_is_influxdb_available_disabled(self):
        """Test InfluxDB availability check when disabled."""
        mock_data_provider = Mock()
        handler = HistoricalAnalysisHandler(mock_data_provider)
        
        with patch.dict(os.environ, {"INFLUXDB_ENABLED": "false"}):
            available = handler.is_influxdb_available()
            assert available is False
    
    @patch('mcp_server.tools.historical_analysis.main.InfluxDBClient')
    def test_is_influxdb_available_connection_failed(self, mock_influx_client):
        """Test InfluxDB availability check when connection fails."""
        mock_client_instance = Mock()
        mock_client_instance.test_connection.return_value = False
        mock_influx_client.return_value = mock_client_instance
        
        mock_data_provider = Mock()
        handler = HistoricalAnalysisHandler(mock_data_provider)
        
        with patch.dict(os.environ, {"INFLUXDB_ENABLED": "true"}):
            available = handler.is_influxdb_available()
            assert available is False
    
    @patch('mcp_server.tools.historical_analysis.main.InfluxDBClient')
    def test_is_influxdb_available_success(self, mock_influx_client):
        """Test successful InfluxDB availability check."""
        mock_client_instance = Mock()
        mock_client_instance.test_connection.return_value = True
        mock_influx_client.return_value = mock_client_instance
        
        mock_data_provider = Mock()
        handler = HistoricalAnalysisHandler(mock_data_provider)
        
        with patch.dict(os.environ, {"INFLUXDB_ENABLED": "true"}):
            available = handler.is_influxdb_available()
            assert available is True
    
    def test_helper_functions(self):
        """Test helper functions for time and state formatting."""
        mock_data_provider = Mock()
        handler = HistoricalAnalysisHandler(mock_data_provider)
        
        # Test get_delta_summary
        from datetime import datetime, timezone
        start = datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        end = datetime(2025, 1, 1, 12, 30, 45, tzinfo=timezone.utc)
        
        hours, minutes, seconds = handler._get_delta_summary(start, end)
        assert hours == 2
        assert minutes == 30
        assert seconds == 45
        
        # Test format_state_value
        assert handler._format_state_value(True) == "on"
        assert handler._format_state_value(False) == "off"
        assert handler._format_state_value(1) == "on"
        assert handler._format_state_value(0) == "off"
        assert handler._format_state_value(50) == "50"
        assert handler._format_state_value("active") == "active"
        assert handler._format_state_value(None) == "unknown"
    
    def test_convert_to_local_timezone(self):
        """Test timezone conversion."""
        mock_data_provider = Mock()
        handler = HistoricalAnalysisHandler(mock_data_provider)
        
        # Test with Z suffix
        utc_time = "2025-01-01T12:00:00Z"
        local_time = handler._convert_to_local_timezone(utc_time)
        
        assert local_time.tzinfo is not None
        assert local_time.year == 2025
        assert local_time.month == 1
        assert local_time.day == 1
        
        # Test without Z suffix
        utc_time = "2025-01-01T12:00:00"
        local_time = handler._convert_to_local_timezone(utc_time)
        
        assert local_time.tzinfo is not None
        assert local_time.year == 2025
        assert local_time.month == 1
        assert local_time.day == 1