#!/usr/bin/env python3
"""
Test script using newer influxdb-client to diagnose query issues
"""

from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS

# Connection parameters
url = "http://influx.home.mikelamoureux.net:8086"
token = ""  # InfluxDB 1.x doesn't use tokens
org = "-"  # InfluxDB 1.x doesn't use orgs
username = "indigo"
password = "4AFcW2AAMdvQUygWfQBxavu"
database = "indigo"

def test_with_v1_compatibility():
    """Test using InfluxDB v1 compatibility API"""
    print("=== Testing InfluxDB Connection (v1 compatibility) ===")
    
    # For InfluxDB 1.x, we need to use username/password auth
    client = InfluxDBClient(
        url=url,
        username=username,
        password=password,
        org=org
    )
    
    try:
        # Get the query API with v1 compatibility
        query_api = client.query_api()
        
        # List all devices - v1 style query
        print("\n=== Listing All Devices ===")
        query = 'SHOW TAG VALUES ON "indigo" FROM "device_changes" WITH KEY = "name"'
        
        try:
            result = query_api.query(query=query, org=org)
            
            devices = []
            for table in result:
                for record in table.records:
                    device_name = record.get_value()
                    devices.append(device_name)
                    
                    # Check for JoEllen related devices
                    if any(word in device_name.lower() for word in ['joellen', 'jo ellen', 'presence']):
                        print(f"  * {device_name} <-- Possible match!")
                    
            print(f"\nTotal devices found: {len(devices)}")
            
            # Filter for JoEllen
            joellen_devices = [d for d in devices if 'joellen' in d.lower()]
            if joellen_devices:
                print(f"\nJoEllen devices found: {joellen_devices}")
            
        except Exception as e:
            print(f"Error with SHOW TAG VALUES: {e}")
            
        # Try a direct query for the device
        print("\n=== Testing Direct Query for 'JoEllen home presence' ===")
        
        # Build a Flux-like query for v1 data
        device_query = '''
        from(bucket: "indigo/autogen")
          |> range(start: -30d)
          |> filter(fn: (r) => r._measurement == "device_changes")
          |> filter(fn: (r) => r.name == "JoEllen home presence")
          |> limit(n: 10)
        '''
        
        try:
            result = query_api.query(query=device_query, org=org)
            
            count = 0
            for table in result:
                for record in table.records:
                    count += 1
                    print(f"  Found record: {record.get_time()} - {record.get_field()} = {record.get_value()}")
            
            if count == 0:
                print("  No data found for 'JoEllen home presence'")
                
        except Exception as e:
            print(f"Error with Flux query: {e}")
            print("  This might be because InfluxDB 1.x doesn't support Flux queries")
            
    finally:
        client.close()

def test_with_curl():
    """Test using curl to query InfluxDB directly"""
    print("\n=== Testing with curl commands ===")
    
    import subprocess
    
    # Base curl command
    base_cmd = [
        'curl', '-G', f'{url}/query',
        '-u', f'{username}:{password}',
        '--data-urlencode', f'db={database}'
    ]
    
    # List devices
    print("\nListing devices with curl:")
    list_cmd = base_cmd + ['--data-urlencode', 'q=SHOW TAG VALUES FROM "device_changes" WITH KEY = "name"']
    
    try:
        result = subprocess.run(list_cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print("✓ curl command successful")
            # Parse and display results
            import json
            data = json.loads(result.stdout)
            if 'results' in data and data['results']:
                values = data['results'][0].get('series', [{}])[0].get('values', [])
                print(f"Found {len(values)} devices")
                
                # Look for JoEllen
                for value in values:
                    if len(value) > 1 and 'joellen' in str(value[1]).lower():
                        print(f"  Found JoEllen device: {value[1]}")
        else:
            print(f"✗ curl command failed: {result.stderr}")
            
    except Exception as e:
        print(f"Error running curl: {e}")
    
    # Query specific device
    print("\nQuerying 'JoEllen home presence' with curl:")
    query_cmd = base_cmd + ['--data-urlencode', 
        'q=SELECT * FROM "device_changes" WHERE "name" = \'JoEllen home presence\' ORDER BY time DESC LIMIT 5']
    
    try:
        result = subprocess.run(query_cmd, capture_output=True, text=True)
        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)
            if 'results' in data and data['results'][0].get('series'):
                print("✓ Found data for 'JoEllen home presence'")
                series = data['results'][0]['series'][0]
                print(f"  Columns: {series.get('columns', [])}")
                values = series.get('values', [])
                if values:
                    print(f"  Latest entry: {values[0]}")
            else:
                print("✗ No data found for 'JoEllen home presence'")
        else:
            print(f"✗ Query failed: {result.stderr}")
            
    except Exception as e:
        print(f"Error: {e}")

def main():
    """Run all tests"""
    print("Starting InfluxDB diagnostic tests...\n")
    
    # Try v2 client with v1 compatibility
    test_with_v1_compatibility()
    
    # Try direct curl commands
    test_with_curl()
    
    print("\n=== Diagnostic Complete ===")

if __name__ == "__main__":
    main()