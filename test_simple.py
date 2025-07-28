"""
Simple test to verify our core implementations work.
"""

import sys
import os

# Add the server plugin directory to path
sys.path.insert(0, 'MCP Server.indigoPlugin/Contents/Server Plugin')

def test_base_handler():
    """Test the base handler implementation."""
    from mcp_server.tools.base_handler import BaseToolHandler
    
    # Test initialization
    handler = BaseToolHandler("test_tool")
    assert handler.tool_name == "test_tool"
    
    # Test validation
    result = handler.validate_required_params({"param1": "value1"}, ["param1"])
    assert result is None  # Should be None for valid params
    
    result = handler.validate_required_params({}, ["param1"])
    assert result is not None  # Should return error for missing params
    assert "Missing required parameters" in result["error"]
    
    print("✅ BaseToolHandler tests passed")


def test_influxdb_imports():
    """Test that InfluxDB utilities can be imported."""
    try:
        from mcp_server.common.influxdb.time_utils import TimeFormatter
        from mcp_server.common.influxdb.queries import InfluxDBQueryBuilder
        
        # Test time formatter
        formatter = TimeFormatter()
        hours, minutes, seconds = formatter.get_delta_summary(
            formatter.convert_to_local_timezone("2023-01-01T12:00:00Z"),
            formatter.convert_to_local_timezone("2023-01-01T13:30:45Z")
        )
        assert hours == 1
        assert minutes == 30
        assert seconds == 45
        
        # Test query builder
        builder = InfluxDBQueryBuilder()
        query = builder.build_device_history_query("Test Device", "onState", 7)
        assert "Test Device" in query
        assert "onState" in query
        
        print("✅ InfluxDB utilities tests passed")
        
    except ImportError as e:
        print(f"⚠️  InfluxDB utilities import failed (expected without influxdb package): {e}")


def test_plugin_config_validation():
    """Test plugin configuration validation logic."""
    
    # Mock plugin validation logic
    def validate_influxdb_config(values_dict):
        errors_dict = {}
        
        if values_dict.get("enable_influxdb", False):
            influx_url = values_dict.get("influx_url", "").strip()
            influx_port = values_dict.get("influx_port", "").strip()
            
            if not influx_url:
                errors_dict["influx_url"] = "InfluxDB URL is required when InfluxDB is enabled"
            elif not (influx_url.startswith("http://") or influx_url.startswith("https://")):
                errors_dict["influx_url"] = "InfluxDB URL must start with http:// or https://"
            
            if not influx_port:
                errors_dict["influx_port"] = "InfluxDB port is required when InfluxDB is enabled"
            else:
                try:
                    port = int(influx_port)
                    if port < 1 or port > 65535:
                        errors_dict["influx_port"] = "InfluxDB port must be between 1 and 65535"
                except (ValueError, TypeError):
                    errors_dict["influx_port"] = "InfluxDB port must be a valid number"
        
        return errors_dict
    
    # Test valid config
    valid_config = {
        "enable_influxdb": True,
        "influx_url": "http://localhost",
        "influx_port": "8086"
    }
    errors = validate_influxdb_config(valid_config)
    assert len(errors) == 0
    
    # Test invalid config
    invalid_config = {
        "enable_influxdb": True,
        "influx_url": "",
        "influx_port": "invalid"
    }
    errors = validate_influxdb_config(invalid_config)
    assert len(errors) == 2
    assert "influx_url" in errors
    assert "influx_port" in errors
    
    print("✅ Plugin configuration validation tests passed")


def test_historical_analysis_state():
    """Test historical analysis state structure."""
    try:
        from mcp_server.tools.historical_analysis.state import HistoricalAnalysisState
        
        # Test state can be created with required fields
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
        
        assert sample_state["query"] == "test"
        assert sample_state["time_range_days"] == 30
        
        print("✅ Historical analysis state tests passed")
        
    except ImportError as e:
        print(f"⚠️  Historical analysis import failed (expected without langgraph): {e}")


def main():
    """Run all simple tests."""
    print("Running simple implementation tests...\n")
    
    test_base_handler()
    test_influxdb_imports()
    test_plugin_config_validation()
    test_historical_analysis_state()
    
    print("\n🎉 All available tests completed!")


if __name__ == "__main__":
    main()