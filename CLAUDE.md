# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an Indigo MCP (Model Context Protocol) Server plugin that provides AI assistants like Claude with access to Indigo Domotics home automation system. The plugin implements an MCP server with semantic search capabilities and read-only access to Indigo entities.

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

### MCP Server (plugin.py)
- Runs MCP server using stdio transport
- Provides one tool: `search_entities` for natural language search
- Provides resources for read-only access:
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

### Install Dependencies
```bash
pip install -r "MCP Server.indigoPlugin/Contents/Server Plugin/requirements.txt"
```

Dependencies:
- mcp - Model Context Protocol SDK
- lancedb - Vector database
- pyarrow - Required by LanceDB
- openai - For embeddings
- pyyaml - YAML support
- dicttoxml - XML support

## Plugin Configuration

The plugin requires:
- **OpenAI API Key**: For generating embeddings for semantic search
- **Debug Mode**: Optional debug logging

## MCP Integration

To use with Claude Desktop, add to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "indigo": {
      "command": "indigo-plugin-host",
      "args": ["com.vtmikel.mcp_server"]
    }
  }
}
```

## Plugin Development Notes

1. **Indigo API Version**: The plugin targets Indigo Server API version 3.6
2. **Plugin Version**: 2025.0.1
3. **Bundle ID**: com.vtmikel.mcp_server
4. **MCP Transport**: Uses stdio for local communication
5. **Vector Store**: Located at `{Indigo}/Preferences/Plugins/com.vtmikel.mcp_server/vector_db`

## Testing MCP Tools

Example queries for testing:
- "Find all light switches"
- "Show me temperature sensors"
- "List all scenes"
- "Find devices in the bedroom"
- "Show all variables with value true"