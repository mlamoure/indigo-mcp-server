#!/usr/bin/env python3
"""
Simple test script to verify debug logging is working on production MCP server
"""

import requests
import json
import sys

def test_initialize_with_logging():
    """Test initialize request to trigger debug logging"""
    
    url = "https://vtmikel.indigodomo.net/message/com.vtmikel.mcp_server/mcp"
    headers = {
        "Authorization": "Bearer f1eb0796-dff0-484b-a17d-3a04c24b335c",
        "Content-Type": "application/json",
        "Accept": "text/event-stream"
    }
    
    payload = {
        "jsonrpc": "2.0",
        "method": "initialize", 
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {
                "roots": {"listChanged": True},
                "sampling": {}
            },
            "clientInfo": {
                "name": "Debug Test Client",
                "version": "1.0.0"
            }
        },
        "id": 1
    }
    
    print("🔍 Testing MCP server debug logging...")
    print(f"📡 Endpoint: {url}")
    print(f"🔑 Bearer token: {headers['Authorization'][:20]}...")
    print(f"📄 Payload: {json.dumps(payload, indent=2)}")
    print()
    
    try:
        print("🚀 Sending initialize request...")
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        
        print(f"📊 Response Status: {response.status_code}")
        print(f"📋 Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            try:
                result = response.json()
                print(f"✅ Success! Response: {json.dumps(result, indent=2)}")
                
                # Check for session ID in headers
                session_id = response.headers.get('Mcp-Session-Id')
                if session_id:
                    print(f"🎫 Session ID received: {session_id}")
                    return session_id
                else:
                    print("⚠️  No session ID in response headers")
                    
            except json.JSONDecodeError as e:
                print(f"❌ Failed to parse JSON response: {e}")
                print(f"Raw response: {response.text}")
        else:
            print(f"❌ Request failed with status {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")
        return None
    
    return None

def test_tools_list(session_id):
    """Test tools/list request with session ID"""
    
    if not session_id:
        print("⚠️  Skipping tools/list test - no session ID")
        return
        
    url = "https://vtmikel.indigodomo.net/message/com.vtmikel.mcp_server/mcp"
    headers = {
        "Authorization": "Bearer f1eb0796-dff0-484b-a17d-3a04c24b335c",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "Mcp-Session-Id": session_id
    }
    
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/list",
        "params": {},
        "id": 2
    }
    
    print("\n🔧 Testing tools/list with session...")
    print(f"🎫 Session ID: {session_id}")
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        
        print(f"📊 Response Status: {response.status_code}")
        
        if response.status_code == 200:
            try:
                result = response.json()
                tools_count = len(result.get('result', {}).get('tools', []))
                print(f"✅ Success! Found {tools_count} tools")
            except:
                print(f"✅ Success! Response received")
        else:
            print(f"❌ Request failed with status {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")

def main():
    print("=" * 60)
    print("MCP Server Debug Logging Test")
    print("=" * 60)
    
    # Test initialize
    session_id = test_initialize_with_logging()
    
    # Test tools/list if we got a session
    test_tools_list(session_id)
    
    print("\n" + "=" * 60)
    print("Test completed!")
    print("📝 Check the Indigo plugin logs for detailed debug output")
    print("=" * 60)

if __name__ == "__main__":
    main()