#!/usr/bin/env python3
"""
Test script to diagnose InfluxDB query issues for historical analysis
"""

import os
import sys
import logging
from datetime import datetime, timedelta

# Add the plugin directory to the path
sys.path.insert(0, '/Users/mike/Mike_Sync_Documents/Programming/indigo-mcp-server/MCP Server.indigoPlugin/Contents/Server Plugin')

# Set up environment variables
os.environ['INFLUXDB_ENABLED'] = 'true'
os.environ['INFLUXDB_HOST'] = 'influx.home.mikelamoureux.net'
os.environ['INFLUXDB_PORT'] = '8086'
os.environ['INFLUXDB_USERNAME'] = 'indigo'
os.environ['INFLUXDB_PASSWORD'] = '4AFcW2AAMdvQUygWfQBxavu'
os.environ['INFLUXDB_DATABASE'] = 'indigo'

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from mcp_server.common.influxdb import InfluxDBClient, InfluxDBQueryBuilder

def test_influxdb_connection():
    """Test basic InfluxDB connection"""
    print("\n=== Testing InfluxDB Connection ===")
    client = InfluxDBClient(logger=logger)
    
    print(f"InfluxDB Enabled: {client.is_enabled()}")
    print(f"Connection Info: {client.get_connection_info()}")
    
    if client.test_connection():
        print("✓ Connection successful!")
        return True
    else:
        print("✗ Connection failed!")
        return False

def test_database_info():
    """Get database and measurement information"""
    print("\n=== Testing Database Info ===")
    client = InfluxDBClient(logger=logger)
    
    # Get databases
    databases = client.get_database_list()
    print(f"Available databases: {databases}")
    
    # Get measurements
    measurements = client.get_measurement_list()
    print(f"Available measurements: {measurements}")
    
    return measurements

def test_device_query(device_name="JoEllen home presence"):
    """Test querying specific device data"""
    print(f"\n=== Testing Query for Device: {device_name} ===")
    
    client = InfluxDBClient(logger=logger)
    query_builder = InfluxDBQueryBuilder(logger=logger)
    
    # Test different property queries
    properties = ["onState", "state", "onOffState", "isPoweredOn", "sensorValue"]
    
    for prop in properties:
        print(f"\nTesting property: {prop}")
        
        try:
            # Build query for last 30 days
            query = query_builder.build_device_history_query(
                device_name=device_name,
                device_property=prop,
                time_range_days=30,
                measurement="device_changes"
            )
            
            print(f"Query: {query}")
            
            # Execute query
            results = client.execute_query(query)
            
            if results:
                print(f"✓ Found {len(results)} data points")
                # Show first few results
                for i, result in enumerate(results[:3]):
                    print(f"  Result {i+1}: {result}")
                if len(results) > 3:
                    print(f"  ... and {len(results) - 3} more")
            else:
                print(f"✗ No data found for property '{prop}'")
                
        except Exception as e:
            print(f"✗ Error querying property '{prop}': {e}")

def list_all_devices():
    """List all devices in InfluxDB"""
    print("\n=== Listing All Devices in InfluxDB ===")
    
    client = InfluxDBClient(logger=logger)
    
    # Query to get all unique device names
    query = 'SHOW TAG VALUES FROM "device_changes" WITH KEY = "name"'
    
    try:
        results = client.execute_query(query)
        
        if results:
            print(f"Found {len(results)} devices:")
            for i, result in enumerate(results):
                device_name = result.get('value', 'Unknown')
                print(f"{i+1}. {device_name}")
                
                # Check if this matches our target
                if "joellen" in device_name.lower() or "presence" in device_name.lower():
                    print(f"   ^^^ Possible match for JoEllen presence!")
        else:
            print("No devices found in InfluxDB")
            
    except Exception as e:
        print(f"Error listing devices: {e}")

def test_exact_device_match():
    """Test various device name variations"""
    print("\n=== Testing Device Name Variations ===")
    
    client = InfluxDBClient(logger=logger)
    
    # Try various name patterns
    variations = [
        "JoEllen home presence",
        "JoEllen Home Presence",
        "joellen home presence",
        "JOELLEN HOME PRESENCE",
        "JoEllen_home_presence",
        "JoEllen-home-presence",
        "JoEllen",
        "Home Presence - JoEllen",
        "JoEllen Presence"
    ]
    
    for name in variations:
        query = f'SELECT COUNT(*) FROM "device_changes" WHERE "name" = \'{name}\' AND time > now() - 30d'
        
        try:
            results = client.execute_query(query)
            if results and results[0].get('count_onState', 0) > 0:
                print(f"✓ Found data for: {name}")
                # Get a sample of the data
                sample_query = f'SELECT * FROM "device_changes" WHERE "name" = \'{name}\' ORDER BY time DESC LIMIT 5'
                sample_results = client.execute_query(sample_query)
                if sample_results:
                    print(f"  Latest entry: {sample_results[0]}")
        except Exception as e:
            logger.debug(f"Error checking {name}: {e}")

def main():
    """Run all tests"""
    print("Starting InfluxDB diagnostic tests...")
    
    # Test connection
    if not test_influxdb_connection():
        print("\n!!! Cannot proceed without InfluxDB connection")
        return
    
    # Get database info
    test_database_info()
    
    # List all devices
    list_all_devices()
    
    # Test exact name matches
    test_exact_device_match()
    
    # Test specific device query
    test_device_query("JoEllen home presence")
    
    print("\n=== Diagnostic Complete ===")

if __name__ == "__main__":
    main()