# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an Indigo MCP (Model Context Protocol) Server plugin that provides AI assistants like Claude with access to
Indigo Domotics home automation system. The plugin implements a FastMCP server with HTTP transport, semantic search
capabilities and read-only access to Indigo entities.

## Python Enviornment

This project uses a virtual environment in the .venv folder
Use source .venv/bin/activate to activate the virtual environment

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
│               └── search_entities/      # Natural language search tool library
│                   ├── __init__.py
│                   ├── main.py           # SearchEntitiesHandler implementation
│                   ├── query_parser.py   # Query parsing logic
│                   └── result_formatter.py # Result formatting
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

**Note:** The test suite includes ~280 tests covering unit tests, integration tests, and mock implementations of all
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

The plugin requires:

- **OpenAI API Key**: For generating embeddings for semantic search
- **Server Port**: HTTP port for FastMCP server (default: 8080, range: 1024-65535)
- **Debug Mode**: Optional debug logging

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

**Note**: Update the port number (8080) to match your configured server port.

## FastMCP Design Architecture

This plugin uses FastMCP with Streamable HTTP transport for improved performance and reliability over the standard MCP
stdio transport.

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

1. **search_entities**: Natural language search across all Indigo entities
    - Returns all results above 0.15 similarity threshold with intelligent result limiting
    - Includes complete device properties (not filtered by default)
    - Supports device type filtering (dimmer, relay, sensor, etc.)
    - **NEW**: Optional state_filter parameter for post-search state filtering
    - **NEW**: Automatically detects state keywords and increases result limits
    - **NEW**: Provides suggestions for using specialized tools when state queries are detected
    - Enhanced with semantic keywords for better search accuracy

2. **list_devices**: List all devices with optional state filtering ⭐ NEW
    - Returns ALL devices without semantic filtering or limits
    - Optional state_filter parameter using Indigo state names
    - Perfect for queries like "all lights that are on": `list_devices({"onState": true})`
    - Supports complex conditions: `{"brightnessLevel": {"gt": 50}}`
    - Includes full device properties and states

3. **list_variables**: List all variables ⭐ NEW
    - Returns ALL variables with current values
    - No filtering or limits - complete variable information

4. **list_action_groups**: List all action groups ⭐ NEW
    - Returns ALL action groups with descriptions
    - No filtering or limits - complete action group information

5. **get_devices_by_state**: Get devices by state conditions ⭐ NEW
    - Purpose-built for state-based queries
    - Returns all devices matching state conditions without limits
    - Supports complex operators: gt, gte, lt, lte, eq, ne, contains, regex
    - Optional device type filtering
    - Examples: `get_devices_by_state({"onState": true}, ["dimmer"])`

6. **get_devices_by_type**: Get all devices of a specific type
    - Returns ALL devices of specified type without semantic filtering
    - Supports all device types: dimmer, relay, sensor, multiio, speedcontrol, sprinkler, thermostat, device
    - Includes complete device properties

7. **Device Control Tools**:
    - **device_turn_on**: Turn on a device by device_id
    - **device_turn_off**: Turn off a device by device_id
    - **device_set_brightness**: Set brightness level (0-1 or 0-100) for dimmable devices

8. **variable_update**: Update a variable's value
    - Updates variable by variable_id with new string value

9. **action_execute_group**: Execute an action group
    - Executes action group by action_group_id
    - Optional delay parameter in seconds

10. **analyze_historical_data**: Analyze historical device data using LangGraph workflow
    - Natural language queries about device behavior and patterns
    - Analyzes specified device names over configurable time range (1-365 days, default: 30)
    - Uses AI-powered analysis workflow for insights and trends

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

### Control Tool Examples:

- Turn on device ID 123: `device_turn_on(123)`
- Turn off all bedroom lights: First use `list_devices({"onState": true})` to find lights, then use
  `device_turn_off(device_id)` for each
- Set dimmer to 50%: `device_set_brightness(device_id, 50)` or `device_set_brightness(device_id, 0.5)`
- Update variable: `variable_update(variable_id, "new_value")`
- Execute scene: `action_execute_group(action_group_id)`
- Execute scene with delay: `action_execute_group(action_group_id, 30)` (30 second delay)

### Historical Analysis Examples:

- "How often did the front door sensor trigger last week?" with device_names=["Front Door Sensor"], time_range_days=7
- "What was the temperature pattern in the living room last month?" with device_names=["Living Room Thermostat"],
  time_range_days=30
- "When were the garage lights most active?" with device_names=["Garage Light Switch"], time_range_days=14

### Solving the "Lights That Are On" Problem:

**Before (Limited Results):**

- `search_entities("lights on")` - Returns only 10 lights, may miss devices

**After (Complete Results):**

- `list_devices({"onState": true})` - Returns ALL devices that are on
- `get_devices_by_state({"onState": true}, ["dimmer", "relay"])` - All lights that are on
- `search_entities("lights on")` - Now detects state query and suggests better tools

## Development Environment

- **Plugin Symbolic Link**: The plugin is symbolic linked to my Indigo plugins folder: /Library/Application
  Support/Perceptive Automation/Indigo 2024.2/Plugins/MCP Server.indigoPlugin/. Make any reads or changes using the
  local repository.