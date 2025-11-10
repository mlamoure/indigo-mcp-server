# Indigo MCP Server Plugin

A Model Context Protocol (MCP) server plugin that enables AI assistants like Claude to interact with your Indigo home
automation system through natural language queries.

## What It Does

Search, analyze, and control your Indigo devices using natural language:

- "Find all light switches in the bedroom"
- "Show me temperature sensors"
- "Turn on the garage lights"
- "What devices are currently on?"
- "Execute the bedtime scene"

## Requirements

- **Indigo Domotics**: 2024.2 or later
- **macOS**: 10.15 (Catalina) or later
- **CPU**: Intel Mac (2013+) or Apple Silicon (M1/M2/M3/M4)
    - Note: LanceDB (used for vector search) requires AVX2 CPU instructions
    - Most Intel Macs from 2013 onwards support AVX2
    - All Apple Silicon Macs are fully supported
- **Node.js**: Required for MCP client connection ([Download](https://nodejs.org/))
    - Provides `npx` command used by Claude Desktop configuration
    - Install via Homebrew: `brew install node`
    - Or download from [nodejs.org](https://nodejs.org/)
- **Claude Desktop**: Primary MCP client (ChatGPT support coming to Plus plan)
- **OpenAI API Key**: Required for semantic search ([Get API key](https://platform.openai.com/api-keys))
    - Sends device metadata to OpenAI for embeddings (minimal cost)
    - Only device names, types, descriptions sent - no sensitive data

## Installation

1. **Install Node.js**: If not already installed, install Node.js for `npx` command
   - Via Homebrew: `brew install node`
   - Or download from [nodejs.org](https://nodejs.org/)
   - Verify installation: `npx --version`
2. **Install Plugin**: Add MCP Server plugin to Indigo via Plugin Manager
3. **Configure Plugin**: Enter OpenAI API key in plugin preferences
4. **Create MCP Server Device**: Add new "MCP Server" device in Indigo
5. **Wait for Indexing**: Plugin will index your Indigo database (takes time on first run)
6. **Configure Claude Desktop**: Add configuration to `claude_desktop_config.json`

## Optional Features

- **InfluxDB Connection information**: Required for historical data analysis queries
- **LangSmith**: Optional debugging and tracing of AI prompts. Not needed for most people.

### MCP Server Device Setup

The MCP Server Indigo device is what creates the actual MCP Server.

- **Server Access**: Configured via MCP Server device in Indigo
- **Single Server**: Plugin enforces one MCP Server device per installation

### Authentication & Security

⚠️ **IMPORTANT**: All MCP connections require authentication using an Indigo API key as a Bearer token.

**How to obtain API keys:**

- **Local/LAN access**: Create a `secrets.json` file
  with [local secrets](https://wiki.indigodomo.com/doku.php?id=indigo_2024.2_documentation:indigo_web_server#local_secrets)
    - Location: `/Library/Application Support/Perceptive Automation/Indigo [VERSION]/Preferences/secrets.json`
    - See documentation link above for JSON format details
    - Note: Restart Indigo Web Server after creating/modifying this file
- **Remote access**: Use your Indigo Reflector API key from your Reflector settings

### Claude Desktop / MCP Client Configuration

For Claude Desktop -- Add one of the following configurations to
`~/Library/Application Support/Claude/claude_desktop_config.json` based on your use case:

In all cases, you will need an API Key. For this, you have two choices:

- **Indigo Reflector API Key**: Obtained from your Reflector settings
- **Local Secret**: Created in `secrets.json` file (
  see [documentation](https://wiki.indigodomo.com/doku.php?id=indigo_2024.2_documentation:indigo_web_server#local_secrets))

#### Scenario 1: HTTPS via Reflector (Most Common, Enables remote access outside your home)

**Use when:**

- Accessing Indigo from outside your local network
- Security: Encrypted connection with valid SSL certificate

```json
{
  "mcpServers": {
    "indigo": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://your-reflector-url.indigodomo.net/message/com.vtmikel.mcp_server/mcp/",
        "--header",
        "Authorization:Bearer YOUR_REFLECTOR_API_KEY"
      ]
    }
  }
}
```

**Setup:**

1. Configure Indigo Reflector in Web Server Settings
2. Use your Reflector API key
3. Replace `your-reflector-url.indigodomo.net` with your actual Reflector URL
4. Replace `YOUR_REFLECTOR_API_KEY` with your Reflector API key

#### Scenario 2: HTTPS on LAN with Self-Signed Certificate

```json
{
  "mcpServers": {
    "indigo": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://your-local-hostname-or-ip:8176/message/com.vtmikel.mcp_server/mcp/",
        "--header",
        "Authorization:Bearer YOUR_LOCAL_SECRET_KEY"
      ],
      "env": {
        "NODE_TLS_REJECT_UNAUTHORIZED": "0"
      }
    }
  }
}
```

**Setup:**

1. Create a local secret (
   see [local secrets documentation](https://wiki.indigodomo.com/doku.php?id=indigo_2024.2_documentation:indigo_web_server#local_secrets))
    - Create/edit: `/Library/Application Support/Perceptive Automation/Indigo [VERSION]/Preferences/secrets.json`
    - Restart Indigo Web Server after modifying
2. Replace `your-local-hostname-or-ip` with your Indigo server IP/hostname
3. Replace `YOUR_LOCAL_SECRET_KEY` with your generated local secret
4. `NODE_TLS_REJECT_UNAUTHORIZED=0` disables certificate validation (required for self-signed certs)
5. Replace port 8176 if you are not using the default Indigo Web Server port

#### Scenario 3: HTTP on Local/LAN

If you have HTTPS disabled on your Indigo Web Server.

```json
{
  "mcpServers": {
    "indigo": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "http://your-local-hostname-or-ip:8176/message/com.vtmikel.mcp_server/mcp/",
        "--allow-http",
        "--header",
        "Authorization:Bearer YOUR_LOCAL_SECRET_KEY"
      ]
    }
  }
}
```

**Setup:**

1. Create a local secret (
   see [local secrets documentation](https://wiki.indigodomo.com/doku.php?id=indigo_2024.2_documentation:indigo_web_server#local_secrets))
    - Create/edit: `/Library/Application Support/Perceptive Automation/Indigo [VERSION]/Preferences/secrets.json`
    - Restart Indigo Web Server after modifying
2. Replace `YOUR_LOCAL_SECRET_KEY` with your generated local secret
3. Replace `your-local-hostname-or-ip` with your server IP/hostname for LAN access
4. Replace port 8176 if you are not using the default Indigo Web Server port

## Pagination Support

**Important:** To handle large Indigo installations, list and search tools support pagination:

- **Default Limit**: 50 results per request
- **Maximum Limit**: 500 results per request
- **Parameters**: Add `limit` and `offset` to paginate through results
- **Response Metadata**: Returns `total_count`, `offset`, `has_more` for navigation

**Example:**
```python
# Get first 50 devices
list_devices(limit=50, offset=0)

# Get next 50 devices
list_devices(limit=50, offset=50)

# Search with pagination
search_entities("bedroom lights", limit=20)
```

**Tools with Pagination:** `search_entities`, `list_devices`, `list_variables`, `list_action_groups`, `get_devices_by_state`

## Available Tools

### Search and Query

- **search_entities**: Natural language search across devices, variables, action groups (pagination supported)
- **list_devices**: Get all devices with optional state filtering (pagination supported)
- **list_variables**: Get all variables with current values (pagination supported)
- **list_action_groups**: Get all action groups/scenes (pagination supported)
- **list_variable_folders**: Get all variable folders with IDs
- **get_devices_by_state**: Find devices by state conditions (pagination supported)
- **get_devices_by_type**: Get devices by type (dimmer, relay, sensor, etc.)
- **get_device_by_id**: Get specific device by exact ID
- **get_variable_by_id**: Get specific variable by exact ID
- **get_action_group_by_id**: Get specific action group by exact ID

### Device Control

- **device_turn_on/off**: Control device power state
- **device_set_brightness**: Set dimmer brightness (0-100 or 0-1)

### RGB Device Control

- **device_set_rgb_color**: Set RGB color using 0-255 values
- **device_set_rgb_percent**: Set RGB color using 0-100 percentages
- **device_set_hex_color**: Set RGB color using hex codes (#FF8000)
- **device_set_named_color**: Set RGB color using color names (954 XKCD colors + aliases)
- **device_set_white_levels**: Control white channels for RGBW devices

### Thermostat Control

- **thermostat_set_heat_setpoint**: Set heating temperature target
- **thermostat_set_cool_setpoint**: Set cooling temperature target
- **thermostat_set_hvac_mode**: Change HVAC operating mode (heat, cool, auto, off, program modes)
- **thermostat_set_fan_mode**: Control fan operation (auto, alwaysOn)

### Variable and Action Control

- **variable_create**: Create new variable with optional value and folder
- **variable_update**: Update variable values
- **action_execute_group**: Execute action groups/scenes

### System

- **query_event_log**: Query recent Indigo server event log entries
- **list_plugins**: List all installed Indigo plugins
- **get_plugin_by_id**: Get specific plugin information by ID
- **restart_plugin**: Restart an Indigo plugin
- **get_plugin_status**: Check plugin status and details

### Analysis

- **analyze_historical_data**: AI-powered historical analysis for devices and variables (requires InfluxDB)

## Improving Results

1. **Be Specific**: Use location and device type in queries
2. **Device Notes**: Add descriptions to device Notes field - included in AI context
3. **State vs Search**: Use `list_devices({"onState": true})` for state queries vs `search_entities("lights")`

## Privacy & Security

### Data Sent to OpenAI

When you first install the plugin and when devices are added or modified, the following device information is sent to
OpenAI to create semantic search capabilities:

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

This data is used only to generate embeddings (mathematical representations) that enable natural language search. The
embeddings are stored locally on your Indigo server.

### Network Security

- **Authentication Required**: All MCP connections require Bearer token authentication with Indigo API keys
- **Local Access**: HTTP on localhost/LAN is secure (traffic never leaves local network)
- **Remote Access**: Use Indigo Reflector for secure remote access with HTTPS and valid SSL certificates
- **Self-Signed Certificates**: If using HTTPS on LAN, set `NODE_TLS_REJECT_UNAUTHORIZED=0` (see Scenario 3 above)

## Support

- **Issues**: Submit on project repository
- **Questions**: [Indigo Domotics Forum](https://forums.indigodomo.com/viewforum.php?f=274)