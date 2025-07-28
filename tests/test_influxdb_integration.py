"""
Tests for InfluxDB integration.
"""

import pytest
import os
from unittest.mock import Mock, patch, MagicMock
from mcp_server.common.influxdb import InfluxDBClient, InfluxDBQueryBuilder, TimeFormatter


class TestInfluxDBClient:
    """Test cases for InfluxDBClient."""
    
    def test_is_enabled_true(self):
        """Test InfluxDB enabled detection."""
        with patch.dict(os.environ, {"INFLUXDB_ENABLED": "true"}):
            client = InfluxDBClient()
            assert client.is_enabled() is True
    
    def test_is_enabled_false(self):
        """Test InfluxDB disabled detection."""
        with patch.dict(os.environ, {"INFLUXDB_ENABLED": "false"}):
            client = InfluxDBClient()
            assert client.is_enabled() is False
    
    def test_is_enabled_missing(self):
        """Test InfluxDB enabled with missing env var."""
        with patch.dict(os.environ, {}, clear=True):
            client = InfluxDBClient()
            assert client.is_enabled() is False
    
    def test_get_connection_info(self):
        """Test connection info extraction from environment."""
        env_vars = {
            "INFLUXDB_HOST": "test-host",
            "INFLUXDB_PORT": "9999",
            "INFLUXDB_USERNAME": "testuser",
            "INFLUXDB_PASSWORD": "testpass",
            "INFLUXDB_DATABASE": "testdb"
        }
        
        with patch.dict(os.environ, env_vars):
            client = InfluxDBClient()
            info = client.get_connection_info()
            
            assert info["host"] == "test-host"
            assert info["port"] == 9999
            assert info["username"] == "testuser"
            assert info["password"] == "testpass"
            assert info["database"] == "testdb"
    
    def test_get_connection_info_defaults(self):
        """Test connection info with default values."""
        with patch.dict(os.environ, {}, clear=True):
            client = InfluxDBClient()
            info = client.get_connection_info()
            
            assert info["host"] == "localhost"
            assert info["port"] == 8086
            assert info["username"] == ""
            assert info["password"] == ""
            assert info["database"] == "indigo"
    
    @patch('mcp_server.common.influxdb.client.InfluxClient')
    def test_get_client_success(self, mock_influx_client):
        """Test successful client creation."""
        mock_client_instance = MagicMock()
        mock_client_instance.ping.return_value = True
        mock_influx_client.return_value = mock_client_instance
        
        env_vars = {
            "INFLUXDB_ENABLED": "true",
            "INFLUXDB_HOST": "localhost",
            "INFLUXDB_PORT": "8086",
            "INFLUXDB_DATABASE": "indigo"
        }
        
        with patch.dict(os.environ, env_vars):
            client = InfluxDBClient()
            
            with client.get_client() as influx_client:
                assert influx_client == mock_client_instance
                mock_client_instance.ping.assert_called_once()
    
    def test_get_client_not_enabled(self):
        """Test client creation when InfluxDB is not enabled."""
        with patch.dict(os.environ, {"INFLUXDB_ENABLED": "false"}):
            client = InfluxDBClient()
            
            with pytest.raises(RuntimeError, match="InfluxDB is not enabled"):
                with client.get_client():
                    pass
    
    @patch('mcp_server.common.influxdb.client.InfluxClient')
    def test_get_client_ping_fails(self, mock_influx_client):
        """Test client creation with ping failure."""
        mock_client_instance = MagicMock()
        mock_client_instance.ping.return_value = False
        mock_influx_client.return_value = mock_client_instance
        
        env_vars = {"INFLUXDB_ENABLED": "true"}
        
        with patch.dict(os.environ, env_vars):
            client = InfluxDBClient()
            
            with pytest.raises(RuntimeError, match="InfluxDB ping failed"):
                with client.get_client():
                    pass
    
    @patch('mcp_server.common.influxdb.client.InfluxClient')
    def test_execute_query_success(self, mock_influx_client):
        """Test successful query execution."""
        mock_result = MagicMock()
        mock_result.get_points.return_value = [
            {"time": "2023-01-01T00:00:00Z", "device": "test", "value": 1},
            {"time": "2023-01-01T01:00:00Z", "device": "test", "value": 0}
        ]
        
        mock_client_instance = MagicMock()
        mock_client_instance.ping.return_value = True
        mock_client_instance.query.return_value = mock_result
        mock_influx_client.return_value = mock_client_instance
        
        env_vars = {"INFLUXDB_ENABLED": "true"}
        
        with patch.dict(os.environ, env_vars):
            client = InfluxDBClient()
            results = client.execute_query("SELECT * FROM test")
            
            assert len(results) == 2
            assert results[0]["device"] == "test"
            assert results[0]["value"] == 1
            mock_client_instance.query.assert_called_once_with("SELECT * FROM test")


class TestInfluxDBQueryBuilder:
    """Test cases for InfluxDBQueryBuilder."""
    
    def test_build_device_history_query(self):
        """Test device history query building."""
        builder = InfluxDBQueryBuilder()
        
        query = builder.build_device_history_query(
            device_name="Test Device",
            device_property="onState",
            time_range_days=7
        )
        
        assert 'SELECT "onState" FROM "device_changes"' in query
        assert "WHERE \"name\" = 'Test Device'" in query
        assert "time >=" in query
        assert 'GROUP BY "name"' in query
        assert "ORDER BY time ASC" in query
    
    def test_build_device_latest_query(self):
        """Test latest device state query building."""
        builder = InfluxDBQueryBuilder()
        
        query = builder.build_device_latest_query(
            device_name="Test Device",
            device_property="brightness"
        )
        
        assert 'SELECT LAST("brightness") FROM "device_changes"' in query
        assert "WHERE \"name\" = 'Test Device'" in query
        assert 'GROUP BY "name"' in query
    
    def test_build_devices_summary_query(self):
        """Test multiple devices summary query building."""
        builder = InfluxDBQueryBuilder()
        
        query = builder.build_devices_summary_query(
            device_names=["Device1", "Device2"],
            time_range_hours=12
        )
        
        assert "SELECT * FROM \"device_changes\"" in query
        assert "\"name\" = 'Device1' OR \"name\" = 'Device2'" in query
        assert "time >=" in query
        assert 'GROUP BY "name"' in query
    
    def test_build_aggregation_query(self):
        """Test aggregation query building."""
        builder = InfluxDBQueryBuilder()
        
        query = builder.build_aggregation_query(
            device_name="Test Device",
            device_property="temperature",
            aggregation="MEAN",
            time_range_days=1,
            group_by_time="1h"
        )
        
        assert 'SELECT MEAN("temperature") FROM "device_changes"' in query
        assert "WHERE \"name\" = 'Test Device'" in query
        assert "GROUP BY time(1h)" in query
        assert "ORDER BY time ASC" in query


class TestTimeFormatter:
    """Test cases for TimeFormatter."""
    
    def test_convert_to_local_timezone(self):
        """Test UTC to local timezone conversion."""
        formatter = TimeFormatter()
        
        # Test with Z suffix
        result = formatter.convert_to_local_timezone("2023-01-01T12:00:00Z")
        assert result is not None
        assert result.tzinfo is not None
    
    def test_convert_to_local_timezone_no_z(self):
        """Test timezone conversion without Z suffix."""
        formatter = TimeFormatter()
        
        result = formatter.convert_to_local_timezone("2023-01-01T12:00:00")
        assert result is not None
        assert result.tzinfo is not None
    
    def test_get_delta_summary(self):
        """Test time delta calculation."""
        formatter = TimeFormatter()
        
        from datetime import datetime, timedelta
        start = datetime.now()
        end = start + timedelta(hours=2, minutes=30, seconds=45)
        
        hours, minutes, seconds = formatter.get_delta_summary(start, end)
        
        assert hours == 2
        assert minutes == 30
        assert seconds == 45
    
    def test_get_delta_summary_negative(self):
        """Test negative time delta handling."""
        formatter = TimeFormatter()
        
        from datetime import datetime, timedelta
        start = datetime.now()
        end = start - timedelta(hours=1)  # End before start
        
        hours, minutes, seconds = formatter.get_delta_summary(start, end)
        
        # Should return zero for negative deltas
        assert hours == 0
        assert minutes == 0
        assert seconds == 0
    
    def test_format_duration(self):
        """Test duration formatting."""
        formatter = TimeFormatter()
        
        # Test various combinations
        assert "2 hours and 30 minutes" in formatter.format_duration(2, 30, 0)
        assert "1 hour and 1 minute" in formatter.format_duration(1, 1, 0)
        assert "45 seconds" in formatter.format_duration(0, 0, 45)
        assert "1 hour, 15 minutes, and 30 seconds" in formatter.format_duration(1, 15, 30)
    
    def test_format_device_state_message(self):
        """Test device state message formatting."""
        formatter = TimeFormatter()
        
        from datetime import datetime, timedelta
        start = datetime.now()
        end = start + timedelta(hours=1, minutes=30)
        
        message = formatter.format_device_state_message(
            "Test Device", "on", start, end
        )
        
        assert "Test Device" in message
        assert "was on for" in message
        assert "1 hour and 30 minutes" in message
    
    def test_get_time_range_for_period(self):
        """Test time range calculation."""
        formatter = TimeFormatter()
        
        start, end = formatter.get_time_range_for_period(7)
        
        assert start < end
        assert (end - start).days == 7
        assert start.tzinfo is not None
        assert end.tzinfo is not None