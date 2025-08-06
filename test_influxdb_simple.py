#!/usr/bin/env python3
"""
Simple test script to diagnose InfluxDB query issues
"""

import os
from influxdb import InfluxDBClient

# Set up connection parameters
HOST = 'influx.home.mikelamoureux.net'
PORT = 8086
USERNAME = 'indigo'
PASSWORD = '4AFcW2AAMdvQUygWfQBxavu'
DATABASE = 'indigo'

def test_connection():
    """Test basic connection"""
    print("=== Testing InfluxDB Connection ===")
    
    client = InfluxDBClient(host=HOST, port=PORT, username=USERNAME, password=PASSWORD, database=DATABASE)
    
    try:
        # Test ping
        version = client.ping()
        print(f"✓ Connected to InfluxDB version: {version}")
        
        # List databases
        databases = client.get_list_database()
        print(f"Available databases: {[db['name'] for db in databases]}")
        
        return client
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return None

def list_devices(client):
    """List all devices in the database"""
    print("\n=== Listing All Devices ===")
    
    try:
        # Query to get all unique device names
        query = 'SHOW TAG VALUES FROM "device_changes" WITH KEY = "name"'
        results = client.query(query)
        
        devices = []
        for point in results.get_points():
            device_name = point.get('value', 'Unknown')
            devices.append(device_name)
            
            # Check for JoEllen related devices
            if any(word in device_name.lower() for word in ['joellen', 'jo ellen', 'presence', 'home']):
                print(f"  * {device_name} <-- Possible match!")
            else:
                print(f"  - {device_name}")
        
        print(f"\nTotal devices found: {len(devices)}")
        
        # Search for JoEllen specifically
        print("\n=== Searching for JoEllen-related devices ===")
        joellen_devices = [d for d in devices if 'joellen' in d.lower() or 'jo ellen' in d.lower()]
        if joellen_devices:
            print(f"Found {len(joellen_devices)} JoEllen-related devices:")
            for d in joellen_devices:
                print(f"  - {d}")
        else:
            print("No devices with 'JoEllen' in the name found")
            
        return devices
        
    except Exception as e:
        print(f"Error listing devices: {e}")
        return []

def test_device_data(client, device_name):
    """Test querying data for a specific device"""
    print(f"\n=== Testing Data for: {device_name} ===")
    
    try:
        # First, check if device exists
        check_query = f"SELECT COUNT(*) FROM \"device_changes\" WHERE \"name\" = '{device_name}'"
        result = client.query(check_query)
        points = list(result.get_points())
        
        if not points:
            print(f"✗ No data found for device: {device_name}")
            return
            
        # Get available fields for this device
        fields_query = f"SHOW FIELD KEYS FROM \"device_changes\""
        fields_result = client.query(fields_query)
        print("\nAvailable fields:")
        for point in fields_result.get_points():
            print(f"  - {point['fieldKey']} ({point['fieldType']})")
        
        # Query recent data
        data_query = f"""
            SELECT * FROM "device_changes" 
            WHERE "name" = '{device_name}' 
            ORDER BY time DESC 
            LIMIT 10
        """
        
        data_result = client.query(data_query)
        data_points = list(data_result.get_points())
        
        if data_points:
            print(f"\n✓ Found {len(data_points)} recent data points")
            print("\nMost recent entry:")
            latest = data_points[0]
            for key, value in latest.items():
                if value is not None and key != 'name':
                    print(f"  {key}: {value}")
        else:
            print("✗ No recent data found")
            
    except Exception as e:
        print(f"Error querying device data: {e}")

def search_presence_devices(client):
    """Search for presence-related devices"""
    print("\n=== Searching for Presence Devices ===")
    
    try:
        # Query for any device with 'presence' in the name
        query = """
            SELECT DISTINCT("name") as device_name 
            FROM "device_changes" 
            WHERE time > now() - 7d
            GROUP BY "name"
        """
        
        result = client.query(query)
        all_devices = []
        
        # Get unique device names
        for series in result:
            for point in series:
                if 'device_name' in point and point['device_name']:
                    all_devices.append(point['device_name'])
        
        # Filter for presence devices
        presence_devices = [d for d in all_devices if 'presence' in d.lower()]
        
        if presence_devices:
            print(f"Found {len(presence_devices)} presence devices:")
            for d in presence_devices:
                print(f"  - {d}")
        else:
            print("No presence devices found")
            
    except Exception as e:
        print(f"Error searching presence devices: {e}")

def main():
    """Run all tests"""
    print("Starting InfluxDB diagnostic tests...\n")
    
    # Test connection
    client = test_connection()
    if not client:
        return
    
    # List all devices
    devices = list_devices(client)
    
    # Search for presence devices
    search_presence_devices(client)
    
    # Test specific device
    test_device_data(client, "JoEllen home presence")
    
    # Try variations
    print("\n=== Testing Device Name Variations ===")
    variations = [
        "JoEllen Home Presence",
        "Home Presence - JoEllen",
        "JoEllen Presence",
        "JoEllen",
    ]
    
    for name in variations:
        print(f"\nTrying: {name}")
        query = f"SELECT COUNT(*) FROM \"device_changes\" WHERE \"name\" = '{name}' AND time > now() - 30d"
        try:
            result = client.query(query)
            points = list(result.get_points())
            if points and any(v > 0 for v in points[0].values() if isinstance(v, (int, float))):
                print(f"  ✓ Found data!")
                # Get a sample
                sample_query = f"SELECT * FROM \"device_changes\" WHERE \"name\" = '{name}' ORDER BY time DESC LIMIT 1"
                sample_result = client.query(sample_query)
                for point in sample_result.get_points():
                    print(f"  Latest: {point}")
            else:
                print(f"  ✗ No data")
        except Exception as e:
            print(f"  Error: {e}")
    
    client.close()
    print("\n=== Diagnostic Complete ===")

if __name__ == "__main__":
    main()