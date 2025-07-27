# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an Indigo MCP (Model Context Protocol) Server plugin that provides AI assistants like Claude with access to Indigo Domotics home automation system. The plugin implements a FastMCP server with HTTP transport, semantic search capabilities and read-only access to Indigo entities.

## Plugin Structure

```
MCP Server.indigoPlugin/
├── Contents/
│   ├── Info.plist           # Plugin metadata (version, identifier, API version)
│   └── Server Plugin/
│       ├── plugin.py        # Main plugin with MCP server implementation
│       ├── Actions.xml      # Defines plugin actions (currently unused)
│       ├── MenuItems.xml    # Plugin menu items
│       ├── PluginConfig.xml # Configuration UI
│       ├── requirements.txt # Python dependencies
│       ├── common/
│       │   ├── __init__.py
│       │   └── vector_store.py  # LanceDB vector store for embeddings
│       └── search_entities/
│           ├── __init__.py
│           └── search_tool.py   # Natural language search tool
```

## Key Components

### FastMCP Server (plugin.py)
- Runs FastMCP server using HTTP transport for better performance and reliability
- Configurable HTTP port (default: 8080)
- Provides one tool: `search_entities` for natural language search
- Provides resources for read-only access via HTTP endpoints:
  - `/devices` - List all devices
  - `/devices/{id}` - Get specific device
  - `/variables` - List all variables
  - `/variables/{id}` - Get specific variable
  - `/actions` - List all action groups
  - `/actions/{id}` - Get specific action

### Vector Store (common/vector_store.py)
- Uses LanceDB for vector embeddings
- Stores embeddings for devices, variables, and actions
- Supports semantic search with OpenAI embeddings
- Auto-updates when entities change

### Search Tool (search_entities/search_tool.py)
- Natural language search interface
- Parses queries to determine search parameters
- Returns relevance-scored results

## Development Commands

### Deploy to Production Server
```bash
cd /Users/mike/Mike_Sync_Documents/Programming/mike-local-development-scripts
./deploy_indigo_plugin_to_server.sh /Users/mike/Mike_Sync_Documents/Programming/indigo-mcp-server/MCP Server.indigoPlugin
```

### Dependencies

- **Requirements File Synchronization**
  - Always keep `requirements.txt` in sync with 'MCP Server.indigoPlugin/Contents/Server Plugin/requirements.txt' and 'requirements.txt' in the root folder.
  - When adding a new Python library via pip in the virtual environment, update BOTH requirements.txt files to ensure dependency consistency

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

## MCP Integration

To use with Claude Desktop, add to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "indigo": {
      "command": "npx",
      "args": ["@anthropic/mcp-client", "http://127.0.0.1:8080"]
    }
  }
}
```

**Note**: Update the port number (8080) to match your configured server port.

## FastMCP Design Architecture

This plugin uses FastMCP with Streamable HTTP transport for improved performance and reliability over the standard MCP stdio transport.

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

## Testing MCP Tools

Example queries for testing:
- "Find all light switches"
- "Show me temperature sensors"
- "List all scenes"
- "Find devices in the bedroom"
- "Show all variables with value true"

## Development Environment

- **Plugin Symbolic Link**: The plugin is symbolic linked to my Indigo plugins folder: /Library/Application Support/Perceptive Automation/Indigo 2024.2/Plugins/MCP Server.indigoPlugin/.  Make any reads or changes using the local repository.