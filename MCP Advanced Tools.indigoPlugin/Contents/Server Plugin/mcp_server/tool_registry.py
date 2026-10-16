"""
Tool registry for MCP server.

Defines all available tool schemas for the MCP server.
Each tool includes a description, input schema, and reference to its implementation function.
"""

# Tools that change state. Their activity is always logged at INFO;
# everything else is read-only and logs at DEBUG unless the user enables
# the "Log AI read activity" preference (see common/log_style.py).
WRITE_TOOLS = frozenset({
    "create_event_subscription",
    "delete_event_subscription",
    "control_trigger",
    "control_schedule",
    "control_action_group",
    "update_trigger",
    "update_schedule",
    "update_action_group",
    "manage_tags",
    "tag_objects",
})

# Tools this plugin served before Indigo 2026.1, mapped to the built-in
# Indigo MCP Control (/v3/api/mcp) tool that replaces each. A call to one of
# these names (e.g. from a client's cached tool list) gets an error naming
# the replacement instead of a bare "Unknown tool".
MCP_CONTROL_EQUIVALENTS = {
    "device_turn_on": "turn_on",
    "device_turn_off": "turn_off",
    "device_set_brightness": "set_brightness",
    "device_set_rgb_color": "set_color",
    "device_set_rgb_percent": "set_color",
    "device_set_hex_color": "set_color",
    "device_set_named_color": "set_color",
    "device_set_white_levels": "set_color",
    "thermostat_set_heat_setpoint": "set_heat_setpoint",
    "thermostat_set_cool_setpoint": "set_cool_setpoint",
    "thermostat_set_hvac_mode": "set_hvac_mode",
    "thermostat_set_fan_mode": "set_fan_mode",
    "variable_update": "update_variable",
    "variable_create": "create_variable",
    "action_execute_group": "execute_action_group",
    "list_devices": "list_devices",
    "list_variables": "list_variables",
    "list_action_groups": "list_action_groups",
    "list_variable_folders": "list_folders",
    "get_devices_by_type": "get_devices_by_type",
    "get_devices_by_state": "get_devices_by_state",
    "get_device_by_id": "get_device_by_id",
    "get_variable_by_id": "get_variable_by_id",
    "get_action_group_by_id": "get_action_group_by_id",
    "list_plugins": "list_plugins",
    "get_plugin_by_id": "get_plugin",
    "get_plugin_status": "get_plugin_status",
    "restart_plugin": "restart_plugin",
}

# Tools that moved to another Indigo plugin, mapped to (the tool's name as
# this server lists it once that plugin is installed, the plugin).
MOVED_TO_PLUGINS = {
    "analyze_historical_data": (
        "influxlog_query_history",
        "the Grafana Home Dashboard (InfluxDB logging) plugin",
    ),
}


def removed_tool_hint(tool_name):
    """
    Error text for a call to a tool that moved to Indigo MCP Control or to
    another plugin, or None when tool_name was never one of ours.
    """
    moved = MOVED_TO_PLUGINS.get(tool_name)
    if moved is not None:
        replacement, plugin = moved
        return (
            f"Tool '{tool_name}' was removed from MCP Advanced Tools (formerly the MCP Server plugin): {plugin} "
            f"provides it as `{replacement}`, listed on this server while that "
            f"plugin is installed."
        )
    equivalent = MCP_CONTROL_EQUIVALENTS.get(tool_name)
    if equivalent is None:
        return None
    hint = (
        f"Tool '{tool_name}' was removed from MCP Advanced Tools (formerly the MCP Server plugin): Indigo's "
        f"built-in MCP Control (Web Server path /v3/api/mcp) provides it as "
        f"`{equivalent}`."
    )
    if tool_name == "action_execute_group":
        hint += " It returns a confirmation token to pass to MCP Control's `confirm` tool."
    return hint


def get_tool_schemas(tool_functions):
    """
    Get all tool schemas with their corresponding implementation functions.

    Args:
        tool_functions: Dictionary mapping tool names to their implementation functions

    Returns:
        Dictionary of tool schemas ready for MCP registration
    """
    tools = {}

    # Tag filter shared by search_entities, list_triggers and list_schedules
    _tag_filter_props = {
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Only entities carrying these Indigo tags (names from MCP Control's list_tags)",
        },
        "tag_match": {
            "type": "string",
            "enum": ["all", "any"],
            "description": "With tags: 'all' (default) requires every tag, 'any' at least one",
        },
    }

    # Search entities tool
    tools["search_entities"] = {
        "description": "Search for Indigo entities using natural language with pagination support. Covers every device, variable, action group, trigger and schedule, including ones not published for remote display. Each result carries its Indigo tags; tags narrows the search to tagged entities ('basement lighting' -> tags [basement, lighting]). To act on a result (turn on, dim, set a variable, run an action group), use Indigo MCP Control's tools (turn_on, set_brightness, update_variable, execute_action_group, ...).",
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
                    "description": "Maximum number of results to return (default: 10, or more when the query asks for a list). Results are ranked best first; an exact name match is always first. Above 20 results, devices come back with minimal fields.",
                    "minimum": 1,
                    "maximum": 500
                },
                "offset": {
                    "type": "integer",
                    "description": "Number of results to skip (default: 0)",
                    "default": 0,
                    "minimum": 0
                },
                **_tag_filter_props,
            },
            "required": ["query"]
        },
        "function": tool_functions["search_entities"]
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
        "description": "List Indigo triggers with a one-line summary of what each one watches (device state, variable, plugin event, ...) and their tags. Filter by name, enabled state, type, folder, or tags. Use get_trigger_details for a trigger's conditions and actions.",
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
                **_tag_filter_props,
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
        "description": "List Indigo schedules (time/date events) including each schedule's next execution time, a human-readable timing summary and its tags. Filter by name, enabled state, folder, or tags. Sorted by next execution by default. Use get_schedule_details for a schedule's conditions and actions.",
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
                **_tag_filter_props,
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

    _DETAILS_COMMON = (
        " Includes its folder and tags. Action steps and conditions come from Indigo's "
        "database file, which can lag live edits by a few minutes (see "
        "meta.structure_source). Entity IDs are resolved to names."
    )
    _include_scripts_prop = {
        "type": "boolean",
        "description": "Include embedded Python script source in action steps and scripted conditions (default: true; scripts over 4000 chars are truncated)"
    }

    tools["get_trigger_details"] = {
        "description": "Explain a trigger in full: the event that fires it, its condition tree (or embedded Python condition script), and every action step it executes (device commands, variable writes, nested action groups, embedded Python, plugin actions with their configuration)." + _DETAILS_COMMON,
        "inputSchema": {
            "type": "object",
            "properties": {
                "trigger_id": {"type": "integer", "description": "The trigger ID"},
                "include_scripts": _include_scripts_prop,
            },
            "required": ["trigger_id"]
        },
        "function": tool_functions["get_trigger_details"]
    }

    tools["get_schedule_details"] = {
        "description": "Explain a schedule in full: its timing, its condition tree (or embedded Python condition script), and every action step it executes." + _DETAILS_COMMON,
        "inputSchema": {
            "type": "object",
            "properties": {
                "schedule_id": {"type": "integer", "description": "The schedule ID"},
                "include_scripts": _include_scripts_prop,
            },
            "required": ["schedule_id"]
        },
        "function": tool_functions["get_schedule_details"]
    }

    tools["get_action_group_details"] = {
        "description": "Explain an action group in full: every action step it executes (device commands, variable writes, nested action groups, embedded Python, plugin actions with their configuration)." + _DETAILS_COMMON,
        "inputSchema": {
            "type": "object",
            "properties": {
                "action_group_id": {"type": "integer", "description": "The action group ID"},
                "include_scripts": _include_scripts_prop,
            },
            "required": ["action_group_id"]
        },
        "function": tool_functions["get_action_group_details"]
    }

    tools["find_automation_references"] = {
        "description": "Reverse lookup: find every trigger, schedule, and action group that references a device, variable, or action group — tagged by role (watches = trigger fires on it, acts_on = an action commands it, sets = an action writes it, condition_reads = a condition checks it, including id/name matches inside scripted-condition Python marked confidence: heuristic, script_reference = its id or name appears in an embedded Python action script (heuristic text match), executes = runs the action group), including indirect paths through nested action-group chains (via_action_groups). Answers 'what could change this device?' and 'what watches this variable?'. Follow up with get_trigger_details / get_schedule_details / get_action_group_details.",
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
        "description": "Answer 'what caused this?' for a device change: locates the device's state-change line in the event log, collects the triggers/schedules/action groups that fired in a window around it, and ranks them as candidate causes using structural evidence (does the automation actually act on this device, directly or through action-group chains?) plus temporal proximity. Returns evidence per candidate — follow up with the matching get_*_details tool on the top candidate. An empty candidate list means the change was likely manual, external, or plugin-internal.",
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

    _delete_note = (
        " Deleting is irreversible and requires confirm=true AND the 'Allow AI to "
        "delete automations' plugin preference. All other actions are always available."
    )
    # The confirmation tag (plugin preference, default ask-first)
    _gate_note = (
        " An element carrying the house's confirmation tag (plugin preference, "
        "default 'ask-first') returns requires_confirmation instead: call again with "
        "confirm=true only if the user themselves asked for this change."
    )
    _control_props = {
        "duration_seconds": {
            "type": "integer",
            "description": "For enable/disable: automatically revert after this many seconds",
            "minimum": 1,
        },
        "delay_seconds": {
            "type": "integer",
            "description": "For enable/disable: apply after this many seconds",
            "minimum": 1,
        },
        "duplicate_name": {"type": "string", "description": "For duplicate: name for the copy"},
        "folder_id": {"type": "integer", "description": "For move_to_folder: destination folder ID"},
        "confirm": {
            "type": "boolean",
            "description": "Required true for delete (irreversible) and for an element carrying the confirmation tag",
        },
    }

    def _control_schema(id_name, actions, can_enable=True):
        props = {
            id_name: {"type": "integer", "description": "The element ID"},
            "action": {"type": "string", "enum": actions, "description": "What to do"},
            "duplicate_name": _control_props["duplicate_name"],
            "folder_id": _control_props["folder_id"],
            "confirm": _control_props["confirm"],
        }
        if can_enable:
            props["duration_seconds"] = _control_props["duration_seconds"]
            props["delay_seconds"] = _control_props["delay_seconds"]
        return {"type": "object", "properties": props, "required": [id_name, "action"]}

    # Running an automation is Indigo MCP Control's job (execute_* + confirm)
    _run_note = (
        " To run it, use Indigo MCP Control's {tool} (it returns a token for its "
        "confirm tool)."
    )
    _trigger_schedule_actions = ["enable", "disable", "duplicate",
                                 "move_to_folder", "remove_delayed_actions", "delete"]

    tools["control_trigger"] = {
        "description": "Trigger lifecycle: enable/disable (optionally with duration_seconds to auto-revert — 'disable this trigger for 2 hours'), duplicate (duplicate-then-edit is the supported way to make a variant, since Indigo has no API to author a trigger's actions/conditions from scratch), move_to_folder, remove_delayed_actions, or delete." + _delete_note + _gate_note + _run_note.format(tool="execute_trigger"),
        "inputSchema": _control_schema("trigger_id", _trigger_schedule_actions),
        "function": tool_functions["control_trigger"],
    }
    tools["control_schedule"] = {
        "description": "Schedule lifecycle: enable/disable (with optional duration_seconds auto-revert), duplicate, move_to_folder, remove_delayed_actions, or delete." + _delete_note + _gate_note + _run_note.format(tool="execute_schedule"),
        "inputSchema": _control_schema("schedule_id", _trigger_schedule_actions),
        "function": tool_functions["control_schedule"],
    }
    tools["control_action_group"] = {
        "description": "Action-group lifecycle: duplicate, move_to_folder, or delete. (Action groups have no enable/disable or delayed-action queue.)" + _delete_note + _gate_note + _run_note.format(tool="execute_action_group"),
        "inputSchema": _control_schema(
            "action_group_id", ["duplicate", "move_to_folder", "delete"],
            can_enable=False),
        "function": tool_functions["control_action_group"],
    }

    _update_note = (
        " Action steps and conditions can NEVER be modified (Indigo has no API); to "
        "change what an automation does, edit it in the Indigo UI. Returns a before/after diff."
    ) + _gate_note
    _update_confirm = {
        "type": "boolean",
        "description": "Required true for an element carrying the confirmation tag",
    }
    tools["update_trigger"] = {
        "description": "Edit a trigger's basic fields: name, description, and its event settings — what it watches (device_id, state_selector, state_change_type, state_value; or variable_id, variable_change_type, variable_value). Enum values use the normalized names the read tools return (becomes_true, becomes_equal, changes, …)." + _update_note,
        "inputSchema": {
            "type": "object",
            "properties": {
                "trigger_id": {"type": "integer", "description": "The trigger ID"},
                "fields": {
                    "type": "object",
                    "description": "Field → new value, e.g. {\"name\": \"New name\"}, {\"state_value\": \"PLAYING\"}, {\"device_id\": 123456, \"state_change_type\": \"becomes_false\"}.",
                },
                "confirm": _update_confirm,
            },
            "required": ["trigger_id", "fields"],
        },
        "function": tool_functions["update_trigger"],
    }
    tools["update_schedule"] = {
        "description": "Edit a schedule's name and/or description. (Schedule timing is read-only in Indigo's scripting API — change it in the Indigo UI.)" + _update_note,
        "inputSchema": {
            "type": "object",
            "properties": {
                "schedule_id": {"type": "integer", "description": "The schedule ID"},
                "fields": {
                    "type": "object",
                    "description": "Field → new value, e.g. {\"name\": \"…\", \"description\": \"…\"}.",
                },
                "confirm": _update_confirm,
            },
            "required": ["schedule_id", "fields"],
        },
        "function": tool_functions["update_schedule"],
    }
    tools["update_action_group"] = {
        "description": "Edit an action group's name and/or description. (Its action steps are read-only in Indigo's scripting API — change them in the Indigo UI.)" + _update_note,
        "inputSchema": {
            "type": "object",
            "properties": {
                "action_group_id": {"type": "integer", "description": "The action group ID"},
                "fields": {
                    "type": "object",
                    "description": "Field → new value, e.g. {\"name\": \"…\", \"description\": \"…\"}.",
                },
                "confirm": _update_confirm,
            },
            "required": ["action_group_id", "fields"],
        },
        "function": tool_functions["update_action_group"],
    }

    # ------------------------------------------------------------------
    # Tags (Indigo 2026.1). MCP Control reads tags (list_tags, the tag
    # filter on its list_* tools); these create, edit and assign them.
    # ------------------------------------------------------------------

    tools["manage_tags"] = {
        "description": "Maintain Indigo's server-wide tag library: create a tag (name + color), update one (rename and/or recolor; a rename carries to every object that has the tag), or delete one. Tag names are lowercase letters in words joined by single dashes ('kitchen', 'holiday-lighting'). Only the background color is set; Indigo derives the text and border colors. Deleting removes the tag from every object carrying it and cannot be undone: it needs the 'Allow AI to delete tags' plugin preference AND confirm=true (the first call returns how many objects carry the tag). List the library with MCP Control's list_tags; put tags on objects with tag_objects.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["create", "update", "delete"], "description": "What to do"},
                "tag": {"type": "string", "description": "The tag name (for create: the new tag)"},
                "new_tag": {"type": "string", "description": "For update: the new name"},
                "color": {"type": "string", "description": "For create (required) and update: six hex digits, e.g. '4A90D9' (a leading # is fine)"},
                "confirm": {"type": "boolean", "description": "Required true for delete, and for renaming the confirmation tag"},
            },
            "required": ["action", "tag"],
        },
        "function": tool_functions["manage_tags"],
    }

    tools["tag_objects"] = {
        "description": "Put an Indigo tag on, or take it off, up to 200 objects of any type at once: devices, variables, triggers, schedules, action groups and control pages. The tag must already exist (create it with manage_tags). Returns one outcome per object (added, already, removed, not_present, not_found, error), which is also the list to reverse the change with. dry_run=true reports what would change without writing. Removing a tag from more than 25 objects, or removing the confirmation tag (plugin preference, default 'ask-first'), needs confirm=true.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tag": {"type": "string", "description": "The tag name"},
                "action": {"type": "string", "enum": ["add", "remove"], "description": "Put the tag on or take it off"},
                "objects": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 200,
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": ["device", "variable", "trigger", "schedule", "action_group", "control_page"],
                            },
                            "id": {"type": "integer"},
                        },
                        "required": ["type", "id"],
                    },
                    "description": "The objects, e.g. [{\"type\": \"device\", \"id\": 123}]",
                },
                "dry_run": {"type": "boolean", "description": "Report what would change without writing (default: false)"},
                "confirm": {"type": "boolean", "description": "Required true for a bulk removal (> 25 objects) or removing the confirmation tag"},
            },
            "required": ["tag", "action", "objects"],
        },
        "function": tool_functions["tag_objects"],
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
