"""
Tool registry for MCP server.

Defines all available tool schemas for the MCP server.
Each tool includes a description, input schema, and reference to its implementation function.
"""

# Tools that change state. Their activity is always logged at INFO;
# everything else is read-only and logs at DEBUG unless the user enables
# the "Log AI read activity" preference (see common/log_style.py).
WRITE_TOOLS = frozenset({
    "device_turn_on",
    "device_turn_off",
    "device_set_brightness",
    "device_set_rgb_color",
    "device_set_rgb_percent",
    "device_set_hex_color",
    "device_set_named_color",
    "device_set_white_levels",
    "thermostat_set_heat_setpoint",
    "thermostat_set_cool_setpoint",
    "thermostat_set_hvac_mode",
    "thermostat_set_fan_mode",
    "variable_update",
    "variable_create",
    "action_execute_group",
    "restart_plugin",
    "create_event_subscription",
    "delete_event_subscription",
    "automation_control",
    "update_automation",
})


def get_tool_schemas(tool_functions):
    """
    Get all tool schemas with their corresponding implementation functions.

    Args:
        tool_functions: Dictionary mapping tool names to their implementation functions

    Returns:
        Dictionary of tool schemas ready for MCP registration
    """
    tools = {}

    # Search entities tool
    tools["search_entities"] = {
        "description": "Search for Indigo entities using natural language with pagination support",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query"
                },
                "device_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional device types to filter. Valid types: dimmer, relay, sensor, multiio, speedcontrol, sprinkler, thermostat, device. Common aliases supported: light→dimmer, switch→relay, motion→sensor, fan→speedcontrol, etc."
                },
                "entity_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional entity types to search: device, variable, action, trigger, schedule (default: all)"
                },
                "state_filter": {
                    "type": "object",
                    "description": "Optional state conditions to filter results"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 50)",
                    "default": 50,
                    "minimum": 1,
                    "maximum": 500
                },
                "offset": {
                    "type": "integer",
                    "description": "Number of results to skip (default: 0)",
                    "default": 0,
                    "minimum": 0
                }
            },
            "required": ["query"]
        },
        "function": tool_functions["search_entities"]
    }

    # Get devices by type
    tools["get_devices_by_type"] = {
        "description": "Get devices of a specific type with pagination support",
        "inputSchema": {
            "type": "object",
            "properties": {
                "device_type": {
                    "type": "string",
                    "description": "Device type. Valid types: dimmer, relay, sensor, multiio, speedcontrol, sprinkler, thermostat, device. Aliases supported: light→dimmer, switch→relay, motion→sensor, fan→speedcontrol, etc."
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of devices to return (default: 50)",
                    "default": 50,
                    "minimum": 1,
                    "maximum": 500
                },
                "offset": {
                    "type": "integer",
                    "description": "Number of devices to skip (default: 0)",
                    "default": 0,
                    "minimum": 0
                }
            },
            "required": ["device_type"]
        },
        "function": tool_functions["get_devices_by_type"]
    }

    # Device control tools
    tools["device_turn_on"] = {
        "description": "Turn on a device",
        "inputSchema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "integer",
                    "description": "The ID of the device to turn on"
                }
            },
            "required": ["device_id"]
        },
        "function": tool_functions["device_turn_on"]
    }

    tools["device_turn_off"] = {
        "description": "Turn off a device",
        "inputSchema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "integer",
                    "description": "The ID of the device to turn off"
                }
            },
            "required": ["device_id"]
        },
        "function": tool_functions["device_turn_off"]
    }

    tools["device_set_brightness"] = {
        "description": "Set device brightness level",
        "inputSchema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "integer",
                    "description": "The ID of the device"
                },
                "brightness": {
                    "type": "number",
                    "description": "Brightness level (0-1 or 0-100)"
                }
            },
            "required": ["device_id", "brightness"]
        },
        "function": tool_functions["device_set_brightness"]
    }

    # RGB device control
    tools["device_set_rgb_color"] = {
        "description": "Set RGB color using 0-255 values",
        "inputSchema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "integer",
                    "description": "The ID of the RGB device"
                },
                "red": {
                    "type": "integer",
                    "description": "Red value (0-255)",
                    "minimum": 0,
                    "maximum": 255
                },
                "green": {
                    "type": "integer",
                    "description": "Green value (0-255)",
                    "minimum": 0,
                    "maximum": 255
                },
                "blue": {
                    "type": "integer",
                    "description": "Blue value (0-255)",
                    "minimum": 0,
                    "maximum": 255
                },
                "delay": {
                    "type": "integer",
                    "description": "Optional delay in seconds (default: 0)",
                    "minimum": 0
                }
            },
            "required": ["device_id", "red", "green", "blue"]
        },
        "function": tool_functions["device_set_rgb_color"]
    }

    tools["device_set_rgb_percent"] = {
        "description": "Set RGB color using 0-100 percentage values",
        "inputSchema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "integer",
                    "description": "The ID of the RGB device"
                },
                "red_percent": {
                    "type": "number",
                    "description": "Red percentage (0-100)",
                    "minimum": 0,
                    "maximum": 100
                },
                "green_percent": {
                    "type": "number",
                    "description": "Green percentage (0-100)",
                    "minimum": 0,
                    "maximum": 100
                },
                "blue_percent": {
                    "type": "number",
                    "description": "Blue percentage (0-100)",
                    "minimum": 0,
                    "maximum": 100
                },
                "delay": {
                    "type": "integer",
                    "description": "Optional delay in seconds (default: 0)",
                    "minimum": 0
                }
            },
            "required": ["device_id", "red_percent", "green_percent", "blue_percent"]
        },
        "function": tool_functions["device_set_rgb_percent"]
    }

    tools["device_set_hex_color"] = {
        "description": "Set RGB color using hex color code",
        "inputSchema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "integer",
                    "description": "The ID of the RGB device"
                },
                "hex_color": {
                    "type": "string",
                    "description": "Hex color code (e.g., '#FF8000' or 'FF8000')",
                    "pattern": "^#?[0-9A-Fa-f]{6}$"
                },
                "delay": {
                    "type": "integer",
                    "description": "Optional delay in seconds (default: 0)",
                    "minimum": 0
                }
            },
            "required": ["device_id", "hex_color"]
        },
        "function": tool_functions["device_set_hex_color"]
    }

    tools["device_set_named_color"] = {
        "description": "Set RGB color using named color (954 XKCD colors + aliases)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "integer",
                    "description": "The ID of the RGB device"
                },
                "color_name": {
                    "type": "string",
                    "description": "Color name (e.g., 'sky blue', 'warm white', 'burnt orange')"
                },
                "delay": {
                    "type": "integer",
                    "description": "Optional delay in seconds (default: 0)",
                    "minimum": 0
                }
            },
            "required": ["device_id", "color_name"]
        },
        "function": tool_functions["device_set_named_color"]
    }

    tools["device_set_white_levels"] = {
        "description": "Set white channel levels for RGBW devices",
        "inputSchema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "integer",
                    "description": "The ID of the RGBW device"
                },
                "white_level": {
                    "type": "number",
                    "description": "White channel level (0-100), optional",
                    "minimum": 0,
                    "maximum": 100
                },
                "white_level2": {
                    "type": "number",
                    "description": "Second white channel level (0-100), optional",
                    "minimum": 0,
                    "maximum": 100
                },
                "white_temperature": {
                    "type": "integer",
                    "description": "White temperature in Kelvin (1200-15000), optional",
                    "minimum": 1200,
                    "maximum": 15000
                },
                "delay": {
                    "type": "integer",
                    "description": "Optional delay in seconds (default: 0)",
                    "minimum": 0
                }
            },
            "required": ["device_id"]
        },
        "function": tool_functions["device_set_white_levels"]
    }

    # Thermostat control
    tools["thermostat_set_heat_setpoint"] = {
        "description": "Set heat setpoint for a thermostat device",
        "inputSchema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "integer",
                    "description": "The ID of the thermostat device"
                },
                "temperature": {
                    "type": "number",
                    "description": "Temperature setpoint value (typically Fahrenheit)"
                }
            },
            "required": ["device_id", "temperature"]
        },
        "function": tool_functions["thermostat_set_heat_setpoint"]
    }

    tools["thermostat_set_cool_setpoint"] = {
        "description": "Set cool setpoint for a thermostat device",
        "inputSchema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "integer",
                    "description": "The ID of the thermostat device"
                },
                "temperature": {
                    "type": "number",
                    "description": "Temperature setpoint value (typically Fahrenheit)"
                }
            },
            "required": ["device_id", "temperature"]
        },
        "function": tool_functions["thermostat_set_cool_setpoint"]
    }

    tools["thermostat_set_hvac_mode"] = {
        "description": "Set HVAC operating mode for a thermostat device",
        "inputSchema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "integer",
                    "description": "The ID of the thermostat device"
                },
                "mode": {
                    "type": "string",
                    "description": "HVAC mode",
                    "enum": ["heat", "cool", "auto", "off", "heatcool", "programheat", "programcool", "programauto"]
                }
            },
            "required": ["device_id", "mode"]
        },
        "function": tool_functions["thermostat_set_hvac_mode"]
    }

    tools["thermostat_set_fan_mode"] = {
        "description": "Set fan operating mode for a thermostat device",
        "inputSchema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "integer",
                    "description": "The ID of the thermostat device"
                },
                "mode": {
                    "type": "string",
                    "description": "Fan mode",
                    "enum": ["auto", "alwayson"]
                }
            },
            "required": ["device_id", "mode"]
        },
        "function": tool_functions["thermostat_set_fan_mode"]
    }

    # Variable control
    tools["variable_update"] = {
        "description": "Update a variable's value",
        "inputSchema": {
            "type": "object",
            "properties": {
                "variable_id": {
                    "type": "integer",
                    "description": "The ID of the variable"
                },
                "value": {
                    "type": "string",
                    "description": "The new value for the variable"
                }
            },
            "required": ["variable_id", "value"]
        },
        "function": tool_functions["variable_update"]
    }

    # Variable creation
    tools["variable_create"] = {
        "description": "Create a new variable",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The name of the variable (required)"
                },
                "value": {
                    "type": "string",
                    "description": "Initial value for the variable (optional, defaults to empty string)"
                },
                "folder_id": {
                    "type": "integer",
                    "description": "Folder ID for organization (optional, defaults to 0 = root)"
                }
            },
            "required": ["name"]
        },
        "function": tool_functions["variable_create"]
    }

    # Action group control
    tools["action_execute_group"] = {
        "description": "Execute an action group",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action_group_id": {
                    "type": "integer",
                    "description": "The ID of the action group"
                },
                "delay": {
                    "type": "integer",
                    "description": "Optional delay in seconds"
                }
            },
            "required": ["action_group_id"]
        },
        "function": tool_functions["action_execute_group"]
    }

    # Historical analysis
    tools["analyze_historical_data"] = {
        "description": "Analyze historical data patterns and trends for specific devices using AI-powered insights. IMPORTANT: Requires EXACT device names - use 'search_entities' or 'list_devices' first to find correct device names. Only works if InfluxDB historical data logging is enabled.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language query about what you want to analyze (e.g., 'show state changes', 'analyze usage patterns', 'track temperature trends'). This helps the system select the right device properties to analyze."
                },
                "device_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "EXACT device names to analyze (case-sensitive). Must match device names exactly as they appear in Indigo. Use 'search_entities' or 'list_devices' first to find correct names. Examples: ['Living Room Lamp', 'Front Door Sensor', 'Master Bedroom Thermostat']"
                },
                "time_range_days": {
                    "type": "integer",
                    "description": "Number of days to analyze (1-365, default: 30). Larger ranges take longer to process."
                }
            },
            "required": ["query", "device_names"]
        },
        "function": tool_functions["analyze_historical_data"]
    }

    # List tools
    tools["list_devices"] = {
        "description": "List all devices with optional state filtering and pagination support",
        "inputSchema": {
            "type": "object",
            "properties": {
                "state_filter": {
                    "type": "object",
                    "description": "Optional state conditions to filter devices"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of devices to return (default: 50)",
                    "default": 50,
                    "minimum": 1,
                    "maximum": 500
                },
                "offset": {
                    "type": "integer",
                    "description": "Number of devices to skip (default: 0)",
                    "default": 0,
                    "minimum": 0
                }
            }
        },
        "function": tool_functions["list_devices"]
    }

    tools["list_variables"] = {
        "description": "List all variables with id, name, and folder (when not in root), with pagination support",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of variables to return (default: 50)",
                    "default": 50,
                    "minimum": 1,
                    "maximum": 500
                },
                "offset": {
                    "type": "integer",
                    "description": "Number of variables to skip (default: 0)",
                    "default": 0,
                    "minimum": 0
                }
            }
        },
        "function": tool_functions["list_variables"]
    }

    tools["list_action_groups"] = {
        "description": "List all action groups with pagination support",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of action groups to return (default: 50)",
                    "default": 50,
                    "minimum": 1,
                    "maximum": 500
                },
                "offset": {
                    "type": "integer",
                    "description": "Number of action groups to skip (default: 0)",
                    "default": 0,
                    "minimum": 0
                }
            }
        },
        "function": tool_functions["list_action_groups"]
    }

    # List variable folders tool
    tools["list_variable_folders"] = {
        "description": "List all variable folders for organization",
        "inputSchema": {
            "type": "object",
            "properties": {}
        },
        "function": tool_functions["list_variable_folders"]
    }

    # State-based queries
    tools["get_devices_by_state"] = {
        "description": "Get devices by state conditions with pagination support",
        "inputSchema": {
            "type": "object",
            "properties": {
                "state_conditions": {
                    "type": "object",
                    "description": "State conditions to match"
                },
                "device_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional device types to filter. Valid types: dimmer, relay, sensor, multiio, speedcontrol, sprinkler, thermostat, device. Common aliases supported: light→dimmer, switch→relay, motion→sensor, fan→speedcontrol, etc."
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of devices to return (default: 50)",
                    "default": 50,
                    "minimum": 1,
                    "maximum": 500
                },
                "offset": {
                    "type": "integer",
                    "description": "Number of devices to skip (default: 0)",
                    "default": 0,
                    "minimum": 0
                }
            },
            "required": ["state_conditions"]
        },
        "function": tool_functions["get_devices_by_state"]
    }

    # Direct lookup tools
    tools["get_device_by_id"] = {
        "description": "Get a specific device by ID",
        "inputSchema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "integer",
                    "description": "The device ID"
                }
            },
            "required": ["device_id"]
        },
        "function": tool_functions["get_device_by_id"]
    }

    tools["get_variable_by_id"] = {
        "description": "Get a specific variable by ID",
        "inputSchema": {
            "type": "object",
            "properties": {
                "variable_id": {
                    "type": "integer",
                    "description": "The variable ID"
                }
            },
            "required": ["variable_id"]
        },
        "function": tool_functions["get_variable_by_id"]
    }

    tools["get_action_group_by_id"] = {
        "description": "Get a specific action group by ID",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action_group_id": {
                    "type": "integer",
                    "description": "The action group ID"
                }
            },
            "required": ["action_group_id"]
        },
        "function": tool_functions["get_action_group_by_id"]
    }

    # Event log tool — recent tail by default, historical search when filtered
    tools["query_event_log"] = {
        "description": "Read the Indigo event log, newest first. Called with no filters it returns the most recent entries from Indigo's live event log (fast). Add any of query/types/start_time/end_time and it scans the daily log files instead, reaching full history with text/regex matching, type filters, and time ranges. Each entry is {timestamp, type, message}; line types include 'Trigger' (a trigger fired), 'Schedule' (a schedule executed), 'Action Group' (an action group ran), 'Z-Wave' and plugin names (device updates), and error types. The response 'source' field is 'live' or 'log_files'.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Case-insensitive substring to match (or a regular expression when regex=true). Supplying this scans the historical log files."
                },
                "regex": {
                    "type": "boolean",
                    "description": "Treat query as a regular expression (default: false)"
                },
                "types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Only entries of these types, e.g. [\"Trigger\", \"Schedule\", \"Action Group\", \"Z-Wave\"]. Supplying this scans the historical log files."
                },
                "start_time": {
                    "type": "string",
                    "description": "ISO datetime lower bound, e.g. 2026-07-01T00:00:00. Supplying this scans the historical log files."
                },
                "end_time": {
                    "type": "string",
                    "description": "ISO datetime upper bound"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum entries to return (default: 50)",
                    "default": 50,
                    "minimum": 1,
                    "maximum": 1000
                },
                "offset": {
                    "type": "integer",
                    "description": "Number of entries to skip (default: 0)",
                    "default": 0,
                    "minimum": 0
                }
            }
        },
        "function": tool_functions["query_event_log"]
    }

    # ------------------------------------------------------------------
    # Automation introspection tools (triggers, schedules, action groups)
    # ------------------------------------------------------------------

    tools["list_triggers"] = {
        "description": "List Indigo triggers with a one-line summary of what each one watches (device state, variable, plugin event, ...). Filter by name, enabled state, type, or folder. Use get_automation_details for a trigger's conditions and actions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name_contains": {
                    "type": "string",
                    "description": "Case-insensitive substring filter on the trigger name"
                },
                "enabled_only": {
                    "type": "boolean",
                    "description": "Only return enabled triggers (default: false)"
                },
                "trigger_type": {
                    "type": "string",
                    "description": "Filter by trigger type: device_state_change, variable_change, plugin_event, server_startup, email_received, power_failure, interface_failure, interface_initialized"
                },
                "folder_id": {
                    "type": "integer",
                    "description": "Only triggers in this folder"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of triggers to return (default: 50)",
                    "default": 50,
                    "minimum": 1,
                    "maximum": 500
                },
                "offset": {
                    "type": "integer",
                    "description": "Number of triggers to skip (default: 0)",
                    "default": 0,
                    "minimum": 0
                }
            }
        },
        "function": tool_functions["list_triggers"]
    }

    tools["list_schedules"] = {
        "description": "List Indigo schedules (time/date events) including each schedule's next execution time and a human-readable timing summary. Sorted by next execution by default. Use get_automation_details for a schedule's conditions and actions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name_contains": {
                    "type": "string",
                    "description": "Case-insensitive substring filter on the schedule name"
                },
                "enabled_only": {
                    "type": "boolean",
                    "description": "Only return enabled schedules (default: false)"
                },
                "folder_id": {
                    "type": "integer",
                    "description": "Only schedules in this folder"
                },
                "sort_by": {
                    "type": "string",
                    "enum": ["next_execution", "name"],
                    "description": "Sort order (default: next_execution; schedules without one sort last)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of schedules to return (default: 50)",
                    "default": 50,
                    "minimum": 1,
                    "maximum": 500
                },
                "offset": {
                    "type": "integer",
                    "description": "Number of schedules to skip (default: 0)",
                    "default": 0,
                    "minimum": 0
                }
            }
        },
        "function": tool_functions["list_schedules"]
    }

    tools["get_automation_details"] = {
        "description": "Explain a trigger, schedule, or action group in full: the event or timing that fires it, its condition tree, and every action step it executes (device commands, variable writes, nested action groups, embedded Python scripts, plugin actions with their configuration). Entity IDs are resolved to names. Action steps and conditions come from Indigo's database file, which can lag live edits by a few minutes (see meta.structure_source).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_type": {
                    "type": "string",
                    "enum": ["trigger", "schedule", "action_group"],
                    "description": "The kind of automation element"
                },
                "entity_id": {
                    "type": "integer",
                    "description": "The element ID"
                },
                "include_scripts": {
                    "type": "boolean",
                    "description": "Include embedded Python script source in action steps (default: true; scripts over 4000 chars are truncated)"
                }
            },
            "required": ["entity_type", "entity_id"]
        },
        "function": tool_functions["get_automation_details"]
    }

    tools["find_automation_references"] = {
        "description": "Reverse lookup: find every trigger, schedule, and action group that references a device, variable, or action group — tagged by role (watches = trigger fires on it, acts_on = an action commands it, sets = an action writes it, condition_reads = a condition checks it, executes = runs the action group), including indirect paths through nested action-group chains (via_action_groups). Answers 'what could change this device?' and 'what watches this variable?'.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_type": {
                    "type": "string",
                    "enum": ["device", "variable", "action_group"],
                    "description": "The kind of entity to find references to"
                },
                "entity_id": {
                    "type": "integer",
                    "description": "The entity ID"
                },
                "include_server_check": {
                    "type": "boolean",
                    "description": "Also cross-check with the Indigo server's own dependency graph (slower but catches control pages and very recent edits; default: true)"
                }
            },
            "required": ["entity_type", "entity_id"]
        },
        "function": tool_functions["find_automation_references"]
    }

    # ------------------------------------------------------------------
    # Event-log investigation tools
    # ------------------------------------------------------------------

    tools["investigate_event"] = {
        "description": "Answer 'what caused this?' for a device change: locates the device's state-change line in the event log, collects the triggers/schedules/action groups that fired in a window around it, and ranks them as candidate causes using structural evidence (does the automation actually act on this device, directly or through action-group chains?) plus temporal proximity. Returns evidence per candidate — follow up with get_automation_details on the top candidate. An empty candidate list means the change was likely manual, external, or plugin-internal.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "integer",
                    "description": "The device whose change to investigate (preferred — enables structural ranking)"
                },
                "search_text": {
                    "type": "string",
                    "description": "Alternative: locate the target log line by text instead of device id"
                },
                "around_time": {
                    "type": "string",
                    "description": "ISO datetime near the event; defaults to the most recent match"
                },
                "occurrence": {
                    "type": "integer",
                    "description": "When around_time is not given: investigate the Nth most recent match (default: 1)",
                    "default": 1,
                    "minimum": 1
                },
                "lookback_seconds": {
                    "type": "integer",
                    "description": "How far before the event to look for causes (default: 60)",
                    "default": 60,
                    "minimum": 1,
                    "maximum": 3600
                },
                "lookahead_seconds": {
                    "type": "integer",
                    "description": "How far after the event to look (default: 5; status updates often log after the command)",
                    "default": 5,
                    "minimum": 0,
                    "maximum": 600
                }
            }
        },
        "function": tool_functions["investigate_event"]
    }

    # ------------------------------------------------------------------
    # Automation control (writes)
    # ------------------------------------------------------------------

    tools["automation_control"] = {
        "description": "Control a trigger, schedule, or action group: enable/disable (optionally with duration_seconds to auto-revert — e.g. 'disable this trigger for 2 hours'), execute now, duplicate (the supported way to 'create a variant' — duplicate then adjust), move_to_folder, remove_delayed_actions, or delete. Deleting is irreversible: it requires confirm=true AND the 'Allow AI to delete automations' plugin preference. Note: Indigo has no API to author a trigger's actions or conditions from scratch, so duplicate-and-modify is the creation path. Action groups only support execute/duplicate/move_to_folder/delete.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_type": {
                    "type": "string",
                    "enum": ["trigger", "schedule", "action_group"],
                    "description": "The kind of automation element"
                },
                "entity_id": {
                    "type": "integer",
                    "description": "The element ID"
                },
                "action": {
                    "type": "string",
                    "enum": ["enable", "disable", "execute", "duplicate",
                             "move_to_folder", "remove_delayed_actions", "delete"],
                    "description": "What to do"
                },
                "duration_seconds": {
                    "type": "integer",
                    "description": "For enable/disable: automatically revert after this many seconds",
                    "minimum": 1
                },
                "delay_seconds": {
                    "type": "integer",
                    "description": "For enable/disable/execute: apply after this many seconds",
                    "minimum": 1
                },
                "duplicate_name": {
                    "type": "string",
                    "description": "For duplicate: name for the copy"
                },
                "folder_id": {
                    "type": "integer",
                    "description": "For move_to_folder: destination folder ID"
                },
                "confirm": {
                    "type": "boolean",
                    "description": "Required true for delete (irreversible)"
                }
            },
            "required": ["entity_type", "entity_id", "action"]
        },
        "function": tool_functions["automation_control"]
    }

    tools["update_automation"] = {
        "description": "Modify basic fields of a trigger, schedule, or action group. Editable: names/descriptions (all three types); trigger event settings (device_id, state_selector, state_change_type, state_value; variable_id, variable_change_type, variable_value). Schedule TIMING is read-only in Indigo's scripting API — only a schedule's name/description can be edited; timing changes require the Indigo UI. Action steps and conditions can NEVER be modified (Indigo has no API); to change what an automation does, edit it in the Indigo UI. Combined with automation_control's duplicate, this is the supported way to create trigger variants. Requires the 'Allow AI to edit automations (experimental)' plugin preference. Returns a before/after diff and warns when the server discarded a value (e.g. state_value on a becomes_true trigger). Use enable/disable and move_to_folder via automation_control, not here.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_type": {
                    "type": "string",
                    "enum": ["trigger", "schedule", "action_group"],
                    "description": "The kind of automation element"
                },
                "entity_id": {
                    "type": "integer",
                    "description": "The element ID"
                },
                "fields": {
                    "type": "object",
                    "description": "Field name → new value. E.g. {\"name\": \"New name\"}, {\"state_value\": \"PLAYING\"}, {\"device_id\": 123456, \"state_change_type\": \"becomes_false\"}. Enum values use the same normalized names the read tools return (becomes_true, becomes_equal, changes, ...)."
                }
            },
            "required": ["entity_type", "entity_id", "fields"]
        },
        "function": tool_functions["update_automation"]
    }

    # Plugin control tools
    tools["list_plugins"] = {
        "description": "List all Indigo plugins",
        "inputSchema": {
            "type": "object",
            "properties": {
                "include_disabled": {
                    "type": "boolean",
                    "description": "Whether to include disabled plugins (default: False)"
                }
            }
        },
        "function": tool_functions["list_plugins"]
    }

    tools["get_plugin_by_id"] = {
        "description": "Get specific plugin information by ID",
        "inputSchema": {
            "type": "object",
            "properties": {
                "plugin_id": {
                    "type": "string",
                    "description": "Plugin bundle identifier (e.g., 'com.vtmikel.mcp_server')"
                }
            },
            "required": ["plugin_id"]
        },
        "function": tool_functions["get_plugin_by_id"]
    }

    tools["restart_plugin"] = {
        "description": "Restart an Indigo plugin",
        "inputSchema": {
            "type": "object",
            "properties": {
                "plugin_id": {
                    "type": "string",
                    "description": "Plugin bundle identifier"
                }
            },
            "required": ["plugin_id"]
        },
        "function": tool_functions["restart_plugin"]
    }

    tools["get_plugin_status"] = {
        "description": "Get detailed plugin status",
        "inputSchema": {
            "type": "object",
            "properties": {
                "plugin_id": {
                    "type": "string",
                    "description": "Plugin bundle identifier"
                }
            },
            "required": ["plugin_id"]
        },
        "function": tool_functions["get_plugin_status"]
    }

    # ------------------------------------------------------------------
    # Event subscription tools (conditionally included)
    # ------------------------------------------------------------------

    if "create_event_subscription" in tool_functions:
        tools["create_event_subscription"] = {
            "description": "Create a webhook subscription for Indigo entity state changes. When the specified conditions are met on the target entity, a structured JSON event is POSTed to the webhook URL. Supports all device state keys including third-party plugin states.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "webhook_url": {
                        "type": "string",
                        "description": "HTTP(S) endpoint URL to POST events to"
                    },
                    "auth": {
                        "type": "object",
                        "description": "Authentication config for outbound webhooks",
                        "properties": {
                            "mode": {
                                "type": "string",
                                "enum": ["none", "bearer", "hmac"],
                                "description": "Auth mode: none, bearer (token in Authorization header), or hmac (HMAC-SHA256 signature)",
                                "default": "none"
                            },
                            "token": {
                                "type": "string",
                                "description": "Bearer token or HMAC shared secret"
                            },
                            "verify_ssl": {
                                "type": "boolean",
                                "description": "Verify SSL certificates (set false for self-signed certs)",
                                "default": True
                            }
                        }
                    },
                    "entity_type": {
                        "type": "string",
                        "enum": ["device", "variable"],
                        "description": "Type of entity to watch"
                    },
                    "entity_id": {
                        "type": "integer",
                        "description": "Specific entity ID to watch, or omit for all entities of the given type"
                    },
                    "conditions": {
                        "type": "object",
                        "description": "State conditions that trigger the webhook. Uses StateFilter operators: simple equality ({\"onState\": true}), or complex ({\"brightness\": {\"gt\": 50}, \"temperature\": {\"lt\": 32}}). Operators: eq, ne, gt, gte, lt, lte, contains, regex. Webhook fires on transition INTO matching state. For variables, match on the \"value\" key (e.g. {\"value\": true} or {\"value\": {\"gt\": 50}}); variable values are stored as strings but booleans and numbers are coerced automatically. Variable-only: pass {\"any_change\": true} to fire on every value change (not allowed for devices, and cannot be combined with duration_seconds)."
                    },
                    "duration_seconds": {
                        "type": "integer",
                        "description": "Optional dwell time: condition must remain matched for this many seconds before firing. If condition reverts before expiry, webhook is cancelled.",
                        "minimum": 1
                    },
                    "max_fires": {
                        "type": "integer",
                        "description": "Auto-delete subscription after this many successful deliveries. Omit for unlimited. Use 1 for one-shot notifications.",
                        "minimum": 1
                    },
                    "description": {
                        "type": "string",
                        "description": "Human-readable label for this subscription"
                    }
                },
                "required": ["webhook_url", "entity_type", "conditions"]
            },
            "function": tool_functions["create_event_subscription"]
        }

        tools["list_event_subscriptions"] = {
            "description": "List all active event webhook subscriptions with delivery health stats, or get a single subscription by ID.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "subscription_id": {
                        "type": "string",
                        "description": "Optional: get a specific subscription by ID"
                    }
                }
            },
            "function": tool_functions["list_event_subscriptions"]
        }

        tools["delete_event_subscription"] = {
            "description": "Delete an event webhook subscription by ID. Cancels any pending dwell timers for the subscription.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "subscription_id": {
                        "type": "string",
                        "description": "ID of the subscription to delete"
                    }
                },
                "required": ["subscription_id"]
            },
            "function": tool_functions["delete_event_subscription"]
        }

    return tools
