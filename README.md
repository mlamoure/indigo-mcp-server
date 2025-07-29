# Indigo MCP Server Plugin

A Model Context Protocol (MCP) server plugin for Indigo Domotics that enables AI assistants like Claude to interact with
your home automation system through natural language queries.

## Demo Video

![Indigo MCP Demo](static/Indigo%20MCP.mov)

*Watch the Indigo MCP Server in action with Claude Desktop*

## What It Does

The Indigo MCP Server Plugin bridges the gap between AI assistants and your Indigo home automation system by providing
ways to search, and take action on your devices, variables, and actions.

Example queries you can use:

- "Find all light switches in the bedroom" - Returns comprehensive lighting device data
- "Show me temperature sensors" - Finds all temperature and environmental sensors with full properties
- "List all scenes related to evening lighting" - Searches action groups for scene-like entities
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