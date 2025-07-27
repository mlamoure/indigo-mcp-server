# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an Indigo MCP (Model Context Protocol) Server plugin that integrates AI models (OpenAI) with Indigo Domotics home automation system. The plugin provides API endpoints and actions for device information retrieval and appears to be designed to support LangChain/LangSmith integration and InfluxDB logging.

## Plugin Structure

```
MCP Server.indigoPlugin/
├── Contents/
│   ├── Info.plist           # Plugin metadata (version, identifier, API version)
│   └── Server Plugin/
│       ├── plugin.py        # Main plugin implementation
│       ├── Actions.xml      # Defines plugin actions
│       ├── MenuItems.xml    # Defines menu items
│       ├── PluginConfig.xml # Configuration UI definition
│       └── requirements.txt # Python dependencies (currently empty)
```

## Key Components

### Plugin Class (plugin.py)
- Main entry point: `Plugin` class inheriting from `indigo.PluginBase`
- Current functionality:
  - `get_device_info`: Returns device information in JSON/YAML/XML format
  - Menu items for stopping/restarting servers (methods not yet implemented)

### Configuration (PluginConfig.xml)
The plugin supports configuration for:
- OpenAI API integration (API key, model selection)
- Indigo Server API connection
- Hello Indigo API/UI servers (ports 8000/9000)
- InfluxDB logging
- LangSmith tracing

## Development Commands

### Deploy to Production Server
```bash
cd /Users/mike/Mike_Sync_Documents/Programming/mike-local-development-scripts
./deploy_indigo_plugin_to_server.sh /Users/mike/Mike_Sync_Documents/Programming/indigo-mcp-server/MCP Server.indigoPlugin
```

### Install Dependencies
If requirements.txt is populated in the future:
```bash
pip install -r "MCP Server.indigoPlugin/Contents/Server Plugin/requirements.txt"
```

## Plugin Development Notes

1. **Indigo API Version**: The plugin targets Indigo Server API version 3.6
2. **Plugin Version**: Currently at 2025.0.1
3. **Bundle ID**: com.vtmikel.mcp_server
4. **Dependencies**: The plugin imports `dicttoxml` and `yaml` but requirements.txt is empty - these may need to be added

## Next Steps for Implementation

Based on the configuration UI and current stub implementation, the plugin appears intended to:
1. Implement MCP server functionality for AI model integration
2. Add Hello Indigo API/UI server implementation
3. Implement InfluxDB device history logging
4. Add menu item handlers for server control
5. Integrate with LangChain/LangSmith for tracing

## Testing

Currently no test framework is implemented. When adding tests, consider:
- Unit tests for device info formatting
- Integration tests for API endpoints
- Mock tests for Indigo device interactions