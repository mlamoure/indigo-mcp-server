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
│           └── tools/
│               ├── __init__.py
│               ├── search_entities.py    # Natural language search tool
│               ├── query_parser.py       # Query parsing logic
│               └── result_formatter.py   # Result formatting
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
- Provides one tool: `search_entities` for natural language search

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
- **SearchEntitiesHandler**: Natural language search coordination (search_entities.py)
- **QueryParser**: Parses user queries for entity types and parameters
- **ResultFormatter**: Formats search results with relevance scoring

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
      "args": ["mcp-remote", "http://localhost:8080/mcp"]
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