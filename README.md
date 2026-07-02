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

## Server Requirements

- **Indigo Domotics**: 2025.2 or later (ships Python 3.13)
- **macOS**: 10.15 (Catalina) or later
- **CPU**: Apple Silicon only (M1/M2/M3/M4)
    - LanceDB 0.30+ no longer ships Intel Mac (x86) wheels
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
- **Event Webhooks**: Optional real-time push notifications, delivered as an HTTP POST to an
  endpoint **you run** (disabled by default; requires a custom agent/automation system, **not**
  stock Claude Desktop — see [Event Subscriptions & Webhooks](#event-subscriptions--webhooks)).
  *Added in v2026.1.0.*

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

### HTTP Transport Behavior

The endpoint implements the MCP streamable-HTTP transport over the Indigo Web Server:

- `POST` carries all MCP messages.
- `GET` returns `405` — the server does not offer a server→client SSE stream (spec-permitted).
- `DELETE` with an `Mcp-Session-Id` header terminates that session. Note: current Indigo Web Server versions reject `DELETE` before it reaches the plugin, so sessions are also expired automatically after 2 hours idle.

### Claude Desktop / MCP Client Configuration

Requirements:
- **Node.js**: Required for MCP client connection ([Download](https://nodejs.org/))
    - Provides `npx` command used by Claude Desktop configuration
    - Install via Homebrew: `brew install node`
    - Or download from [nodejs.org](https://nodejs.org/)

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

> **Note**: For VS Code, Cursor, or Claude Code CLI, see the "VS Code / Cursor / Claude Code Configuration" section below for direct HTTP configuration.

### VS Code / Cursor / Claude Code Configuration

These clients support **direct HTTP transport** which is simpler and more reliable than the `mcp-remote` proxy.

#### Scenario 1: Local Access (Same Machine as Indigo)

Add to your MCP settings file:
- **VS Code**: `.vscode/mcp.json` or VS Code settings
- **Cursor**: Cursor MCP settings
- **Claude Code**: `~/.claude.json` or project `.mcp.json`

```json
{
  "mcpServers": {
    "indigo": {
      "type": "http",
      "url": "http://localhost:8176/message/com.vtmikel.mcp_server/mcp/",
      "headers": {
        "Authorization": "Bearer YOUR_LOCAL_SECRET_KEY"
      }
    }
  }
}
```

#### Scenario 2: LAN Access (Different Machine on Same Network)

```json
{
  "mcpServers": {
    "indigo": {
      "type": "http",
      "url": "http://YOUR_INDIGO_IP:8176/message/com.vtmikel.mcp_server/mcp/",
      "headers": {
        "Authorization": "Bearer YOUR_LOCAL_SECRET_KEY"
      }
    }
  }
}
```

Replace `YOUR_INDIGO_IP` with your Indigo server's LAN IP address (e.g., `192.168.1.100`).

#### Scenario 3: Remote HTTPS via Indigo Reflector

```json
{
  "mcpServers": {
    "indigo": {
      "type": "http",
      "url": "https://your-reflector-id.indigodomo.net/message/com.vtmikel.mcp_server/mcp/",
      "headers": {
        "Authorization": "Bearer YOUR_REFLECTOR_API_KEY"
      }
    }
  }
}
```

> **Why direct HTTP?** The `mcp-remote` proxy used by Claude Desktop requests OAuth endpoints that Indigo doesn't implement. Direct HTTP transport avoids this issue entirely.

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

**Tools with Pagination:** `search_entities`, `list_devices`, `list_variables`, `list_action_groups`, `get_devices_by_state`, `list_triggers`, `list_schedules`

## Available Tools

### Search and Query

- **search_entities**: Natural language search across devices, variables, action groups, triggers, and schedules (pagination supported)
- **list_devices**: Get all devices with optional state filtering (pagination supported)
- **list_variables**: Get all variables with current values (pagination supported)
- **list_action_groups**: Get all action groups/scenes (pagination supported)
- **list_variable_folders**: Get all variable folders with IDs
- **get_devices_by_state**: Find devices by state conditions (pagination supported)
- **get_devices_by_type**: Get devices by type (dimmer, relay, sensor, etc.)
- **get_device_by_id**: Get specific device by exact ID
- **get_variable_by_id**: Get specific variable by exact ID
- **get_action_group_by_id**: Get specific action group by exact ID

### Automation Introspection

*Added in v2026.6.0.* Triggers, schedules, and action groups can now be inspected in
full — including the action steps and condition trees that Indigo's scripting API
does not expose (read from the server's database file, refreshed within minutes of
changes).

- **list_triggers**: List triggers with a one-line summary of what each watches; filter by name/type/enabled/folder (pagination supported)
- **list_schedules**: List schedules including **next execution time** and a timing summary (pagination supported)
- **get_automation_details**: Explain a trigger, schedule, or action group — its event/timing, condition tree, and every action step (device commands, variable writes, nested action groups, embedded Python scripts, plugin actions with configuration), with entity IDs resolved to names
- **find_automation_references**: Reverse lookup — which triggers/schedules/action groups watch, act on, set, or condition-read a device, variable, or action group, including indirect paths through nested action groups, cross-checked against the Indigo server's own dependency graph

### Investigation

*Added in v2026.6.0.*

- **search_event_log**: Search the historical daily event-log files with text/regex matching, type filters (`Trigger`, `Schedule`, `Action Group`, `Z-Wave`, ...), time ranges, and pagination
- **investigate_event**: "What caused this?" — finds a device's state-change line in the log, collects the automations that fired around it, and ranks candidate causes by structural evidence (does it actually act on that device, directly or through action-group chains?) plus temporal proximity

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

### Event Subscriptions

> Available only when **Enable Event Webhooks** is turned on in plugin preferences, and require you
> to run your own webhook receiver. *Added in v2026.1.0.* See
> [Event Subscriptions & Webhooks](#event-subscriptions--webhooks) for the full guide.

- **create_event_subscription**: Subscribe to device/variable state changes; POST a JSON event to your webhook URL when conditions match
- **list_event_subscriptions**: List active subscriptions with delivery health stats (or fetch one by ID)
- **delete_event_subscription**: Delete a subscription by ID (cancels pending dwell timers)

## Event Subscriptions & Webhooks

*Added in v2026.1.0.*

Event subscriptions let an MCP client ask Indigo to notify it the next time something happens —
"tell me the next time the front door opens", "alert me if the temperature goes above 80°F", "notify
me if the garage door stays open for 10 minutes".

> ### ⚠️ This is an *outbound* webhook — you must run your own server
>
> When a subscription's conditions match, the plugin sends an **HTTP POST** to a URL **you provide**.
> The plugin is a **sender only** — there is **no built-in receiver**. You must run your own
> always-on HTTP server with a reachable endpoint that accepts that POST and does something with it.
>
> **This will not work with stock Claude Desktop** (or most off-the-shelf MCP clients). Those clients
> have no way to receive a proactive, server-initiated notification — enabling webhooks and
> restarting Claude Desktop does nothing visible. Event subscriptions are intended for **custom
> agents / automation systems that own a persistent HTTP endpoint** (for example,
> [OpenClaw](https://openclaw.ai/)). If you don't have a server that can receive a POST, this feature
> is not for you yet.

### Enabling webhooks

The feature is **disabled by default**. In the plugin's preferences (Plugins → MCP Server → Configure),
check **Enable Event Webhooks**. The three event-subscription tools
(`create_event_subscription`, `list_event_subscriptions`, `delete_event_subscription`) are hidden
from MCP clients until this is turned on.

### Creating a subscription

`create_event_subscription` accepts:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `webhook_url` | string | **yes** | HTTP(S) endpoint **you run** that events are POSTed to. |
| `entity_type` | `"device"` \| `"variable"` | **yes** | What kind of entity to watch. |
| `conditions` | object | **yes** | State conditions that trigger the webhook (see operators below). |
| `entity_id` | integer | no | A specific device/variable ID, or omit to watch **all** entities of that type. |
| `auth` | object | no | `{ "mode": "none"\|"bearer"\|"hmac", "token": "…", "verify_ssl": true }` (see Authentication). |
| `duration_seconds` | integer (≥1) | no | **Dwell time** — the condition must stay matched this long before firing. If it reverts first, nothing is sent. |
| `max_fires` | integer (≥1) | no | Auto-delete the subscription after this many successful deliveries. Use `1` for a one-shot notification. Omit for unlimited. |
| `description` | string | no | Human-readable label for the subscription. |

A webhook fires on the **transition into** a matching state (not repeatedly while it stays matched).
When multiple conditions are given, they are combined with **AND** — all must match.

```python
# Notify me once, the next time the front door opens
create_event_subscription(
    webhook_url="https://my-server.example.com/indigo-hook",
    entity_type="device",
    entity_id=12345,
    conditions={"onState": True},
    max_fires=1,
    description="Front door opened",
)

# Alert me if the garage door stays open for 10 minutes
create_event_subscription(
    webhook_url="https://my-server.example.com/indigo-hook",
    entity_type="device",
    entity_id=67890,
    conditions={"onState": True},
    duration_seconds=600,
    description="Garage left open",
)
```

### Condition operators

Conditions are matched against device/variable state keys (including third-party plugin states).
Use simple equality, or an operator object per key:

```jsonc
{ "onState": true }                                  // equality
{ "brightness": { "gt": 50 } }                       // single operator
{ "temperatureInput1": { "gt": 80 }, "onState": true } // AND of multiple keys
```

| Operator | Meaning |
|----------|---------|
| `eq` | equal to |
| `ne` | not equal to |
| `gt` / `gte` | greater than / greater than or equal |
| `lt` / `lte` | less than / less than or equal |
| `contains` | substring is contained in the value |
| `regex` | value matches the regular expression |

**Watching variables.** Match a variable on its `value` key. Indigo stores every variable value as a
**string**, but booleans and numbers in your conditions are coerced automatically, so all of these work:

```jsonc
{ "value": true }            // matches the string "true"
{ "value": { "eq": "open" } } // exact string match
{ "value": { "gt": 50 } }     // numeric comparison against the string value
```

**Any change (variables only).** To fire on *every* change to a variable's value regardless of what it
becomes, use the `any_change` sentinel. It is **only valid for variables** (devices update far too
often), and cannot be combined with `duration_seconds`:

```python
create_event_subscription(
    webhook_url="https://my-server.example.com/indigo-hook",
    entity_type="variable",
    entity_id=88,
    conditions={"any_change": True},
    description="House mode changed",
)
```

### Authentication

Set via the `auth` parameter. The receiver should validate this so that only your Indigo server can
post to your endpoint.

- **`none`** (default) — no auth headers added.
- **`bearer`** — adds `Authorization: Bearer <token>` to each POST.
- **`hmac`** — adds an HMAC-SHA256 signature over the **raw request body**:
  - `X-Webhook-Signature: sha256=<hexdigest>`
  - `X-Webhook-Timestamp: <unix-seconds>`

  The signature is computed as `HMAC-SHA256(token, raw_body_bytes)`. Verify it on the receiver:

  ```python
  import hmac, hashlib
  expected = "sha256=" + hmac.new(SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
  ok = hmac.compare_digest(expected, request.headers["X-Webhook-Signature"])
  ```

Set `"verify_ssl": false` only if your receiver uses a self-signed certificate.

### The webhook payload

Each delivery is a `POST` with `Content-Type: application/json` and these headers:

```
X-Event-Id: <event id>          # same value as the body's event_id
X-Event-Type: <event type>      # device.state_changed | variable.value_changed
X-Subscription-Id: <subscription id>
```

…plus the auth headers above when configured. The JSON body looks like this:

```json
{
  "event_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
  "schema_version": "1.0",
  "dedupe_key": "indigo:device:12345:state:onState:True",
  "source": { "system": "indigo", "plugin": "com.vtmikel.mcp_server", "host": "my-indigo-mac" },
  "timestamp": "2026-06-01T15:30:45.123456+00:00",
  "event_type": "device.state_changed",
  "entity": { "kind": "device", "id": 12345, "name": "Front Door", "device_type": "…" },
  "state": {
    "changed_keys": ["onState"],
    "old": { "onState": false },
    "new": { "onState": true }
  },
  "trigger": { "subscription_id": "…", "conditions_matched": { "onState": true } },
  "human": { "title": "Front Door state changed", "summary": "Front Door: onState=true" }
}
```

Variable changes use `event_type: "variable.value_changed"`, `entity.kind: "variable"`, and a
`state` of `{ "changed_keys": ["value"], "old": { "value": "…" }, "new": { "value": "…" } }`.

### Delivery behavior

- **At-least-once delivery.** Retries mean the same event can arrive more than once — your receiver
  **must deduplicate by `event_id`** (or `dedupe_key`).
- **Retries:** up to **4 delivery attempts** (1 initial + 3 retries), 10-second timeout each, with
  exponential backoff (~1s, 2s, 4s between attempts). Retries happen on `5xx` and network/connection
  errors. A `4xx` response is treated as a permanent rejection and is **not** retried.
- **Success** is any `2xx` response — have your endpoint return `200` promptly.
- **Persisted across restarts:** subscriptions are saved to
  `…/Preferences/Plugins/com.vtmikel.mcp_server/subscriptions.json` and reloaded on startup, so they
  survive plugin/Indigo restarts and upgrades. The file is written `0600` and **contains your webhook
  auth tokens** (it must, so authenticated webhooks can re-authenticate after a restart) — it lives in
  Indigo's protected app-support directory. Delivery stats are saved on each change and on shutdown
  (best-effort after an unclean crash). Pending **dwell timers are not persisted** — a held condition
  re-arms on its next matching transition.

### Managing subscriptions in a browser (Web UI)

*Added in v2026.3.0.* When event webhooks are enabled, the plugin serves a small web page that **lists
every active subscription with full detail and lets you remove individual ones** (it does not create or
edit — that stays with the MCP tools). API keys / bearer tokens are never shown.

![Event Subscriptions web UI](docs/event-subscriptions-web-ui.png)

- **URL:** `http://<your-indigo-host>:8176/message/com.vtmikel.mcp_server/events_ui/`
- It is served by the Indigo Web Server and uses the **same authentication** as the rest of IWS — open it
  from a browser that is logged into Indigo (no separate login).
- The plugin menu **Plugins → MCP Server → Print Event Subscriptions Web UI URL** prints the exact URLs
  for local, LAN, and Reflector access to the Indigo log.
- The page reflects the current process only — subscriptions are in-memory and disappear on a plugin restart.

### Minimal example receiver

Any HTTPS endpoint reachable from your Indigo host works — a small Flask app, a serverless function,
an automation platform's inbound webhook, etc. Here's a dependency-free Python receiver to test with:

```python
from http.server import BaseHTTPRequestHandler, HTTPServer
import json

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        # (Optional) verify X-Webhook-Signature here if using HMAC auth.
        event = json.loads(body)
        # Dedupe by event_id — at-least-once delivery means retries can repeat.
        print(f"{event['event_type']} {event['event_id']}: {event['human']['summary']}")
        self.send_response(200)   # any 2xx = success
        self.end_headers()

HTTPServer(("0.0.0.0", 8888), Handler).serve_forever()
```

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
