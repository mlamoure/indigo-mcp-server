# MCP Provider Manifest — contributing tools from your Indigo plugin

Any Indigo plugin can contribute tools to the Indigo MCP Server (v2026.8.1+),
making its functionality available to AI assistants as first-class, typed MCP
tools. A provider needs three things: a **manifest file**, a **hidden action**,
and (recommended) a **startup broadcast**. No MCP protocol knowledge is
required — the MCP Server handles discovery, tool listing, and dispatch.

Reference implementation: the [Auto Lights plugin](https://github.com/mlamoure/indigo-auto-lights)
(`com.vtmikel.autolights`), which contributes 15 config-authoring tools.

## No MCP Server? No problem

**A provider plugin must work perfectly for users who do not have the MCP
Server plugin installed** — and does, when built as described here:

1. The manifest is inert data. Nothing reads it unless the MCP Server is
   installed and scans for it.
2. The hidden action is only ever called by the MCP Server. Import your
   tool-handler modules **lazily inside the action callback**, never at plugin
   import/startup time — then a bug in tool code can never break normal plugin
   startup.
3. The startup broadcast is a harmless no-op when nobody subscribes; wrap it in
   try/except anyway so it can never affect startup.

Net: zero hard dependency, zero errors, zero behavior change for users without
the MCP Server.

## 1. The manifest file

Ship `Contents/Resources/mcp-manifest.json` in your plugin bundle:

```json
{
  "manifest_version": 1,
  "provider": {
    "plugin_id": "com.example.myplugin",
    "display_name": "My Plugin"
  },
  "tool_prefix": "myplugin",
  "invoke_action_id": "mcp_tool_invoke",
  "tools": [
    {
      "name": "get_status",
      "description": "Return the plugin's current status.",
      "write": false,
      "timeout_seconds": 15,
      "inputSchema": {"type": "object", "properties": {}, "required": []}
    },
    {
      "name": "set_mode",
      "description": "Change the operating mode.",
      "write": true,
      "timeout_seconds": 30,
      "inputSchema": {
        "type": "object",
        "properties": {
          "mode": {"type": "string", "enum": ["auto", "manual"]}
        },
        "required": ["mode"]
      }
    }
  ]
}
```

### Field reference

| Field | Required | Rules |
|---|---|---|
| `manifest_version` | yes | Must be `1`. Manifests with any other version are skipped with a warning. |
| `provider.plugin_id` | yes | Must equal your bundle's `CFBundleIdentifier`. A mismatch rejects the whole manifest (spoof guard). |
| `provider.display_name` | no | Shown in logs and appended to tool descriptions. Defaults to the plugin id. |
| `tool_prefix` | no | Optional override, `^[a-z][a-z0-9_]{0,31}$`. Defaults to the last dot-segment of your plugin id, snake-cased. |
| `invoke_action_id` | no | The hidden action the MCP Server calls. Default `mcp_tool_invoke`. Per-tool `action_id` overrides are allowed. |
| `tools[].name` | yes | `^[a-z][a-z0-9_]{0,40}$`, unique within the manifest. |
| `tools[].description` | yes | Shown to AI clients. Describe behavior, side effects, and argument semantics — the AI relies on this. |
| `tools[].inputSchema` | yes | A real JSON Schema object with `"type": "object"`; served to MCP clients verbatim. Good schemas (types, enums, descriptions, `required`) are what let the AI call your tool correctly and self-correct. |
| `tools[].write` | no | Whether the tool changes state. **Defaults to `true`** (fail safe): write tools are refused when the user unchecks "Allow plugin-provided tools to make changes" in the MCP Server config. |
| `tools[].timeout_seconds` | no | Dispatch deadline, clamped to 5–120. Default 30. |

### Tool naming — enforced prefixes

Every exposed tool name is **always** `{prefix}_{name}` (e.g.
`myplugin_get_status`). There is no opt-out: the prefix is computed and
enforced by the MCP Server, never trusted from the manifest. Prefixes are
claimed **first-come across providers**: if a second plugin declares a prefix
another plugin already holds, its whole manifest is rejected with an ERROR
naming both plugin ids. Names that would collide with a built-in MCP Server
tool are skipped.

## 2. The invoke action

Declare a hidden action in `Actions.xml`:

```xml
<Action id="mcp_tool_invoke" uiPath="hidden">
    <Name>MCP Tool Invocation Endpoint</Name>
    <CallbackMethod>handle_mcp_tool_invoke</CallbackMethod>
</Action>
```

The MCP Server calls it via
`plugin.executeAction("mcp_tool_invoke", props={"tool": <bare name>, "arguments": <JSON string>}, waitUntilDone=True)`.

Your handler receives the bare tool name (no prefix) and the arguments as a
**JSON string** (never an `indigo.Dict` — indigo.Dict cannot carry `null`
values or `$`-prefixed keys), and must return a **JSON string** envelope:

```python
def handle_mcp_tool_invoke(self, action, dev=None, caller_waiting_for_result=True):
    import json
    try:
        from my_tools import dispatch  # lazy import — see "No MCP Server? No problem"
        tool = action.props.get("tool", "")
        arguments = json.loads(action.props.get("arguments", "{}"))
        return dispatch(tool, arguments)  # returns the JSON-string envelope
    except Exception as e:
        return json.dumps({"status": "error",
                           "error": {"type": "internal", "message": str(e)}})
```

### Reply envelope

Success:

```json
{"status": "ok", "result": {"anything": "JSON-serializable"}}
```

Failure — **in-band, never as a raised exception** (exceptions are reserved for
infrastructure breakage and reach the AI as an opaque error):

```json
{"status": "error",
 "error": {"type": "validation", "message": "mode must be one of auto|manual",
           "details": {"errors": [{"path": "mode", "message": "..."}]}}}
```

`error.type` is one of `validation` (bad input — include enough detail for the
AI to fix its call), `not_found`, `conflict` (state changed underneath the
caller), or `internal`.

## 3. The startup broadcast (recommended)

```python
def startup(self):
    ...
    try:
        indigo.server.broadcastToSubscribers("mcp_tools_updated")
    except Exception:
        pass
```

The MCP Server subscribes to this key and re-reads your manifest on receipt, so
your tools register (or refresh after an update) the moment your plugin starts —
no MCP Server restart needed. Also broadcast it any time your effective tool
set changes at runtime. Without the broadcast, tools are still picked up at MCP
Server startup or via its "Rescan Plugin-Provided MCP Tools" menu item.

## Conduct rules

- **Be quick.** Your handler runs on your plugin's single callback thread,
  serialized with all your other callbacks — a slow handler freezes your own
  plugin's UI interactions. Stay well under your declared `timeout_seconds`;
  for anything slow (hardware, network), acquire
  `indigo.acquireCallbackCompleteHandler()` and finish on a worker thread.
- **Never call back into the MCP Server synchronously.** A tool handler must
  not `executeAction` into `com.vtmikel.mcp_server` with `waitUntilDone=True`:
  the MCP Server may be blocked waiting on *you*, `executeAction` has no
  timeout, and the resulting mutual deadlock does not self-heal.
- **Validate your inputs.** Calls do not pass through your ConfigUI validation.
  Validate every argument in the handler and return `validation` errors with
  precise messages — that is what lets the AI correct itself.
- **Timeouts are real.** If your handler exceeds its `timeout_seconds`, the MCP
  Server abandons the call (your handler keeps running to completion) and
  reports a timeout to the AI.
