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
- **macOS**: 10.15 (Catalina) or later on compatible hardware (see CPU requirements below)
- **CPU**: Intel Haswell (2013+) or Apple Silicon required
    - **Compatible**: Mid-2013 MacBook Air/Pro and later, Late-2013 iMac and later, 2019 Mac Pro and later, all Apple Silicon Macs
    - **Incompatible**: 2012-2013 Intel Macs (Ivy Bridge or older), 2013 Mac Pro "trash can" (MacPro6,1)
    - Requires AVX2 instruction set support (check compatibility below)
- **Claude Desktop**: Primary MCP client (ChatGPT support coming to Plus plan)
- **OpenAI API Key**: Required for semantic search ([Get API key](https://platform.openai.com/api-keys))
    - Sends device metadata to OpenAI for embeddings (minimal cost)
    - Only device names, types, descriptions sent - no sensitive data

### CPU Compatibility

This plugin requires **AVX2 CPU instructions** (Intel Haswell or newer). The plugin will automatically check your CPU on startup and display a clear error if incompatible.

**To check if your Mac supports AVX2:**
```bash
sysctl -n machdep.cpu.leaf7_features | grep AVX2
```
If this command returns "AVX2", your Mac is compatible.

**Why AVX2 is required:** The plugin uses LanceDB for vector search, which requires AVX2 instructions for performance. There is no workaround for systems without AVX2 support.

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

- **Server Access**: Configured via MCP Server device in Indigo
- **Single Server**: Plugin enforces one MCP Server device per installation

### Authentication & Security

⚠️ **IMPORTANT**: All MCP connections require authentication using an Indigo API key as a Bearer token.

**How to obtain API keys:**
- **Local/LAN access**: Create a [local secret](https://wiki.indigodomo.com/doku.php?id=indigo_2024.2_documentation:indigo_web_server#local_secrets) at Indigo > Web Server Settings > Local Secrets
- **Remote access**: Use your Indigo Reflector API key from your Reflector settings

### Claude Desktop Configuration

Add one of the following configurations to `~/Library/Application Support/Claude/claude_desktop_config.json` based on your use case:

#### Scenario 1: HTTP on Local/LAN (Recommended for Local Access)

**Use when:**
- Running Claude Desktop on the same machine as Indigo
- Accessing from your local network
- Security: HTTP is safe on localhost/LAN (traffic never leaves local network)

```json
{
  "mcpServers": {
    "indigo": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "http://localhost:8176/message/com.vtmikel.mcp_server/mcp/",
        "--allow-http",
        "--header",
        "Authorization:Bearer YOUR_LOCAL_SECRET_KEY"
      ]
    }
  }
}
```

**Setup:**
1. Create a local secret in Indigo Web Server Settings
2. Replace `YOUR_LOCAL_SECRET_KEY` with your generated local secret
3. Replace `localhost` with your server IP/hostname for LAN access
4. Port 8176 is the default Indigo Web Server port

#### Scenario 2: HTTPS via Reflector (Remote Access)

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

#### Scenario 3: HTTPS on LAN with Self-Signed Certificate (Advanced)

**Use when:**
- HTTPS is required on local network
- Using Indigo's self-signed SSL certificate
- Note: Less common, most users should use Scenario 1

```json
{
  "mcpServers": {
    "indigo": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://192.168.1.100:8176/message/com.vtmikel.mcp_server/mcp/",
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
1. Create a local secret in Indigo Web Server Settings
2. Replace `192.168.1.100` with your Indigo server IP/hostname
3. Replace `YOUR_LOCAL_SECRET_KEY` with your generated local secret
4. `NODE_TLS_REJECT_UNAUTHORIZED=0` disables certificate validation (required for self-signed certs)

## Available Tools

### Search and Query

- **search_entities**: Natural language search across devices, variables, action groups
- **list_devices**: Get all devices with optional state filtering
- **list_variables**: Get all variables with current values
- **list_action_groups**: Get all action groups/scenes
- **list_variable_folders**: Get all variable folders with IDs
- **get_devices_by_state**: Find devices by state conditions
- **get_devices_by_type**: Get devices by type (dimmer, relay, sensor, etc.)
- **get_device_by_id**: Get specific device by exact ID
- **get_variable_by_id**: Get specific variable by exact ID
- **get_action_group_by_id**: Get specific action group by exact ID

### Control

- **device_turn_on/off**: Control device power state
- **device_set_brightness**: Set dimmer brightness (0-100 or 0-1)
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

- **Authentication Required**: All MCP connections require Bearer token authentication with Indigo API keys
- **Local Access**: HTTP on localhost/LAN is secure (traffic never leaves local network)
- **Remote Access**: Use Indigo Reflector for secure remote access with HTTPS and valid SSL certificates
- **Self-Signed Certificates**: If using HTTPS on LAN, set `NODE_TLS_REJECT_UNAUTHORIZED=0` (see Scenario 3 above)

## Support

- **Issues**: Submit on project repository
- **Questions**: [Indigo Domotics Forum](https://forums.indigodomo.com/viewforum.php?f=274)