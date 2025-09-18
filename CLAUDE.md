# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an Indigo MCP (Model Context Protocol) Server plugin that provides AI assistants like Claude with access to
Indigo Domotics home automation system. The plugin implements a FastMCP server with HTTP transport, semantic search
capabilities and read-only access to Indigo entities.

## Python Environment

This project uses a virtual environment in the .venv folder
Use source .venv/bin/activate to activate the virtual environment

## System Requirements

- **macOS**: 10.15 (Catalina) or later
- **Python**: 3.9+ (as required by dependencies)
- **PyArrow**: 21.0.0+ (latest with pre-built wheels for macOS 10.15+)

## Plugin Structure

```
MCP Server.indigoPlugin/
├── Contents/
│   ├── Info.plist           # Plugin metadata (version, identifier, API version)
│   └── Server Plugin/
│       ├── plugin.py        # Main plugin entry point
│       ├── Actions.xml      # Defines plugin actions (currently unused)
│       ├── MenuItems.xml    # Plugin menu items
│       ├── PluginConfig.xml # Configuration UI
│       ├── requirements.txt # Python dependencies
│       └── mcp_server/
│           ├── __init__.py
│           ├── core.py        # Core MCP server implementation
│           ├── adapters/      # Data access layer
│           │   ├── __init__.py
│           │   ├── data_provider.py           # Abstract data provider interface
│           │   ├── indigo_data_provider.py    # Indigo-specific data provider
│           │   └── vector_store_interface.py  # Vector store interface
│           ├── common/
│           │   ├── __init__.py
│           │   ├── json_encoder.py            # JSON encoding utilities
│           │   ├── state_filter.py            # State filtering utilities
│           │   ├── indigo_device_types.py     # Device classification system
│           │   ├── influxdb/                  # InfluxDB integration
│           │   │   ├── __init__.py
│           │   │   ├── main.py                # Main InfluxDB interface
│           │   │   ├── client.py              # InfluxDB client
│           │   │   ├── queries.py             # Query builders
│           │   │   └── time_utils.py          # Time utility functions
│           │   ├── openai_client/             # OpenAI client utilities
│           │   │   ├── __init__.py
│           │   │   ├── main.py
│           │   │   └── langsmith_config.py
│           │   └── vector_store/              # Vector store implementation
│           │       ├── __init__.py
│           │       ├── main.py                # LanceDB vector store implementation
│           │       ├── progress_tracker.py    # Progress tracking for vector operations
│           │       ├── semantic_keywords.py   # Semantic keyword extraction
│           │       └── vector_store_manager.py # Vector store lifecycle management
│           ├── handlers/      # Shared handler utilities
│           │   ├── __init__.py
│           │   └── list_handlers.py           # Shared listing functionality
│           ├── resources/     # MCP resource handlers
│           │   ├── __init__.py
│           │   ├── devices.py   # Device resource endpoints
│           │   ├── variables.py # Variable resource endpoints
│           │   └── actions.py   # Action resource endpoints
│           ├── security/      # Security and authentication
│           │   ├── __init__.py
│           │   ├── auth_manager.py    # Authentication management
│           │   ├── cert_manager.py    # Certificate management
│           │   └── security_config.py # Security configuration
│           └── tools/         # MCP tool implementations
│               ├── __init__.py
│               ├── base_handler.py            # Base handler architecture
│               ├── search_entities/           # Natural language search
│               │   ├── __init__.py
│               │   ├── main.py                # SearchEntitiesHandler implementation
│               │   ├── query_parser.py        # Query parsing logic
│               │   └── result_formatter.py    # Result formatting
│               ├── device_control/            # Device control tools
│               │   ├── __init__.py
│               │   └── device_control_handler.py
│               ├── variable_control/          # Variable control tools
│               │   ├── __init__.py
│               │   └── variable_control_handler.py
│               ├── action_control/            # Action group control
│               │   ├── __init__.py
│               │   └── action_control_handler.py
│               ├── get_devices_by_type/       # Device type filtering
│               │   ├── __init__.py
│               │   └── main.py
│               └── historical_analysis/       # Historical data analysis
│                   ├── __init__.py
│                   └── main.py
```

## Key Components

### Plugin Entry Point (plugin.py)

- Main Indigo plugin class with lifecycle management
- Sets up environment variables for vector store database path (DB_FILE)
- Initializes data provider and delegates MCP server management to MCPServerCore
- Handles plugin configuration and validation

### MCP Server Core (mcp_server/core.py)

- Core MCP server implementation using FastMCP with HTTP transport
- Manages vector store lifecycle through VectorStoreManager
- Initializes and coordinates resource handlers
- Provides multiple tools for search, control, and analysis

### Data Access Layer (mcp_server/adapters/)

- **IndigoDataProvider**: Accesses Indigo entities using `dict(indigo_entity)` for direct object serialization
- **DataProvider**: Abstract interface for data access
- **VectorStoreInterface**: Abstract interface for vector operations

### Vector Store (mcp_server/common/vector_store/)

- **VectorStore**: LanceDB implementation with OpenAI embeddings (main.py)
- **VectorStoreManager**: Handles lifecycle, background updates, and synchronization
- **ProgressTracker**: Tracks vector store operation progress
- **SemanticKeywords**: Semantic keyword extraction for enhanced search
- Database path configured via DB_FILE environment variable

### OpenAI Client (mcp_server/common/openai_client/)

- **OpenAI Client**: Centralized OpenAI API client management
- **LangSmith Config**: Optional LangSmith integration for observability

### Security Layer (mcp_server/security/)

- **AuthManager**: Authentication and authorization management
- **CertManager**: SSL/TLS certificate management
- **SecurityConfig**: Security configuration settings

### Handlers System (mcp_server/handlers/)

- **ListHandlers**: Shared handlers for listing Indigo entities
- Provides consistent behavior between MCP tools and resources
- Handles state filtering and device type classification
- Used by both listing tools and resource endpoints

### Common Utilities (mcp_server/common/)

- **StateFilter**: Advanced state filtering with complex operators (gt, gte, lt, lte, eq, ne, contains, regex)
- **IndigoDeviceTypes**: Device classification system for logical device type mapping
- **JSONEncoder**: JSON encoding utilities for Indigo objects
- **InfluxDB Integration**: Historical data access and time-series analysis

### InfluxDB Integration (mcp_server/common/influxdb/)

- **InfluxDBClient**: Client interface for InfluxDB connections
- **QueryBuilder**: Flux query construction for historical data
- **TimeUtils**: Time range handling and timezone utilities
- **Main Interface**: High-level API for historical data analysis
- Supports configurable time ranges and device filtering

### Base Handler Architecture (mcp_server/tools/)

- **BaseHandler**: Common base class for all MCP tool handlers
- Provides logging, error handling, and validation
- Standardizes tool implementation patterns
- Enables consistent tool behavior and error reporting

### Resource Handlers (mcp_server/resources/)

- **DeviceResource**: HTTP endpoints for device data
- **VariableResource**: HTTP endpoints for variable data
- **ActionResource**: HTTP endpoints for action group data
- Each provides list and individual entity endpoints

### Search System (mcp_server/tools/)

- **search_entities/**: Natural language search tool library
    - **SearchEntitiesHandler**: Natural language search coordination (main.py)
    - **QueryParser**: Parses user queries for entity types and parameters (default similarity threshold: 0.15)
    - **ResultFormatter**: Formats search results with full device properties and relevance scoring
    - **Enhanced Search**: Returns all results above similarity threshold (no artificial limits)

## Development Commands

### Deploy to Production Server

```bash
cd /Users/mike/Mike_Sync_Documents/Programming/mike-local-development-scripts
./deploy_indigo_plugin_to_server.sh /Users/mike/Mike_Sync_Documents/Programming/indigo-mcp-server/MCP Server.indigoPlugin
```

### Running Tests

To run the test suite:

```bash
# Activate virtual environment
source .venv/bin/activate

# Set Python path and run tests
PYTHONPATH="MCP Server.indigoPlugin/Contents/Server Plugin:$PYTHONPATH" python -m pytest tests/ -v --tb=short

# Run specific test file
PYTHONPATH="MCP Server.indigoPlugin/Contents/Server Plugin:$PYTHONPATH" python -m pytest tests/test_mock_vector_store.py -v --tb=short

# Run tests with coverage
PYTHONPATH="MCP Server.indigoPlugin/Contents/Server Plugin:$PYTHONPATH" python -m pytest tests/ --cov=mcp_server --cov-report=term-missing
```

**Test Environment Requirements:**

- Virtual environment must be activated
- Python path must include plugin directory
- Some tests require specific environment variables (see `.env` file)
- Tests that require the `indigo` module will be skipped in non-Indigo environments

**Note:** The test suite includes 343 tests covering unit tests, integration tests, and mock implementations of all
major components.

### Dependencies

- **Requirements File Synchronization**
    - Always keep `requirements.txt` in sync with 'MCP Server.indigoPlugin/Contents/Server Plugin/requirements.txt'
      and 'requirements.txt' in the root folder.
    - When adding a new Python library via pip in the virtual environment, update BOTH requirements.txt files to ensure
      dependency consistency

Dependencies:

- fastmcp - FastMCP library with HTTP transport support
- lancedb - Vector database
- pyarrow - Required by LanceDB
- openai - For embeddings
- pyyaml - YAML support
- dicttoxml - XML support

## Plugin Configuration

### Plugin-Level Configuration

The plugin requires these settings at the plugin level:

- **OpenAI API Key**: For generating embeddings for semantic search
- **Server Port**: HTTP port for FastMCP server (default: 8080, range: 1024-65535) 
- **Debug Mode**: Optional debug logging
- **LangSmith Integration**: Optional AI tracing and debugging
- **InfluxDB Integration**: Optional historical data analysis

### Device-Level Configuration ⭐ NEW

**Important Architectural Change**: The plugin now uses a custom **MCP Server device** for server access configuration instead of plugin preferences.

#### MCP Server Device

The plugin creates/manages a single MCP Server device with the following:

**Device Configuration**:
- **Server Name**: Display name for the MCP Server instance
- **Server Access**: Control how the server accepts connections
  - Local Only (127.0.0.1): Recommended for security
  - Remote Access (HTTP only): For network access

**Device States** (Real-time monitoring):
- `serverStatus`: Running, Stopped, Starting, Error
- `serverPort`: Current HTTP port number
- `accessMode`: Local Only or Remote Access  
- `clientCount`: Number of connected clients
- `lastActivity`: Timestamp of last server activity

#### Benefits of Device-Based Configuration

1. **Real-time Monitoring**: Server status visible in Indigo interface
2. **Device-Level Control**: Start/stop server via Indigo device management
3. **Single Server Enforcement**: Plugin ensures only one MCP Server device exists
4. **Better Integration**: Native Indigo device lifecycle management
5. **Future Extensibility**: Foundation for advanced server features

#### Device Management

- **Single Device Validation**: Prevents creation of multiple MCP Server devices

## Environment Variables

The plugin uses the following environment variables (set automatically by the plugin):

- **DB_FILE**: Path to the LanceDB vector database directory
- **OPENAI_API_KEY**: OpenAI API key for embeddings generation

## MCP Integration

To use with Claude Desktop, add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "indigo": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "http://localhost:8080/mcp"
      ]
    }
  }
}
```

**Configuration Notes**:
- Update the port number (8080) to match your configured server port
- Use `localhost` for Local Only access mode (recommended)
- Use your server's IP address for Remote Access mode (configure firewall accordingly)
- Server access mode is controlled by the MCP Server device configuration

## MCP Protocol Compliance

This plugin implements the Model Context Protocol (MCP) 2025-06-18 specification with HTTP transport through Indigo's built-in web server.

### Protocol Version Support:

- **Supported Version**: MCP 2025-06-18 (current latest)
- **Previous Versions**: No longer supported (2025-03-26 and earlier)
- **Transport**: HTTP via Indigo Web Server (IWS) integration
- **Message Format**: JSON-RPC 2.0 (single messages only)

### MCP 2025-06-18 Compliance:

#### ✅ Implemented Features:
- **Protocol Version Negotiation**: Supports only 2025-06-18
- **Single Message Processing**: JSON-RPC 2.0 single message handling
- **Session Management**: Proper session ID validation and tracking
- **HTTP Transport**: Standards-compliant HTTP with proper headers
- **Tool System**: 15 comprehensive tools for Indigo interaction
- **Resource System**: Device, variable, and action group resources
- **Error Handling**: Proper JSON-RPC error responses

#### ❌ Removed Features (per 2025-06-18 spec):
- **JSON-RPC Batching**: No longer supported, returns error if attempted
- **Legacy Protocol Versions**: Only 2025-06-18 is accepted

#### ⚠️ Not Implemented (Optional Features):
- **Elicitation**: Server-initiated user prompts (new in 2025-06-18)
- **Resource Links**: Enhanced resource linking in tool responses
- **Structured Tool Output**: Advanced tool response formatting
- **OAuth Resource Server**: Security features (not needed for local-only access)
- **Resource Indicators (RFC 8707)**: Advanced token scoping (not applicable)

### Security Model:

- **Local Access Only**: Server accessible only through Indigo Web Server
- **No External Authentication**: Relies on Indigo's built-in security
- **Read-Only Operations**: Most operations are read-only for safety
- **Controlled Write Access**: Limited device/variable control with proper validation

### Technical Implementation:

- **Transport Layer**: HTTP via Indigo Web Server Actions.xml mapping
- **Protocol**: MCP 2025-06-18 over HTTP with JSON-RPC 2.0
- **Message Processing**: Single message only (batching rejected)
- **Header Validation**: Requires proper MCP headers for authenticated requests
- **Session Management**: Token-based session tracking
- **Error Handling**: Standards-compliant JSON-RPC error responses

## FastMCP Design Architecture

This plugin uses a custom MCP handler with HTTP transport for improved performance and reliability over the standard MCP stdio transport.

### Key Benefits of FastMCP with HTTP Transport:

1. **Better Performance**: HTTP transport reduces overhead and provides better throughput
2. **Reliability**: HTTP protocol provides better error handling and connection management
3. **Scalability**: Multiple clients can connect simultaneously
4. **Network Access**: Can be accessed remotely if needed (configure firewall accordingly)
5. **Standards-Based**: Uses standard HTTP protocols for better interoperability

### Technical Implementation:

- **Transport Layer**: HTTP server on configurable port (default: 8080)
- **Protocol**: FastMCP over HTTP with JSON-RPC 2.0
- **Authentication**: Local access only (127.0.0.1) for security
- **Resource Management**: Synchronous resource handlers for better integration with Indigo's threading model
- **Tool Execution**: Synchronous tool execution to avoid async/await complexity with Indigo API

### Security Considerations:

- Server binds only to localhost (127.0.0.1) for security
- No authentication required as access is local-only
- Consider firewall rules if remote access is needed
- All Indigo access is read-only via the plugin

## Plugin Development Notes

1. **Indigo API Version**: The plugin targets Indigo Server API version 3.6
2. **Plugin Version**: 2025.0.1
3. **Bundle ID**: com.vtmikel.mcp_server
4. **FastMCP Transport**: Uses HTTP transport for improved performance and reliability
5. **Vector Store**: Located at `{Indigo}/Preferences/Plugins/com.vtmikel.mcp_server/vector_db`

## MCP Tools and Resources

### Available Tools

The MCP server provides 15 comprehensive tools for interacting with your Indigo system:

#### Search and Discovery Tools

1. **search_entities**: Natural language search across all Indigo entities
    - Advanced semantic search using AI embeddings for context understanding
    - Intelligent result limiting: adjusts count and detail level based on query keywords
    - Default: 10 results, "few"/"some": 5 results, "many"/"list": 20 results, "all": 50 results
    - Automatic field optimization for large result sets (20+ results use minimal fields)
    - Supports device type filtering and optional state filtering
    - Enhanced with semantic keywords for improved search accuracy
    - Provides suggestions for using specialized tools when state queries detected

2. **get_devices_by_type**: Get all devices of a specific type
    - Returns ALL devices of specified logical type without semantic filtering
    - Supports device types: dimmer, relay, sensor, thermostat, sprinkler, multiio, speedcontrol, device
    - No result limits - complete device information with full properties
    - Ideal for type-based device discovery and inventory

#### Direct Entity Lookup Tools (NEW)

3. **get_device_by_id**: Get a specific device by its exact ID
    - Fast, precise device retrieval when you know the device ID
    - Returns complete device information or error if not found
    - Faster than semantic search for known device IDs
    - Example: `get_device_by_id(1994440374)` - Get device with ID 1994440374

4. **get_variable_by_id**: Get a specific variable by its exact ID
    - Fast, precise variable retrieval when you know the variable ID
    - Returns complete variable information or error if not found
    - Faster than semantic search for known variable IDs
    - Example: `get_variable_by_id(123456789)` - Get variable with specific ID

5. **get_action_group_by_id**: Get a specific action group by its exact ID
    - Fast, precise action group retrieval when you know the action group ID
    - Returns complete action group information or error if not found
    - Faster than semantic search for known action group IDs
    - Example: `get_action_group_by_id(987654321)` - Get action group with specific ID

#### Listing Tools (Complete Data Access)

6. **list_devices**: List all devices with optional state filtering
    - Returns ALL devices without semantic filtering or artificial limits
    - Optional advanced state filtering with complex operators
    - Supports conditions: gt, gte, lt, lte, eq, ne, contains, regex
    - Perfect for comprehensive device inventory and state-based queries
    - Example: `list_devices({"onState": true})` for all devices that are on

7. **list_variables**: List all variables
    - Returns ALL variables with current values
    - No filtering or limits - complete variable information
    - Ideal for variable inventory and value monitoring

8. **list_action_groups**: List all action groups  
    - Returns ALL action groups with descriptions
    - No filtering or limits - complete action group information
    - Perfect for scene and automation discovery

9. **get_devices_by_state**: Get devices by state conditions
    - Purpose-built for state-based device queries
    - Advanced state filtering with complex operators and conditions
    - Optional device type filtering for refined results
    - No artificial limits - returns all matching devices
    - Example: `get_devices_by_state({"onState": true}, ["dimmer"])` for on dimmers

#### Device Control Tools

10. **device_turn_on**: Turn on a device
    - Turns on device by device_id
    - Works with all controllable on/off devices
    - Returns success/failure status with details
    - **Enhanced**: Now waits 1 second and refreshes device state for accurate change detection

11. **device_turn_off**: Turn off a device  
    - Turns off device by device_id
    - Works with all controllable on/off devices
    - Returns success/failure status with details
    - **Enhanced**: Now waits 1 second and refreshes device state for accurate change detection

12. **device_set_brightness**: Set device brightness
    - Sets brightness level for dimmable devices
    - Accepts values 0-1 (float) or 0-100 (integer)
    - Automatically detects and validates device dimming capability
    - **Enhanced**: Now waits 1 second and refreshes device state for accurate change detection

#### Variable and Action Control

13. **variable_update**: Update variable value
     - Updates variable by variable_id with new string value
     - Works with all variable types
     - Returns updated variable information

14. **action_execute_group**: Execute action group
     - Executes action group by action_group_id
     - Optional delay parameter in seconds
     - Returns execution status and details

#### Historical Analysis (Advanced)

15. **analyze_historical_data**: AI-powered historical data analysis for devices and variables
     - **ENHANCED**: Now supports both devices AND variables in a single analysis
     - **IMPORTANT**: Requires EXACT entity names - use `search_entities`, `list_devices`, or `list_variables` first
     - **Device Analysis**: LLM-powered property selection for optimal device properties (1-3 most relevant)
     - **Variable Analysis**: Simplified value tracking (queries `value` field from `variable_changes`)
     - **Mixed Analysis**: Can analyze devices and variables together with automatic type detection
     - **Entity Type Control**: Optional `entity_type` parameter ("auto", "devices", "variables", "mixed")
     - Smart entity validation with similarity matching and type-specific suggestions
     - Analyzes entities over configurable time range (1-365 days, default: 30)
     - Enhanced formatting: devices show property context, variables show simple value changes
     - Requires InfluxDB integration for historical data access

### Available Resources

1. **Device Resources** (`/devices`):
    - `GET /devices` - List all devices with minimal properties
    - `GET /devices/{id}` - Get specific device with full properties
    - `GET /devices/by-type/{type}` - Get devices filtered by logical type (new)

2. **Variable Resources** (`/variables`):
    - `GET /variables` - List all variables
    - `GET /variables/{id}` - Get specific variable

3. **Action Resources** (`/actions`):
    - `GET /actions` - List all action groups
    - `GET /actions/{id}` - Get specific action group

### New Device Type Filtering

The `get_devices_by_type` endpoint supports logical device types:

- `dimmer` - Dimmable lights and controls
- `relay` - On/off switches and relays
- `sensor` - Temperature, motion, contact sensors
- `thermostat` - HVAC controls
- `sprinkler` - Irrigation controls
- `io` - Input/output devices
- `other` - Miscellaneous devices

## Testing MCP Tools

### Search Tool Examples:

- "Find all light switches" - Returns all lighting devices above 0.15 similarity
- "Show me temperature sensors" - Finds temperature and environmental sensors
- "List all scenes" - Searches action groups for scene-like entities
- "Find devices in the bedroom" - Location-based device search
- "Show all variables with value true" - Variable searches with value filtering
- "Get all dimmers" - Device type filtering for dimmable devices
- "Find motion sensors" - Sensor-specific searches
- "lights that are on" - **NEW**: Auto-detects state keyword and suggests using list_devices or get_devices_by_state

### NEW State-Based Query Examples:

- Complete device listings: `list_devices()` - All devices without limits
- State filtering: `list_devices({"onState": true})` - All devices that are on
- Complex conditions: `list_devices({"brightnessLevel": {"gt": 50}})` - Devices > 50% brightness
- Purpose-built state queries: `get_devices_by_state({"onState": true}, ["dimmer"])` - Dimmers that are on
- Multiple conditions: `get_devices_by_state({"onState": false, "errorState": ""})` - Off devices with no errors
- Complete variable listing: `list_variables()` - All variables with current values
- Complete action listing: `list_action_groups()` - All action groups

### NEW Direct Lookup Tool Examples:

- Get specific device: `get_device_by_id(1994440374)` - Fast retrieval when you know the device ID
- Get specific variable: `get_variable_by_id(123456789)` - Fast retrieval when you know the variable ID  
- Get specific action group: `get_action_group_by_id(987654321)` - Fast retrieval when you know the action group ID
- **Use case**: After finding entities with search tools, use direct lookup for subsequent operations
- **Performance**: Bypasses semantic search when exact ID is known

### Control Tool Examples:

- Turn on device ID 123: `device_turn_on(123)`
- Turn off all bedroom lights: First use `list_devices({"onState": true})` to find lights, then use
  `device_turn_off(device_id)` for each
- Set dimmer to 50%: `device_set_brightness(device_id, 50)` or `device_set_brightness(device_id, 0.5)`
- Update variable: `variable_update(variable_id, "new_value")`
- Execute scene: `action_execute_group(action_group_id)`
- Execute scene with delay: `action_execute_group(action_group_id, 30)` (30 second delay)
- **Enhanced**: All device control tools now provide accurate state change detection

### Historical Analysis Examples:

**✅ Device Analysis (EXACT device names):**
- `analyze_historical_data("show state changes", ["Front Door Sensor"], 7)` - Front door activity
- `analyze_historical_data("temperature trends", ["Living Room Thermostat"], 30)` - Temperature patterns  
- `analyze_historical_data("usage patterns", ["Garage Light Switch"], 14)` - Light activity

**✅ Variable Analysis (NEW):**
- `analyze_historical_data("track home status", ["someone_home"], 14)` - Home/away tracking
- `analyze_historical_data("mode changes", ["house_mode"], 7)` - House mode history
- `analyze_historical_data("security status", ["security_armed"], 30)` - Security arm/disarm patterns

**✅ Mixed Analysis (NEW - Devices + Variables):**
- `analyze_historical_data("activity when away", ["Front Door Sensor", "someone_home"], 7)` - Correlate activity with presence
- `analyze_historical_data("energy usage patterns", ["Main Panel Power", "house_mode"], 30)` - Power vs mode analysis

**🎯 Entity Type Control (NEW):**
- `analyze_historical_data("...", ["entities"], 7, "auto")` - Auto-detect entity types (default)
- `analyze_historical_data("...", ["devices"], 7, "devices")` - Devices only (strict validation)
- `analyze_historical_data("...", ["variables"], 7, "variables")` - Variables only (strict validation)

**❌ Common Mistakes:**
- Using fuzzy names: `["front door", "living room temp"]` → **WILL FAIL**
- Not using search first: Always use `search_entities("front door")` to find exact name "Front Door Sensor"

**🔧 Proper Workflow:**
1. `search_entities("front door")` → Find exact name: "Front Door Sensor"
2. `list_variables()` → Find variable names like "someone_home" 
3. `analyze_historical_data("show when opened/closed", ["Front Door Sensor"], 7)`
4. `analyze_historical_data("home status changes", ["someone_home"], 7)` (variable analysis)

**🤖 Device Property Selection (LLM-Powered):**
- Query: "show state changes" → AI selects: `["onState", "onOffState", "isPoweredOn"]`
- Query: "temperature trends" → AI selects: `["temperature", "temperatureInput1"]`
- Query: "brightness levels" → AI selects: `["brightness", "brightnessLevel"]`

**📊 Variable Value Tracking (Simplified):**
- Variables always query the `value` field from `variable_changes` measurement
- No property selection needed - variables have single value field
- Enhanced formatting: strings in quotes, numbers formatted appropriately

### Solving the "Lights That Are On" Problem:

**Before (Limited Results):**

- `search_entities("lights on")` - Returns only 10 lights, may miss devices

**After (Complete Results):**

- `list_devices({"onState": true})` - Returns ALL devices that are on
- `get_devices_by_state({"onState": true}, ["dimmer", "relay"])` - All lights that are on
- `search_entities("lights on")` - Now detects state query and suggests better tools

## Recent Improvements (2025.0.1-beta.3+)

### Search Performance and Accuracy Enhancements

**Issues Addressed:**
- **Duplicate Search Results**: Fixed vector store returning 8-10 duplicates of same device
- **Multiple Failed Searches**: Eliminated need for 4+ search attempts to find target devices
- **Inaccurate Device State**: Device control tools now provide reliable before/after state detection
- **LLM Query Expansion**: Fixed validation logic that was rejecting all query expansions

**Key Improvements:**
1. **Search Deduplication**: Vector store now automatically removes duplicate entries by entity ID
2. **Direct ID Lookup**: Added 3 new tools for fast entity retrieval when ID is known
3. **Enhanced Device Control**: All device commands wait 1 second and refresh state for accuracy
4. **Improved LLM Expansion**: Fixed overly restrictive validation allowing better semantic matching
5. **User-Friendly Logging**: Reduced debug verbosity with cleaner progress messages

**Performance Impact:**
- **Search Efficiency**: "turn off sunroom lamp" requests now succeed in 1-2 operations instead of 4+
- **State Accuracy**: Device control provides reliable change detection and status reporting
- **Result Quality**: Eliminated duplicate entries improving search result clarity

## Development Environment

- **Plugin Symbolic Link**: The plugin is symbolic linked to my Indigo plugins folder: /Library/Application
  Support/Perceptive Automation/Indigo 2024.2/Plugins/MCP Server.indigoPlugin/. Make any reads or changes using the
  local repository.