# Indigo MCP Server Plugin

A Model Context Protocol (MCP) server plugin that lets AI assistants like Claude search, understand, and
control your [Indigo](https://www.indigodomo.com/) home automation system through natural language.

- "Find all light switches in the bedroom"
- "What devices are currently on?"
- "Turn on the garage lights" / "Execute the bedtime scene"
- "What trigger turned off the porch light last night?"

## Requirements

- **Indigo Domotics** 2025.2 or later (ships Python 3.13)
- **macOS** 10.15 (Catalina) or later
- **Apple Silicon** (M-series) only — LanceDB 0.30+ no longer ships Intel Mac wheels
- **OpenAI API key** for semantic search ([get one](https://platform.openai.com/api-keys)). Only device
  names, types, and descriptions are sent, to generate embeddings (minimal cost) — see
  [Privacy & Security](#privacy--security).
- **Node.js** (for Claude Desktop only, which connects via `npx mcp-remote`): `brew install node`

## Installation

1. Install the **MCP Server** plugin in Indigo via the Plugin Manager.
2. Enter your **OpenAI API key** in the plugin's preferences.
3. Add a new **MCP Server** device in Indigo (this creates the actual server; one per install).
4. Wait for the plugin to **index your database** — the first run takes a while.
5. **Connect an MCP client** — see below.

Optional integrations, all off by default:

- **InfluxDB** — required for the `analyze_historical_data` tool.
- **Event Webhooks** — real-time outbound push notifications; requires a server you run, **not** stock
  Claude Desktop. See [Event Subscriptions & Webhooks](#event-subscriptions--webhooks). *(v2026.1.0)*
- **LangSmith** — AI prompt tracing for debugging; most people don't need it.

## Connecting an MCP Client

### 1. Get an API key

Every connection authenticates with an Indigo API key sent as `Authorization: Bearer <key>`. Two kinds:

- **Reflector API key** — from your Indigo Reflector settings. Use for remote/HTTPS access.
- **Local secret** — for local/LAN access. Add one to
  `/Library/Application Support/Perceptive Automation/Indigo <VERSION>/Preferences/secrets.json`
  ([format](https://wiki.indigodomo.com/doku.php?id=indigo_2024.2_documentation:indigo_web_server#local_secrets)),
  then restart the Indigo Web Server.

### 2. Pick your endpoint URL

The endpoint path is always `/message/com.vtmikel.mcp_server/mcp/`. Choose the base by where you connect
from (default Web Server port is `8176`):

| Access | Endpoint URL | Key |
|--------|--------------|-----|
| Same machine as Indigo | `http://localhost:8176/message/com.vtmikel.mcp_server/mcp/` | Local secret |
| Another machine on your LAN | `http://<indigo-ip>:8176/message/com.vtmikel.mcp_server/mcp/` | Local secret |
| Remote (outside your network) | `https://<your-reflector>.indigodomo.net/message/com.vtmikel.mcp_server/mcp/` | Reflector key |

For HTTPS on the LAN with a self-signed certificate, use the `https://<indigo-host>:8176/...` URL and see
the self-signed note in the client examples below.

### 3. Configure your client

**VS Code, Cursor, Claude Code** support direct HTTP transport — simpler and more reliable. Add to your MCP
settings (`.vscode/mcp.json`, Cursor MCP settings, or `~/.claude.json` / project `.mcp.json`):

```json
{
  "mcpServers": {
    "indigo": {
      "type": "http",
      "url": "http://localhost:8176/message/com.vtmikel.mcp_server/mcp/",
      "headers": { "Authorization": "Bearer YOUR_API_KEY" }
    }
  }
}
```

Swap the `url` for the LAN or Reflector variant from the table above.

**Claude Desktop** does not support direct HTTP, so it proxies through `mcp-remote`. Add to
`~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "indigo": {
      "command": "npx",
      "args": [
        "-y", "mcp-remote",
        "https://your-reflector.indigodomo.net/message/com.vtmikel.mcp_server/mcp/",
        "--header", "Authorization:Bearer YOUR_API_KEY"
      ]
    }
  }
}
```

- **Plain HTTP** (local/LAN): add `"--allow-http"` to `args`.
- **Self-signed HTTPS** (LAN): add `"env": { "NODE_TLS_REJECT_UNAUTHORIZED": "0" }` to the server block.

> **Why the difference?** `mcp-remote` requests OAuth endpoints that Indigo doesn't implement; direct HTTP
> transport avoids that entirely, so prefer it whenever your client supports it.

### HTTP transport notes

The endpoint uses the MCP streamable-HTTP transport over the Indigo Web Server: `POST` carries all
messages, `GET` returns `405` (no server→client SSE stream), and sessions expire after 2 hours idle
(current Indigo Web Server versions reject the `DELETE` teardown before it reaches the plugin).

## What's Possible

What the plugin can and can't do with each kind of Indigo entity, and why. The `✗`'s are Indigo
scripting-API (SDK) limits, not plugin choices.

| Entity | Read | Create | Edit definition | Control / run | Delete |
|--------|------|--------|-----------------|---------------|--------|
| **Devices** | ✓ Full — state, properties, model, type, address | ✗ Created by their protocol plugin / the Indigo UI | ✗ Name, address, and config aren't editable via MCP | ✓ On/off, brightness, RGB/RGBW color, thermostat setpoints & modes | ✗ |
| **Variables** | ✓ Full — value, folder | ✓ `variable_create` (name, value, folder) | ~ **Value** only (`variable_update`); rename/move not exposed | — value *is* the writable state | ✗ |
| **Action groups** | ✓ Full — every action step, incl. embedded scripts & plugin configs (`get_action_group_details`) | ✗ Only an empty shell is possible; no API to add steps → **duplicate** an existing one instead | ~ **Name / description** only; the action steps themselves can't be changed | ✓ Execute, duplicate, move to folder | ✓ *gated* |
| **Triggers** | ✓ Full — event, condition tree, action steps (`get_trigger_details`) | ✗ No API to author actions → **duplicate**, then edit | ~ **Name / description + event settings** (what it watches: device/state/value or variable/value). Conditions ✗, action steps ✗ | ✓ Enable/disable (with timed auto-revert), execute, duplicate, move, remove delayed actions | ✓ *gated* |
| **Schedules** | ✓ Full — timing, next run time, condition tree, action steps (`get_schedule_details`) | ✗ **duplicate**, then edit | ~ **Name / description** only. Timing ✗, conditions ✗, action steps ✗ | ✓ Enable/disable (with timed auto-revert), execute, duplicate, move, remove delayed actions | ✓ *gated* |

**Legend:** ✓ fully supported · ~ partial (see the cell) · ✗ not possible · — not applicable.

- **Why the ✗'s?** Indigo's Python SDK provides no way to author an automation's actions or conditions
  from scratch, edit an existing automation's action steps or conditions, or change a schedule's timing.
  Those stay in the Indigo UI. Everything else is programmatic.
- **"Duplicate, then edit"** is the supported way to make a variant: `control_trigger` /
  `control_schedule` / `control_action_group` with `action: "duplicate"`, then `update_trigger` (or rename
  the copy). The copy carries over the original's actions and conditions intact.
- **Delete is the only gated capability** — it requires the *Allow AI to delete automations* plugin
  preference (off by default) **and** `confirm=true`. Everything else (read, control, edit) is always available.

## Available Tools

Most list and search tools paginate with `limit` (default 50, max 500) and `offset`, and return
`total_count` / `has_more` for navigation.

### Search and query

- **search_entities** — natural-language search across devices, variables, action groups, triggers, and schedules
- **list_devices** — all devices, with optional state filtering
- **list_variables** / **list_variable_folders** — variables (with values) and their folders
- **list_action_groups** — action groups / scenes
- **get_devices_by_state** — devices matching state conditions
- **get_devices_by_type** — devices of a type (dimmer, relay, sensor, …)
- **get_device_by_id** / **get_variable_by_id** / **get_action_group_by_id** — exact lookups

### Automation introspection *(v2026.6.0)*

Inspect triggers, schedules, and action groups in full — including the action steps and condition trees
that Indigo's scripting API does not expose (read from the server's database file, refreshed within
minutes of a change).

- **list_triggers** — triggers with a one-line summary of what each watches; filter by name/type/enabled/folder
- **list_schedules** — schedules with **next execution time** and a timing summary
- **get_trigger_details** / **get_schedule_details** / **get_action_group_details** — the full explanation of
  one automation: its event/timing, condition tree, and every action step (device commands, variable writes,
  nested action groups, embedded Python, plugin actions with config), IDs resolved to names
- **find_automation_references** — reverse lookup: which automations watch, act on, set, or condition-read a
  device/variable/action group — including indirect paths through nested action groups, cross-checked
  against Indigo's own dependency graph

### Investigation *(v2026.6.0)*

- **investigate_event** — "what caused this?" Finds a device's state-change in the log, collects the
  automations that fired around it, and ranks candidate causes by structural evidence (does it actually act
  on that device, directly or through action-group chains?) plus temporal proximity.
- **query_event_log** — read the event log, newest first. With no filters it returns the recent tail from
  Indigo's live log; add `query`/`regex`/`types`/`start_time`/`end_time` to scan the full historical daily
  log files instead. Each entry is `{timestamp, type, message}`.

### Automation control *(v2026.6.0)*

- **control_trigger** / **control_schedule** / **control_action_group** — lifecycle actions: `enable`/`disable`
  (with a `duration_seconds` auto-revert — "disable this trigger for 2 hours"), `execute`, `duplicate`,
  `move_to_folder`, `remove_delayed_actions`, and `delete`. (Action groups support execute/duplicate/move/delete
  only.) **Delete** requires `confirm=true` **and** the *Allow AI to delete automations* preference (off by
  default); every other action is always available.
- **update_trigger** — edit a trigger's name/description and its event settings (watched device/variable,
  comparison, value), returning a before/after diff.
- **update_schedule** / **update_action_group** — edit name/description only.

Action steps, conditions, and schedule timing are read-only in Indigo's scripting API — change those in the
Indigo UI. Since there's no API to author actions from scratch, `duplicate` (via `control_trigger`) followed by
`update_trigger` is the supported way to make a trigger variant.

### Device control

- **device_turn_on** / **device_turn_off** — power state
- **device_set_brightness** — dimmer level (0–100 or 0–1)
- **device_set_rgb_color** / **device_set_rgb_percent** / **device_set_hex_color** / **device_set_named_color**
  (954 XKCD colors + aliases) / **device_set_white_levels** — RGB / RGBW control
- **thermostat_set_heat_setpoint** / **thermostat_set_cool_setpoint** / **thermostat_set_hvac_mode** /
  **thermostat_set_fan_mode** — thermostat control

### Variables, actions, and system

- **variable_create** / **variable_update** — create or update variables
- **action_execute_group** — run an action group / scene
- **list_plugins** / **get_plugin_by_id** / **get_plugin_status** / **restart_plugin** — plugin management
- **analyze_historical_data** — AI analysis of device/variable history (requires InfluxDB)

### Event subscriptions *(v2026.1.0, only when webhooks are enabled)*

- **create_event_subscription** — POST a JSON event to your webhook URL when device/variable conditions match
- **list_event_subscriptions** — active subscriptions with delivery health stats (or one by ID)
- **delete_event_subscription** — delete a subscription (cancels pending dwell timers)

See [Event Subscriptions & Webhooks](#event-subscriptions--webhooks) for the full guide.

## Event Subscriptions & Webhooks

*Added in v2026.1.0.* Event subscriptions let an MCP client ask Indigo to notify it the next time something
happens — "the next time the front door opens", "if the temperature goes above 80°F", "if the garage door
stays open for 10 minutes".

> ### ⚠️ This is an *outbound* webhook — you must run your own server
>
> When a subscription's conditions match, the plugin sends an **HTTP POST** to a URL **you provide**. It is a
> **sender only** — there is no built-in receiver. **This will not work with stock Claude Desktop** or most
> off-the-shelf MCP clients, which have no way to receive a proactive notification. It's meant for custom
> agents / automation systems that own a persistent HTTP endpoint (for example, [OpenClaw](https://openclaw.ai/)).

Enable it under **Plugins → MCP Server → Configure → Enable Event Webhooks** (the three tools are hidden
until then).

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

A webhook fires on the **transition into** a matching state (not repeatedly while it stays matched). Multiple
conditions are combined with **AND**.

```python
# Notify me once, the next time the front door opens
create_event_subscription(
    webhook_url="https://my-server.example.com/indigo-hook",
    entity_type="device", entity_id=12345,
    conditions={"onState": True}, max_fires=1,
    description="Front door opened",
)

# Alert me if the garage door stays open for 10 minutes
create_event_subscription(
    webhook_url="https://my-server.example.com/indigo-hook",
    entity_type="device", entity_id=67890,
    conditions={"onState": True}, duration_seconds=600,
    description="Garage left open",
)
```

### Condition operators

Conditions match against device/variable state keys (including third-party plugin states). Use simple
equality, or an operator object per key:

```jsonc
{ "onState": true }                                    // equality
{ "brightness": { "gt": 50 } }                         // single operator
{ "temperatureInput1": { "gt": 80 }, "onState": true } // AND of multiple keys
```

| Operator | Meaning |
|----------|---------|
| `eq` / `ne` | equal to / not equal to |
| `gt` / `gte` | greater than / greater than or equal |
| `lt` / `lte` | less than / less than or equal |
| `contains` | substring is contained in the value |
| `regex` | value matches the regular expression |

**Variables** match on their `value` key. Indigo stores every value as a **string**, but booleans and
numbers in your conditions are coerced automatically, so `{ "value": true }`, `{ "value": { "eq": "open" } }`,
and `{ "value": { "gt": 50 } }` all work. To fire on *every* change regardless of the new value, use
`{ "any_change": true }` — variables only, and not combinable with `duration_seconds`.

### Authentication

Set via the `auth` parameter; your receiver should validate it so only your Indigo server can post to your
endpoint.

- **`none`** (default) — no auth headers.
- **`bearer`** — adds `Authorization: Bearer <token>`.
- **`hmac`** — adds `X-Webhook-Signature: sha256=<hexdigest>` (`HMAC-SHA256(token, raw_body_bytes)`) and
  `X-Webhook-Timestamp: <unix-seconds>`. Verify on the receiver:

  ```python
  import hmac, hashlib
  expected = "sha256=" + hmac.new(SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
  ok = hmac.compare_digest(expected, request.headers["X-Webhook-Signature"])
  ```

Set `"verify_ssl": false` only if your receiver uses a self-signed certificate.

### The webhook payload

Each delivery is a `POST` with `Content-Type: application/json`, the headers `X-Event-Id`, `X-Event-Type`
(`device.state_changed` | `variable.value_changed`), and `X-Subscription-Id` (plus any auth headers), and a
body like:

```json
{
  "event_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
  "schema_version": "1.0",
  "dedupe_key": "indigo:device:12345:state:onState:True",
  "source": { "system": "indigo", "plugin": "com.vtmikel.mcp_server", "host": "my-indigo-mac" },
  "timestamp": "2026-06-01T15:30:45.123456+00:00",
  "event_type": "device.state_changed",
  "entity": { "kind": "device", "id": 12345, "name": "Front Door", "device_type": "…" },
  "state": { "changed_keys": ["onState"], "old": { "onState": false }, "new": { "onState": true } },
  "trigger": { "subscription_id": "…", "conditions_matched": { "onState": true } },
  "human": { "title": "Front Door state changed", "summary": "Front Door: onState=true" }
}
```

Variable changes use `event_type: "variable.value_changed"`, `entity.kind: "variable"`, and a `state` of
`{ "changed_keys": ["value"], "old": { "value": "…" }, "new": { "value": "…" } }`.

### Delivery behavior

- **At-least-once** — retries mean an event can arrive more than once; your receiver **must deduplicate by
  `event_id`** (or `dedupe_key`).
- **Retries** — up to 4 attempts (1 + 3 retries), 10s timeout each, exponential backoff (~1s/2s/4s), on `5xx`
  and network errors. A `4xx` is a permanent rejection and is not retried. Success is any `2xx` — return
  `200` promptly.
- **Persisted across restarts** — subscriptions are saved (`0600`) to
  `…/Preferences/Plugins/com.vtmikel.mcp_server/subscriptions.json` and reloaded on startup, so they survive
  restarts and upgrades. The file **contains your webhook auth tokens** (required so authenticated webhooks
  can re-authenticate). Pending dwell timers are not persisted — a held condition re-arms on its next
  matching transition.

### Managing subscriptions in a browser *(v2026.3.0)*

When webhooks are enabled, the plugin serves a page that **lists active subscriptions and lets you remove
them** (create/edit stays with the MCP tools; auth tokens are never shown).

![Event Subscriptions web UI](docs/event-subscriptions-web-ui.png)

- **URL:** `http://<your-indigo-host>:8176/message/com.vtmikel.mcp_server/events_ui/` — served by the Indigo
  Web Server under the **same authentication** as the rest of IWS (open it from a browser logged into Indigo).
- **Plugins → MCP Server → Print Event Subscriptions Web UI URL** prints the local/LAN/Reflector URLs to the log.

### Minimal example receiver

Any HTTPS endpoint reachable from your Indigo host works. A dependency-free Python receiver to test with:

```python
from http.server import BaseHTTPRequestHandler, HTTPServer
import json

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        # (Optional) verify X-Webhook-Signature here if using HMAC auth.
        event = json.loads(body)
        # Dedupe by event_id — at-least-once delivery means retries can repeat.
        print(f"{event['event_type']} {event['event_id']}: {event['human']['summary']}")
        self.send_response(200)   # any 2xx = success
        self.end_headers()

HTTPServer(("0.0.0.0", 8888), Handler).serve_forever()
```

## Tips for Better Results

- **Be specific** — include location and device type in queries.
- **Use device Notes** — descriptions in the Notes field are included in the AI's context.
- **State vs. search** — use `list_devices({"onState": true})` for state queries, `search_entities("lights")`
  for discovery.

## Privacy & Security

**Sent to OpenAI** (only to generate search embeddings, stored locally on your Indigo server): device
name/description/model/type/address, variable name/description, and action-group name/description — sent on
install and when entities are added or changed. **Never sent:** device states or values, credentials, URLs,
IP/network configuration, or historical/usage data.

**Network** — every MCP connection requires Bearer-token authentication. Local HTTP stays on your LAN; use the
Indigo Reflector for encrypted remote access. For self-signed HTTPS on the LAN, set
`NODE_TLS_REJECT_UNAUTHORIZED=0` (Claude Desktop) as shown above.

## Support

- **Issues:** the project repository
- **Questions:** [Indigo Domotics Forum](https://forums.indigodomo.com/viewforum.php?f=274)
