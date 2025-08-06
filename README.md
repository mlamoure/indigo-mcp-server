# Indigo MCP Server Plugin

A Model Context Protocol (MCP) server plugin for Indigo Domotics that enables AI assistants like Claude to interact with
your home automation system through natural language queries.

## What It Does

The Indigo MCP Server Plugin bridges the gap between AI assistants and your Indigo home automation system by providing
ways to search, and take action on your devices, variables, and actions.

Example queries you can use:

- "Find all light switches in the bedroom" - Returns comprehensive lighting device data
- "Show me temperature sensors" - Finds all temperature and environmental sensors with full properties
- "Get all dimmers" - Device type filtering for dimmable devices
- "Find motion sensors" - Sensor-specific searches with complete device information
- "Show devices in the basement" - Location-based searches with full device metadata

## Requirements

### Required

- **OpenAI API Key**: Essential for semantic search capabilities
    - Get your API key from [OpenAI Platform](https://platform.openai.com/api-keys)
    - Used for generating embeddings to power the vector search functionality
    - Costs are typically minimal for home automation queries

### Supported Systems

- **Indigo Domotics 2024.2** or later
- **Python 3.11+**

## Optional Items

### LangSmith (Testing and Debugging)

- **Purpose**: Advanced tracing and debugging of AI interactions
- **Benefits**: Monitor query performance, debug search results, optimize prompts
- **Setup**: Requires LangSmith API key and project configuration
- **Use Case**: Recommended for developers or users experiencing search issues

### InfluxDB (Historical Queries)

- **Purpose**: Access historical device data and trends
- **Benefits**: Query past device states, analyze usage patterns over time
- **Setup**: Requires running InfluxDB instance with Indigo historical data
- **Use Case**: Useful for users with existing InfluxDB logging setup

## Initial Setup

### Why Vector Store?

The plugin uses a vector database (LanceDB) to enable semantic search capabilities. Instead of simple text matching, it
understands the meaning and context of your queries, making searches more intuitive and powerful.

## API Features

### Available MCP Resources

#### Device Resources

- `GET /devices` - List all devices with minimal properties (for overview)
- `GET /devices/{id}` - Get specific device with complete properties
- `GET /devices/by-type/{type}` - Get devices filtered by logical type

#### Variable Resources

- `GET /variables` - List all variables
- `GET /variables/{id}` - Get specific variable

#### Action Resources

- `GET /actions` - List all action groups
- `GET /actions/{id}` - Get specific action group

### Available MCP Tools

#### 1. search_entities ⭐ ENHANCED

Natural language search across all Indigo entities with intelligent result limiting and state filtering:

- **Purpose**: Semantic search across devices, variables, and action groups with optional state-based filtering
- **Input**: Natural language query with smart modifiers and optional state conditions
- **NEW State Features**:
    - **State Filter Parameter**: Optional state conditions like `{"onState": true}` or `{"brightnessLevel": {"gt": 50}}`
    - **Automatic State Detection**: Recognizes state keywords ("on", "off", "bright", "dim") and adjusts search behavior
    - **Smart Suggestions**: When state queries are detected with limited results, suggests using dedicated state tools
    - **Increased Limits**: Automatically increases result limits for state-based queries to find more matches
- **Search Features**:
    - **Intelligent Result Limits**: Automatically adjusts based on query terms
        - Default: 10 results with full details
        - State queries: 50+ results to find matches after filtering
        - "few"/"some": 5 results with full details
        - "many"/"list": 20 results with minimal fields
        - "all": 50 results with minimal fields  
        - "one"/"single": 1 result with full details
    - **Performance Optimization**: Large result sets (20+) use minimal fields for faster responses
    - **Truncation Feedback**: Clear messages when results are limited with suggestions for better tools
    - **Semantic Enhancement**: AI embeddings with keyword expansion for improved matching
    - **Device Type Filtering**: Support for dimmer, relay, sensor, thermostat, sprinkler, io, other
- **Output**: Formatted results with relevance scoring, state filtering indicators, and tool suggestions

#### 2. list_devices ⭐ NEW

List all devices with optional state filtering - no limits, no semantic search:

- **Purpose**: Get ALL devices with complete information, optionally filtered by state
- **Input**: Optional `state_filter` parameter using Indigo state names
- **State Filtering Examples**:
    - `{"onState": true}` - All devices that are on
    - `{"brightnessLevel": {"gt": 50}}` - Devices with brightness > 50%
    - `{"onState": false, "errorState": ""}` - Off devices with no errors
    - `{"enabled": true}` - All enabled devices
- **Operators**: `gt`, `gte`, `lt`, `lte`, `eq`, `ne`, `contains`, `regex`
- **Output**: All matching devices with complete properties - **no artificial limits**

#### 3. list_variables ⭐ NEW

List all variables with current values:

- **Purpose**: Get ALL variables in the system
- **Input**: None (returns everything)
- **Output**: Complete variable list with IDs, names, values, and properties

#### 4. list_action_groups ⭐ NEW

List all action groups:

- **Purpose**: Get ALL action groups/scenes in the system
- **Input**: None (returns everything)  
- **Output**: Complete action group list with IDs, names, and descriptions

#### 5. get_devices_by_state ⭐ NEW

Purpose-built tool for state-based device queries:

- **Purpose**: Find devices matching specific state conditions without semantic search
- **Input**: 
    - `state_conditions`: Required state requirements using Indigo state names
    - `device_types`: Optional device type filtering (dimmer, relay, sensor, etc.)
- **Examples**:
    - `get_devices_by_state({"onState": true})` - All devices that are on
    - `get_devices_by_state({"onState": true}, ["dimmer"])` - All dimmers that are on
    - `get_devices_by_state({"brightnessLevel": {"lte": 50}})` - Devices dimmed to 50% or less
- **Output**: All matching devices with complete properties and summary statistics

#### 6. get_devices_by_type

Get all devices of a specific type without semantic filtering:

- **Purpose**: Retrieve ALL devices that match a specific device type
- **Input**: Device type (dimmer, relay, sensor, multiio, speedcontrol, sprinkler, thermostat, device)
- **Output**: All devices of the specified type with complete properties
- **Use Case**: When you need every device of a type, not contextual search results

#### 7. Device Control Tools

Direct device control capabilities:

- **device_turn_on**: Turn on a device by device_id
- **device_turn_off**: Turn off a device by device_id
- **device_set_brightness**: Set brightness level (0-1 or 0-100) for dimmable devices

#### 8. variable_update

Update Indigo variable values:

- **Purpose**: Modify variable values in your Indigo system
- **Input**: Variable ID and new value (as string)
- **Output**: Operation status and updated variable information

#### 9. action_execute_group

Execute Indigo action groups (scenes):

- **Purpose**: Trigger action groups/scenes in your Indigo system
- **Input**: Action group ID and optional delay in seconds
- **Output**: Execution status and confirmation

#### 10. analyze_historical_data

AI-powered historical data analysis using LangGraph workflow:

- **Purpose**: Analyze device behavior patterns and trends over time
- **Input**: Natural language query, device names list, time range (1-365 days, default: 30)
- **Features**:
    - Uses advanced AI workflow for data analysis
    - Provides insights and trend identification
    - Supports complex pattern recognition queries
- **Output**: Detailed analysis results with insights and visualizations

## Usage Guidelines

### Query Optimization for search_entities

The `search_entities` tool is designed to provide intelligent result limiting based on your query terms. Understanding these patterns will help you get the most relevant results efficiently:

#### Query Modifiers and Expected Results

| Query Pattern | Result Count | Field Detail | Example |
|---------------|--------------|--------------|---------|
| Default queries | 10 | Full fields | `"bedroom lights"` |
| "few" or "some" | 5 | Full fields | `"few motion sensors"` |
| "many" or "list" | 20 | Minimal fields | `"many dimmers"` |
| "all" | 50 | Minimal fields | `"all temperature sensors"` |
| "one" or "single" | 1 | Full fields | `"one thermostat"` |

#### Best Practices

**For Specific Searches:**
- Use specific terms: `"front door sensor"` instead of `"sensors"`  
- Include location: `"bedroom lights"` instead of `"lights"`
- Be descriptive: `"motion sensor in garage"` vs `"motion"`

**For Browsing Large Collections:**
- Use "all" for overview: `"all lights"` (returns 50 with minimal fields)
- Use "many" for moderate browsing: `"many switches"` (returns 20 with minimal fields)

**For Detailed Information:**
- Use "few" for detailed view: `"few thermostats"` (returns 5 with full details)
- Use specific names when known: `"living room thermostat"`

#### When Results Are Truncated

When you see messages like `"Found 855 entities (showing top 10 - use more specific query for additional results)"`:

1. **Make your query more specific**: Add location, device type, or function
2. **Use filtering**: Add `device_types=["dimmer"]` parameter for device-specific searches
3. **Use get_devices_by_type**: For complete device type listings without semantic filtering

#### Choosing Between Tools

- **Use search_entities when:** You want semantic/contextual matching, location-based searches, or natural language queries
- **Use get_devices_by_type when:** You need ALL devices of a specific type, no contextual filtering needed

### Example Scenarios

#### Scenario 1: State-Based Queries ⭐ NEW
```
Query: "summarize the lights that are on"
BEFORE: search_entities("lights on") → Returns only 10 lights, incomplete results
AFTER: list_devices({"onState": true}) → Returns ALL devices that are on (no limits)

Alternative approaches:
- get_devices_by_state({"onState": true}, ["dimmer", "relay"]) → All lights that are on
- search_entities("lights on") → Now detects state query and suggests better tools
```

#### Scenario 2: Complex State Filtering ⭐ NEW
```
Query: "Find all dimmers with brightness between 25% and 75%"
Solution: get_devices_by_state({
    "brightnessLevel": {"gte": 25, "lte": 75},
    "onState": true
}, ["dimmer"])

Result: All dimmer devices that are on with brightness 25-75%
Fields: Complete device properties with current states
Best for: Precise state-based device control
```

#### Scenario 3: Complete System Overview ⭐ NEW
```
Query: "Show me everything"
Solutions:
- list_devices() → ALL devices (no limits)
- list_variables() → ALL variables
- list_action_groups() → ALL action groups

Best for: System-wide status checks and comprehensive dashboards
```

#### Scenario 4: Specific Search (Full Details)
```
Query: "front door sensor"
Result: "Found 2 entities (2 devices)"
Fields: Full device properties including all states, settings, and metadata
Best for: Getting complete information about specific devices
```

#### Scenario 5: Browse All Devices (Minimal Fields)
```
Query: "show me all lights"  
Result: "Found 127 entities (showing 50 with minimal fields - use more specific query for additional results)"
Fields: name, class, id, deviceTypeId, description, model, onState, states
Best for: Getting an overview of many devices quickly
```

#### Scenario 6: Truncated Results with State Detection ⭐ ENHANCED
```
Query: "lights that are on"
Result: "State-based query detected with truncated results. 
         Consider using list_devices(state_filter={'onState': true}) for complete results."
Recommendation: Use dedicated state tools for complete information
```

#### Scenario 7: Error State Monitoring ⭐ NEW
```
Query: "Find all devices with communication errors"
Solution: get_devices_by_state({"errorState": {"ne": ""}})

Result: All devices with non-empty error states
Best for: System health monitoring and troubleshooting
```

## MCP Client Setup

### Claude Desktop Configuration

Add this configuration to your `claude_desktop_config.json` file:

```json
{
  "mcpServers": {
    "indigo": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "http://[your server]:8080/mcp"
      ]
    }
  }
}
```

Replace your ip or indigo server hostname, and port `8080` with your configured server port if different.

### Claude Desktop Config Location

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

### Other MCP Clients

The plugin works with any MCP-compatible client. Use the HTTP transport endpoint:

```
http://[your server]:[YOUR_PORT]/mcp
```

### Tested Clients

- ✅ **Claude Desktop**: Fully tested and supported
- ⚠️ **Other MCP Clients**: Should work but not extensively tested

## Security and Privacy

### LLM Usage

**Important Privacy Considerations:**

- **OpenAI API**: Your device names, states, and descriptions are sent to OpenAI for embedding generation
- **Search Queries**: Natural language queries may be processed by OpenAI for semantic understanding
- **Minimal Data**: Only device names, types, and descriptions are sent, not sensitive configuration details
- **Local Storage**: All vector embeddings are stored locally on your Indigo server

### HTTP Server Security

- **Local Only**: Server binds to 127.0.0.1 (localhost) by default for security
- If you decide to enable Remote acces, **No Internet Exposure**: **NEVER** expose this HTTP server to the internet

## Improving AI Results

You can add to the Notes of your devices, which will help guide the LLM.

## Roadmap

### Planned Features

* Add SSL Support (will be complex)
* Add Auth tokens

## Support and Troubleshooting

Add issues here.
Support questions, go to: https://forums.indigodomo.com/viewforum.php?f=274&sid=42b03ddd145b4f1309cb493be3bb2908