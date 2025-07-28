"""
Tests for historical analysis functionality.
"""

import pytest
import os
from unittest.mock import Mock, patch, MagicMock
from mcp_server.tools.historical_analysis import HistoricalAnalysisHandler
from mcp_server.tools.historical_analysis.state import HistoricalAnalysisState


class TestHistoricalAnalysisHandler:
    """Test cases for HistoricalAnalysisHandler."""
    
    def test_initialization(self):
        """Test handler initialization."""
        mock_data_provider = Mock()
        handler = HistoricalAnalysisHandler(mock_data_provider)
        
        assert handler.tool_name == "historical_analysis"
        assert handler.data_provider == mock_data_provider
        assert handler.graph is not None
    
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
        
        # Test missing query
        result = handler.analyze_historical_data(
            query="",
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
        
        # Test negative time range
        result = handler.analyze_historical_data(
            query="Test query",
            device_names=["Device1"],
            time_range_days=-1
        )
        
        assert result["success"] is False
        assert "Time range must be between 1 and 365 days" in result["error"]
        
        # Test too large time range
        result = handler.analyze_historical_data(
            query="Test query",
            device_names=["Device1"],
            time_range_days=400
        )
        
        assert result["success"] is False
        assert "Time range must be between 1 and 365 days" in result["error"]
    
    @patch('mcp_server.tools.historical_analysis.main.os.environ')
    @patch('mcp_server.tools.historical_analysis.graph.HistoricalAnalysisGraph')
    def test_analyze_historical_data_success(self, mock_graph_class, mock_environ):
        """Test successful analysis execution."""
        # Mock environment
        mock_environ.get.return_value = "true"
        
        # Mock successful graph execution
        mock_graph = Mock()
        mock_final_state = {
            "query": "Test query",
            "device_names": ["Device1"],
            "time_range_days": 7,
            "raw_data": [{"device": "Device1", "value": 1}],
            "query_success": True,
            "query_error": None,
            "processed_data": [{"device_name": "Device1", "state": "on", "duration_hours": 2}],
            "transform_success": True,
            "transform_error": None,
            "analysis_results": {"statistics": {}, "patterns": {}},
            "analysis_success": True,
            "analysis_error": None,
            "formatted_report": "Test report",
            "summary_stats": {"devices_analyzed": 1},
            "total_data_points": 1,
            "devices_analyzed": ["Device1"],
            "analysis_duration_seconds": 1.5
        }
        mock_graph.execute.return_value = mock_final_state
        mock_graph_class.return_value = mock_graph
        
        mock_data_provider = Mock()
        handler = HistoricalAnalysisHandler(mock_data_provider)
        
        result = handler.analyze_historical_data(
            query="Test query",
            device_names=["Device1"],
            time_range_days=7
        )
        
        assert result["success"] is True
        assert result["data"]["report"] == "Test report"
        assert result["data"]["total_data_points"] == 1
        assert result["data"]["devices_analyzed"] == ["Device1"]
        assert result["data"]["time_range_days"] == 7
    
    @patch('mcp_server.tools.historical_analysis.main.os.environ')
    @patch('mcp_server.tools.historical_analysis.graph.HistoricalAnalysisGraph')
    def test_analyze_historical_data_partial_failure(self, mock_graph_class, mock_environ):
        """Test analysis with partial failure."""
        # Mock environment
        mock_environ.get.return_value = "true"
        
        # Mock graph execution with failure
        mock_graph = Mock()
        mock_final_state = {
            "query": "Test query",
            "device_names": ["Device1"],
            "time_range_days": 7,
            "raw_data": [],
            "query_success": False,
            "query_error": "Connection failed",
            "processed_data": [],
            "transform_success": False,
            "transform_error": "No data to transform",
            "analysis_results": {},
            "analysis_success": False,
            "analysis_error": "No data to analyze",
            "formatted_report": "Analysis failed",
            "summary_stats": {},
            "total_data_points": 0,
            "devices_analyzed": [],
            "analysis_duration_seconds": 0.5
        }
        mock_graph.execute.return_value = mock_final_state
        mock_graph_class.return_value = mock_graph
        
        mock_data_provider = Mock()
        handler = HistoricalAnalysisHandler(mock_data_provider)
        
        result = handler.analyze_historical_data(
            query="Test query",
            device_names=["Device1"],
            time_range_days=7
        )
        
        assert result["success"] is False
        assert "Connection failed" in result["error"]
        assert result["report"] == "Analysis failed"
    
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
        mock_data_provider.get_devices.assert_called_once()
    
    def test_get_available_devices_error(self):
        """Test error handling in get_available_devices."""
        mock_data_provider = Mock()
        mock_data_provider.get_devices.side_effect = Exception("Connection error")
        
        handler = HistoricalAnalysisHandler(mock_data_provider)
        devices = handler.get_available_devices()
        
        assert devices == []
    
    @patch('mcp_server.tools.historical_analysis.main.InfluxDBClient')
    def test_is_influxdb_available_true(self, mock_client_class):
        """Test InfluxDB availability check - available."""
        mock_client = Mock()
        mock_client.test_connection.return_value = True
        mock_client_class.return_value = mock_client
        
        with patch.dict(os.environ, {"INFLUXDB_ENABLED": "true"}):
            mock_data_provider = Mock()
            handler = HistoricalAnalysisHandler(mock_data_provider)
            
            assert handler.is_influxdb_available() is True
    
    @patch('mcp_server.tools.historical_analysis.main.InfluxDBClient')
    def test_is_influxdb_available_connection_fails(self, mock_client_class):
        """Test InfluxDB availability check - connection fails."""
        mock_client = Mock()
        mock_client.test_connection.return_value = False
        mock_client_class.return_value = mock_client
        
        with patch.dict(os.environ, {"INFLUXDB_ENABLED": "true"}):
            mock_data_provider = Mock()
            handler = HistoricalAnalysisHandler(mock_data_provider)
            
            assert handler.is_influxdb_available() is False
    
    def test_is_influxdb_available_disabled(self):
        """Test InfluxDB availability check - disabled."""
        with patch.dict(os.environ, {"INFLUXDB_ENABLED": "false"}):
            mock_data_provider = Mock()
            handler = HistoricalAnalysisHandler(mock_data_provider)
            
            assert handler.is_influxdb_available() is False
    
    @patch('mcp_server.tools.historical_analysis.main.InfluxDBClient')
    def test_is_influxdb_available_exception(self, mock_client_class):
        """Test InfluxDB availability check - exception."""
        mock_client_class.side_effect = Exception("Import error")
        
        with patch.dict(os.environ, {"INFLUXDB_ENABLED": "true"}):
            mock_data_provider = Mock()
            handler = HistoricalAnalysisHandler(mock_data_provider)
            
            assert handler.is_influxdb_available() is False


class TestHistoricalAnalysisState:
    """Test cases for HistoricalAnalysisState."""
    
    def test_state_structure(self):
        """Test that state has expected structure."""
        # This is more of a documentation test to ensure state structure is maintained
        required_keys = {
            "query", "device_names", "time_range_days",
            "raw_data", "query_success", "query_error",
            "processed_data", "transform_success", "transform_error",
            "analysis_results", "analysis_success", "analysis_error",
            "formatted_report", "summary_stats",
            "total_data_points", "devices_analyzed", "analysis_duration_seconds"
        }
        
        # Create a sample state to verify structure
        sample_state: HistoricalAnalysisState = {
            "query": "test",
            "device_names": [],
            "time_range_days": 30,
            "raw_data": [],
            "query_success": False,
            "query_error": None,
            "processed_data": [],
            "transform_success": False,
            "transform_error": None,
            "analysis_results": {},
            "analysis_success": False,
            "analysis_error": None,
            "formatted_report": "",
            "summary_stats": {},
            "total_data_points": 0,
            "devices_analyzed": [],
            "analysis_duration_seconds": 0.0
        }
        
        # Verify all required keys are present
        assert set(sample_state.keys()) == required_keys