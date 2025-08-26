# MCP Server Debug Logging Enhancements

## Overview

Added comprehensive debug logging to the MCP server plugin to help diagnose client connection issues. The logging provides detailed visibility into:

- Request reception and parsing
- Authentication and header validation  
- Session management
- Protocol version negotiation
- Tool and resource handling

## Added Debug Logging Locations

### 1. Plugin Entry Point (`plugin.py`)

**Location**: `handle_mcp_endpoint()` method

**Added Logging**:
- 🌐 MCP endpoint access notification
- HTTP method and request details
- Raw IWS action properties inspection
- 🔑 Authentication header detection and masking
- Accept, Content-Type, and Mcp-Session-Id header logging
- ⚠️ Missing authentication warnings
- 🚀 Request delegation to MCP handler
- 📝 Response status and content length logging
- ✅ Success/warning indicators for response status

### 2. MCP Handler Initialization (`mcp_server/mcp_handler.py`)

**Location**: `__init__()` method

**Added Logging**:
- Initialization start/completion banners
- Protocol version configuration
- Session management initialization
- Vector store manager startup progress
- Tool and resource registration counts
- Component initialization confirmation

### 3. Request Processing (`mcp_server/mcp_handler.py`)

**Location**: `handle_request()` method

**Added Logging**:
- Incoming request details (method, headers, body length)
- Normalized header inspection
- Accept header validation
- JSON parsing success/failure
- HTTP method validation (GET vs POST)
- Content negotiation logging

### 4. Message Dispatching (`mcp_server/mcp_handler.py`)

**Location**: `_dispatch_message()` method

**Added Logging**:
- JSON-RPC message validation
- Method name and parameter logging
- Session ID validation and warnings
- Active session tracking
- Method routing decisions
- Unknown method warnings

### 5. Initialization Handler (`mcp_server/mcp_handler.py`)

**Location**: `_handle_initialize()` method

**Added Logging**:
- ========== Initialization banners ==========
- Protocol version comparison
- Client information logging
- ✅ Session creation success
- Session ID generation and tracking
- Server capabilities listing
- Session header notification
- ❌ Protocol version mismatch warnings
- Unsupported version error details

## Debug Logging Features

### Authentication Detection
```
🔑 Bearer token present: f1eb0796...335c
⚠️ No Authorization header found
```

### Session Management
```
Session 8kj9Jm2nQ1wR5tY7 validated and updated
❌ Invalid session ID: invalid_session_123
Active sessions: ['8kj9Jm2nQ1wR5tY7', 'aB3cD4eF5gH6iJ7k']
```

### Protocol Negotiation
```
========================================
MCP INITIALIZATION REQUEST
Requested protocol version: 2025-03-26
Our protocol version: 2025-03-26
Client info: {'name': 'Claude Desktop', 'version': '1.0.0'}
Request ID: 1
========================================
✅ Protocol version match - creating new session
```

### Request Flow
```
🌐 MCP ENDPOINT ACCESSED
HTTP Method: POST
Headers Count: 5
🔑 Bearer token present: f1eb0796...335c
Accept header: 'text/event-stream'
🚀 Delegating to MCP handler...
📝 Response status: 200
✅ MCP request processed successfully
```

## Testing

Created `tests/test_debug_logging.py` which:
- Tests initialize request with detailed client info
- Tests tools/list with session ID
- Validates session creation and header handling
- Confirms server responses

## Usage

1. **Enable Debug Logging**: Set the plugin's log level to DEBUG in Indigo plugin preferences
2. **Monitor Logs**: Watch the Indigo Event Log or Plugin Logs for detailed MCP request traces
3. **Client Troubleshooting**: Use the debug output to identify:
   - Missing or invalid authentication headers
   - Incorrect Accept headers (must be `text/event-stream` or `application/json`)
   - Session ID issues
   - Protocol version mismatches
   - Request parsing problems

## Key Debug Points for Client Issues

### Common Client Connection Problems:

1. **406 Not Acceptable**
   - Look for: `Invalid Accept header: 'xyz' - returning 406 Not Acceptable`
   - Solution: Client must send `Accept: text/event-stream` or `Accept: application/json`

2. **401 Unauthorized** 
   - Look for: `⚠️ No Authorization header found`
   - Solution: Client must send `Authorization: Bearer <token>`

3. **Session Issues**
   - Look for: `Missing or invalid Mcp-Session-Id`
   - Solution: Client must use session ID from initialize response

4. **Protocol Version Issues**
   - Look for: `❌ Unsupported protocol version: 2024-11-05`
   - Solution: Client must use protocol version `2025-03-26`

## Log Level Requirements

- **INFO**: Basic request flow and session creation
- **DEBUG**: Detailed headers, parameters, and validation steps
- **WARNING**: Authentication issues and protocol mismatches
- **ERROR**: Request parsing failures and internal errors

The enhanced logging provides complete visibility into the MCP protocol negotiation and request processing pipeline, making it much easier to diagnose client connection issues.