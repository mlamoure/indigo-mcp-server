# Indigo MCP Server Plugin

A Model Context Protocol (MCP) server plugin that enables AI assistants like Claude to interact with your Indigo home
automation system through natural language queries.

## What It Does

Search, analyize, and control your Indigo devices using natural language:

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

## Optional Features

- **InfluxDB Connection information**: Required for historical data analysis queries
- **LangSmith**: Optional debugging and tracing of AI prompts. Not needed for most people.

### MCP Server Device Setup

The MCP Server Indigo device is what creates the actual MCP Server.

- **Server Access**: Local Only or Remote Access
- **Single Server**: Plugin enforces one MCP Server device per installation

A note on security: Do not expose the MCP Server to internet. It was not designed for this purpose. In the future I may
implement the required security features, but will likely require collaboration with the Indigo devs.

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

- **analyze_historical_data**: AI-powered historical analysis (requires InfluxDB)

## Improving Results

1. **Be Specific**: Use location and device type in queries
2. **Device Notes**: Add descriptions to device Notes field - included in AI context
3. **State vs Search**: Use `list_devices({"onState": true})` for state queries vs `search_entities("lights")`

## Privacy & Security

### Data Sent to OpenAI

When you first install the plugin and when devices are added or modified, the following device information is sent to OpenAI to create semantic search capabilities:

**For Devices:**
- Device name
- Device description (Notes field)
- Device model
- Device type (dimmer, sensor, etc.)
- Device address

**For Variables:**
- Variable name
- Variable description

**For Action Groups:**
- Action group name
- Action group description

**What is NOT sent:**
- Device states or current values
- URLs, passwords, or authentication credentials
- IP addresses or network configuration
- Historical data or usage patterns

This data is used only to generate embeddings (mathematical representations) that enable natural language search. The embeddings are stored locally on your Indigo server.

### Network Security

- **Local Server**: Binds to localhost by default (configurable via MCP Server device)
- **No Internet Exposure**: Never expose the HTTP server to internet - it lacks authentication

## Support

- **Issues**: Submit on project repository
- **Questions**: [Indigo Domotics Forum](https://forums.indigodomo.com/viewforum.php?f=274)