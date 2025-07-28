# Indigo MCP Server Plugin

A Model Context Protocol (MCP) server plugin for Indigo Domotics that enables AI assistants like Claude to interact with your home automation system through natural language queries.

## What It Does

The Indigo MCP Server Plugin bridges the gap between AI assistants and your Indigo home automation system by providing:

- **Natural Language Search**: Query your devices, variables, and action groups using conversational language
- **Semantic Understanding**: Advanced vector-based search that understands context and relationships
- **Read-Only Access**: Safe, non-destructive access to your home automation data
- **Real-Time Data**: Access current device states, variable values, and system information
- **FastMCP HTTP Transport**: High-performance HTTP-based MCP server for reliable communication

Example queries you can use:
- "Find all light switches in the bedroom"
- "Show me temperature sensors that are currently above 70 degrees"
- "List all scenes related to evening lighting"
- "What security devices are currently active?"

## Requirements

### Required
- **OpenAI API Key**: Essential for semantic search capabilities
  - Get your API key from [OpenAI Platform](https://platform.openai.com/api-keys)
  - Used for generating embeddings to power the vector search functionality
  - Costs are typically minimal for home automation queries

### Supported Systems
- **Indigo Domotics 2024.2** or later
- **macOS** (Indigo's supported platform)
- **Python 3.8+** (handled automatically by Indigo)

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
The plugin uses a vector database (LanceDB) to enable semantic search capabilities. Instead of simple text matching, it understands the meaning and context of your queries, making searches more intuitive and powerful.

### Setup Process
1. **Install the Plugin**: Copy the plugin to your Indigo plugins directory
2. **Configure API Key**: Enter your OpenAI API key in the plugin configuration
3. **Set Server Port**: Choose a port (default: 8080, range: 1024-65535)
4. **Initial Vector Store Build**: 
   - **First Run Time**: 5-15 minutes depending on your system size
   - **Process**: The plugin analyzes all your devices, variables, and action groups
   - **Storage**: Creates optimized search index in your Indigo preferences
   - **Background Updates**: Automatically maintains the index as your system changes

### Configuration Steps
1. Open Indigo Client → Plugins → MCP Server → Configure
2. Enter your OpenAI API Key (required)
3. Set desired server port (8080 recommended)
4. Optionally configure LangSmith or InfluxDB
5. Enable debug logging if troubleshooting
6. Save and restart the plugin

**⏱️ Patience Required**: The initial setup creates a comprehensive search index of your entire Indigo system. Larger systems with hundreds of devices may take longer to process initially.

## MCP Client Setup

### Claude Desktop Configuration
Add this configuration to your `claude_desktop_config.json` file:

```json
{
  "mcpServers": {
    "indigo": {
      "command": "npx",
      "args": ["mcp-remote", "http://localhost:8080/mcp"]
    }
  }
}
```

**Important**: Replace `8080` with your configured server port if different.

### Claude Desktop Config Location
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

### Other MCP Clients
The plugin works with any MCP-compatible client. Use the HTTP transport endpoint:
```
http://localhost:[YOUR_PORT]/mcp
```

### Tested Clients
- ✅ **Claude Desktop**: Fully tested and supported
- ⚠️ **Other MCP Clients**: Should work but not extensively tested

## Security and Privacy

### LLM Usage
**Important Privacy Considerations:**

- **OpenAI API**: Your device names, states, and descriptions are sent to OpenAI for embedding generation
- **Search Queries**: Natural language queries may be processed by OpenAI for semantic understanding
- **No Raw Data Storage**: OpenAI does not store your data permanently, but it does process it
- **Minimal Data**: Only device names, types, and descriptions are sent, not sensitive configuration details

### Vector Store Data
- **Local Storage**: All vector embeddings are stored locally on your Indigo server
- **Semantic Keywords**: The system generates descriptive keywords to improve search quality
- **No Cloud Storage**: Your home automation data never leaves your local network (except for OpenAI API calls)

### HTTP Server Security
⚠️ **Critical Security Warning**: 

- **Local Only**: Server binds to 127.0.0.1 (localhost) by default for security
- **No Internet Exposure**: **NEVER** expose this HTTP server to the internet
- **Firewall Protection**: Ensure your firewall blocks external access to the configured port
- **No Authentication**: Current version has no built-in authentication (see roadmap)

**Why This Matters**: The server provides read access to your entire home automation system. External exposure could allow unauthorized parties to gather detailed information about your home setup, schedules, and security devices.

### Recommended Security Practices
1. Keep the server in "Local Only" mode
2. Use firewall rules to restrict port access
3. Regularly rotate your OpenAI API key
4. Monitor plugin logs for unusual activity
5. Only use trusted MCP clients

## Improving Results

### Device Description Optimization
The semantic search works best when your Indigo devices have descriptive names and notes. Consider these tips:

#### Device Names
```
Good: "Master Bedroom Ceiling Light"
Better: "Master Bedroom Main Ceiling Light - Dimmer"
Best: "Master Bedroom Main Ceiling Light - LED Dimmer - Evening Scene Compatible"
```

#### Device Notes/Descriptions
Add contextual information in device notes:
```
"Living room temperature sensor for HVAC automation. 
Located near the main seating area. Used for evening 
comfort scheduling and energy optimization."
```

#### Location Context
Include room names and functional context:
```
"Kitchen Under-Cabinet LED Strip - Task Lighting - 
Automated with morning coffee scene and evening cleanup routine"
```

#### Functional Grouping
Use consistent naming for related devices:
```
"Security System - Front Door Sensor"
"Security System - Motion Detector - Living Room"  
"Security System - Window Sensor - Master Bedroom"
```

### Variable Optimization
Give variables descriptive names that explain their purpose:
```
Good: "hvac_mode" 
Better: "HVAC_System_Mode"
Best: "HVAC_System_Current_Mode_Heat_Cool_Auto"
```

## Roadmap

### Planned Features

#### SSL Support 
- **Challenge**: Complex certificate management in Indigo plugin environment
- **Complexity**: High - requires certificate generation, renewal, and key management
- **Timeline**: Future release - significant development effort required
- **Workaround**: Use local connections only for now

#### Authorization Tokens
- **Status**: Framework exists, implementation in progress  
- **Purpose**: Secure API access with bearer token authentication
- **Features**: Auto-generated tokens, configurable expiration, token regeneration
- **Timeline**: Next major release
- **Current**: Basic token generation implemented, full auth pending

#### Enhanced Historical Data
- **Dependency**: InfluxDB integration expansion
- **Features**: Time-series queries, trend analysis, historical device state searches
- **Use Cases**: "Show me all motion events last week", "When was the temperature highest yesterday?"

#### Multi-Protocol Support
- **Protocols**: WebSocket transport, stdio transport alongside HTTP
- **Benefits**: Better client compatibility, reduced overhead for some use cases
- **Complexity**: Medium - requires transport abstraction layer

### Community Contributions
We welcome contributions for:
- Additional MCP client testing and compatibility
- Security enhancements and best practices
- Performance optimizations
- Documentation improvements

---

## Support and Troubleshooting

### Plugin Logs
Enable debug logging in the plugin configuration to troubleshoot issues. Logs appear in the Indigo Event Log window.

### Common Issues
- **Slow Initial Setup**: Normal for large systems - vector store creation takes time
- **Search Results Empty**: Check OpenAI API key, verify devices have descriptive names
- **Connection Refused**: Verify port configuration matches MCP client settings
- **High OpenAI Costs**: Consider optimizing device descriptions to reduce API calls

### Version Information
- **Plugin Version**: 2025.0.1
- **Indigo API**: 3.6
- **FastMCP**: HTTP transport with JSON-RPC 2.0
- **Vector Store**: LanceDB with OpenAI embeddings

---

*This plugin provides read-only access to your Indigo system and is designed with security and privacy in mind. Always follow security best practices and never expose the HTTP server to untrusted networks.*