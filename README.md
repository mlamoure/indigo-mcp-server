# Indigo MCP Server Plugin

A Model Context Protocol (MCP) server plugin that enables AI assistants like Claude to interact with your Indigo home automation system through natural language queries.

## What It Does

Search, monitor, and control your Indigo devices using natural language:

- "Find all light switches in the bedroom"
- "Show me temperature sensors" 
- "Turn on the garage lights"
- "What devices are currently on?"
- "Execute the bedtime scene"

## Requirements

- **Indigo Domotics**: 2024.2 or later
- **macOS**: 10.14 (Mojave) or later  
- **Claude Desktop**: Primary MCP client (ChatGPT support coming to Plus plan)
- **OpenAI API Key**: Required for semantic search ([Get API key](https://platform.openai.com/api-keys))
  - Sends device metadata to OpenAI for embeddings (minimal cost)
  - Only device names, types, descriptions sent - no sensitive data

## Installation

1. **Install Plugin**: Add MCP Server plugin to Indigo via Plugin Manager
2. **Configure Plugin**: Enter OpenAI API key in plugin preferences 
3. **Create MCP Server Device**: Add new "MCP Server" device in Indigo
4. **Wait for Indexing**: Plugin will index your Indigo database (takes time on first run)
5. **Configure Claude Desktop**: Add configuration to `claude_desktop_config.json`

### MCP Server Device Setup

The MCP Server device controls server access and provides real-time status:

- **Server Access**: Local Only (recommended) or Remote Access
- **Status Monitoring**: Running/Stopped, port, client count, last activity
- **Single Device**: Plugin enforces one MCP Server device per installation

### Claude Desktop Configuration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

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

Replace `localhost` with your server IP for remote access, and `8080` with your configured port.

## Available Tools

### Search and Query
- **search_entities**: Natural language search across devices, variables, action groups
- **list_devices**: Get all devices with optional state filtering  
- **list_variables**: Get all variables with current values
- **list_action_groups**: Get all action groups/scenes
- **get_devices_by_state**: Find devices by state conditions
- **get_devices_by_type**: Get devices by type (dimmer, relay, sensor, etc.)

### Control  
- **device_turn_on/off**: Control device power state
- **device_set_brightness**: Set dimmer brightness (0-100 or 0-1)
- **variable_update**: Update variable values
- **action_execute_group**: Execute action groups/scenes

### Analysis
- **analyze_historical_data**: AI-powered historical analysis (requires InfluxDB plugin)

## Optional Features

- **LangSmith**: Optional debugging and tracing of AI interactions
- **InfluxDB Plugin**: Required for historical data analysis queries

## Improving Results

1. **Be Specific**: Use location and device type in queries
2. **Device Notes**: Add descriptions to device Notes field - included in AI context
3. **State vs Search**: Use `list_devices({"onState": true})` for state queries vs `search_entities("lights")`

## Privacy & Security

- **Local Server**: Binds to localhost by default (configurable via MCP Server device)
- **OpenAI Usage**: Device metadata sent for embeddings, not sensitive configuration
- **No Internet Exposure**: Never expose the HTTP server to internet

## Troubleshooting

- **Server not responding**: Check MCP Server device status in Indigo
- **API errors**: Verify OpenAI API key and credits  
- **Indexing slow**: Normal on first run - wait for completion
- **Missing results**: Add specific device notes, use more specific queries

## Support

- **Issues**: Submit on project repository
- **Questions**: [Indigo Domotics Forum](https://forums.indigodomo.com/viewforum.php?f=274)