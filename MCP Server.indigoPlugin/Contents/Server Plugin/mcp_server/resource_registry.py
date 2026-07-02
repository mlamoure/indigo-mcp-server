"""
Resource registry for MCP server.

Defines all available resource endpoints for the MCP server.
Each resource includes a URI, name, description, and reference to its implementation function.
"""


def get_resource_schemas(resource_functions):
    """
    Get all resource schemas with their corresponding implementation functions.

    Args:
        resource_functions: Dictionary mapping resource URIs to their implementation functions

    Returns:
        Dictionary of resource schemas ready for MCP registration
    """
    resources = {}

    # Device resources
    resources["indigo://devices"] = {
        "name": "Devices",
        "description": "List all Indigo devices",
        "function": resource_functions["list_devices"]
    }

    resources["indigo://devices/{device_id}"] = {
        "name": "Device",
        "description": "Get a specific device",
        "function": resource_functions["get_device"]
    }

    # Variable resources
    resources["indigo://variables"] = {
        "name": "Variables",
        "description": "List all Indigo variables",
        "function": resource_functions["list_variables"]
    }

    resources["indigo://variables/{variable_id}"] = {
        "name": "Variable",
        "description": "Get a specific variable",
        "function": resource_functions["get_variable"]
    }

    # Action resources
    resources["indigo://actions"] = {
        "name": "Action Groups",
        "description": "List all action groups",
        "function": resource_functions["list_actions"]
    }

    resources["indigo://actions/{action_id}"] = {
        "name": "Action Group",
        "description": "Get a specific action group",
        "function": resource_functions["get_action"]
    }

    # Trigger resources
    resources["indigo://triggers"] = {
        "name": "Triggers",
        "description": "List all Indigo triggers",
        "function": resource_functions["list_triggers"]
    }

    resources["indigo://triggers/{trigger_id}"] = {
        "name": "Trigger",
        "description": "Get a specific trigger with its conditions and actions",
        "function": resource_functions["get_trigger"]
    }

    # Schedule resources
    resources["indigo://schedules"] = {
        "name": "Schedules",
        "description": "List all Indigo schedules",
        "function": resource_functions["list_schedules"]
    }

    resources["indigo://schedules/{schedule_id}"] = {
        "name": "Schedule",
        "description": "Get a specific schedule with its conditions and actions",
        "function": resource_functions["get_schedule"]
    }

    return resources
