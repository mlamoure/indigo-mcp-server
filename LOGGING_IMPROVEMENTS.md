# MCP Server Logging Improvements

Based on production event log analysis (2025-11-10), here are recommendations to make logging more informative and readable.

## Current Issues

### 1. Too Verbose - Protocol Noise
Current event log shows many low-value protocol messages:
```
📨 tools:list | session: jkIeCKfk
📨 initialize | session: none
📨 prompts:list | session: jkIeCKfk
📨 resources:list | session: jkIeCKfk
📨 notify:initialized | session: aFYmU0OS
```

**Problem**: These add noise without providing actionable information.

### 2. Debug Messages Leaking to INFO
Examples from the log:
```
🔍 Expanding with AI
OpenAI completion: gpt-5-mini
Tokens: 119 (limit: 400,000)
Query expanded: 'light switches' -> 'light switches switch control controller'
Generated embedding (1536 dimensions)
Deduplication removed 2707 duplicate entities (3000 -> 293)
```

**Problem**: Search internals should be DEBUG level, not INFO.

### 3. Redundant Success Messages
```
[search_entities]: Found 10 devices, 0 variables, 0 actions (showing 5)
📨 tools:call | session: jkIeCKfk
[get_devices_by_type]: 💡 Found 60 'dimmer' devices (returning 5 from offset 0)
📨 tools:call | session: jkIeCKfk
[list_handlers]: 💡 list_devices completed successfully - 10 items
```

**Problem**: Multiple log lines for single operations, makes it hard to scan.

### 4. Plugin Scanner Noise
```
Found 31 enabled plugins in /Library/Application Support/Perceptive Automation...
Total plugins scanned: 42
Found 11 disabled plugins in /Library/Application Support/Perceptive Automation...
Using cached plugin list (age: 0.8s)
```

**Problem**: Too much detail about caching behavior.

---

## Recommended Changes

### Priority 1: Reduce Protocol Logging

**Change `mcp_handler.py:292`**: Make protocol messages DEBUG level except for significant events

```python
# BEFORE (line 292)
self.logger.info(f"📨 {log_method} | session: {session_short}")

# AFTER
# Only log significant MCP operations at INFO, move protocol to DEBUG
significant_methods = ["tools/call", "resources/read"]
if any(method.startswith(sm) for sm in significant_methods):
    self.logger.info(f"📨 {log_method} | session: {session_short}")
else:
    self.logger.debug(f"📨 {log_method} | session: {session_short}")
```

**Benefit**: Reduces log noise by ~60%, keeps only actionable events.

---

### Priority 2: Consolidate Tool Execution Logging

**Change handler INFO logs**: Use a single consolidated INFO message per tool execution

**Example - in `search_entities/main.py`**:
```python
# BEFORE: Multiple INFO logs throughout execution
self.info_log("🔍 Expanding with AI")
self.info_log(f"Query expanded: '{query}' -> '{expanded}'")
self.info_log(f"Deduplication removed {removed} duplicate entities")
self.info_log(f"Found {len(devices)} devices, {len(variables)} variables...")

# AFTER: Single summary INFO log, move details to DEBUG
self.debug_log(f"Query expansion: '{query}' -> '{expanded}'")
self.debug_log(f"Deduplication: {removed} entries removed")
self.info_log(f"🔍 Search '{query}': {len(devices)} devices, {len(variables)} variables, {len(actions)} actions (showed {len(results['devices'])})")
```

**Benefit**: One line per search operation instead of 6+.

---

### Priority 3: Move Search Internals to DEBUG

**Change `search_entities/query_parser.py` and `main.py`**:

All OpenAI/embedding details should be DEBUG:
- Token counts
- Model names
- Embedding dimensions
- Query expansion details
- Deduplication stats

**Keep at INFO only**:
- Final search results summary
- Errors and warnings

---

### Priority 4: Improve Tool Call Summaries

**Change format for tool execution** - Make it more scannable:

```python
# BEFORE
[list_handlers]: 💡 list_devices completed successfully - 10 items
[get_devices_by_type]: 💡 Found 60 'dimmer' devices (returning 5 from offset 0)

# AFTER
✅ list_devices: 10/982 devices (offset=0)
✅ get_devices_by_type(dimmer): 5/60 devices (offset=0)
✅ search_entities("light"): 5 devices found
✅ device_turn_on(Living Room Lamp): success → on
❌ device_turn_on(Invalid Device): device not found
```

**Format**: `[✅/❌] tool_name(key_params): result_summary`

**Benefits**:
- Consistent format across all tools
- Key parameters visible
- Clear success/failure indicator
- Scannable at a glance

---

### Priority 5: Reduce Plugin Scanner Verbosity

**Change `plugin_control/plugin_scanner.py`**:

```python
# BEFORE (INFO level)
self.logger.info(f"Found {len(enabled)} enabled plugins in {plugins_path}")
self.logger.info(f"Total plugins scanned: {total_count}")
self.logger.info(f"Found {len(disabled)} disabled plugins...")
self.logger.debug(f"Using cached plugin list (age: {age:.1f}s)")

# AFTER (consolidate and reduce)
self.logger.debug(f"Plugin scan: {len(enabled)} enabled, {len(disabled)} disabled (cached: {age:.1f}s)")
# Only log at INFO when cache is refreshed:
self.logger.info(f"Plugin cache refreshed: {len(enabled)} enabled plugins found")
```

---

### Priority 6: Add Contextual Information

**Improve error and warning messages** with more context:

```python
# BEFORE
self.logger.error("❌ Device not found")

# AFTER
self.logger.error(f"❌ device_turn_on failed: device_id={device_id} not found")

# BEFORE
self.logger.warning("⚠️ OpenAI API rate limit")

# AFTER
self.logger.warning(f"⚠️ OpenAI API rate limit (retrying in {retry_seconds}s)")
```

---

## Proposed Event Log Output

### Before (Current - 15 lines for one search):
```
📨 tools:list | session: jkIeCKfk
📨 initialize | session: none
📨 prompts:list | session: jkIeCKfk
📨 tools:call | session: jkIeCKfk
[search_entities]: query: 'light switches', device_types: None, entity_types: []
[search_entities]: Searching: 'light switches'
🔍 Expanding with AI
MCP Server Debug    OpenAI completion: gpt-5-mini
MCP Server Debug    Tokens: 119 (limit: 400,000)
MCP Server Debug    Query expanded: 'light switches' -> 'light switches switch control controller'
MCP Server Debug    Generated embedding (1536 dimensions)
MCP Server Debug    Deduplication removed 2707 duplicate entities (3000 -> 293)
[search_entities]: Found 10 devices, 0 variables, 0 actions (showing 5)
📨 tools:call | session: jkIeCKfk
```

### After (Proposed - 2 lines for one search):
```
📨 tools:call | session: jkIeCKfk
✅ search_entities("light switches"): 5/10 devices, 0 variables, 0 actions
```

**Reduction**: 87% fewer log lines while maintaining all critical information.

---

## Implementation Priority

1. **Phase 1 (High Impact, Low Effort)**:
   - Move protocol messages to DEBUG (except tools/call, resources/read)
   - Consolidate tool success messages to single line
   - Move search internals to DEBUG

2. **Phase 2 (Medium Impact, Medium Effort)**:
   - Standardize tool logging format across all handlers
   - Add contextual error information
   - Reduce plugin scanner verbosity

3. **Phase 3 (Nice to Have)**:
   - Add optional "verbose mode" flag for troubleshooting
   - Session lifecycle summary (client connected/disconnected)
   - Performance metrics (tool execution times)

---

## Configuration Options

Consider adding a plugin preference for log verbosity:

```python
# PluginConfig.xml addition
<Field id="log_verbosity" type="menu" defaultValue="normal">
    <Label>Log Verbosity:</Label>
    <List>
        <Option value="quiet">Quiet (errors only)</Option>
        <Option value="normal">Normal (recommended)</Option>
        <Option value="verbose">Verbose (all details)</Option>
    </List>
</Field>
```

This allows users to choose between:
- **Quiet**: Only errors and warnings
- **Normal**: Tool executions and important events (recommended)
- **Verbose**: Current behavior with all details

---

## Testing Recommendations

After implementing changes:

1. **Test normal operations**: Verify INFO log is scannable and informative
2. **Test with DEBUG enabled**: Ensure all details are still available
3. **Test error scenarios**: Verify error messages have sufficient context
4. **Compare before/after**: Count log lines for same operations

Expected results:
- 70-80% reduction in INFO log lines
- Same or better information density
- All details preserved in DEBUG level
- Easier to spot issues at a glance
