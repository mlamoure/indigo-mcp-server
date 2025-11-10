"""
Tool registry for MCP server.

Defines all available tool schemas for the MCP server.
Each tool includes a description, input schema, and reference to its implementation function.
"""


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
                    "description": "Optional entity types to search"
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

    # Log query tool
    tools["query_event_log"] = {
        "description": "Query recent Indigo server event log entries",
        "inputSchema": {
            "type": "object",
            "properties": {
                "line_count": {
                    "type": "integer",
                    "description": "Number of log entries to return (default: 20)"
                },
                "show_timestamp": {
                    "type": "boolean",
                    "description": "Include timestamps in log entries (default: true)"
                }
            }
        },
        "function": tool_functions["query_event_log"]
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

    return tools
