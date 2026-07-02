"""
Code maps for the .indiDb XML format.

All numeric codes below were verified against a live Indigo 2025.2 server
(the k* enums via introspection, the XML class codes by cross-referencing
database entries with the Indigo UI). Unknown codes must never raise: every
decoder in this package falls back to "unknown" plus raw passthrough so a
format change in a future Indigo release degrades output instead of
breaking it.
"""

# ---------------------------------------------------------------------------
# Action step <Action> "Class" codes (inside ActionSteps vectors)
# ---------------------------------------------------------------------------

ACTION_CLASS_NONE = 0
ACTION_CLASS_DEVICE = 1
ACTION_CLASS_EXECUTE_ACTION_GROUP = 100
ACTION_CLASS_EMBEDDED_SCRIPT = 101
ACTION_CLASS_VARIABLE = 201
ACTION_CLASS_PLUGIN = 999

ACTION_CLASS_KINDS = {
    ACTION_CLASS_NONE: "none",
    ACTION_CLASS_DEVICE: "device_action",
    ACTION_CLASS_EXECUTE_ACTION_GROUP: "execute_action_group",
    ACTION_CLASS_EMBEDDED_SCRIPT: "embedded_script",
    ACTION_CLASS_VARIABLE: "variable_action",
    ACTION_CLASS_PLUGIN: "plugin_action",
}

# <DeviceAction> command codes — indigo.kDeviceAction values.
DEVICE_ACTION_COMMANDS = {
    0: "all_off",
    1: "all_lights_on",
    2: "all_lights_off",
    4: "turn_on",
    5: "turn_off",
    6: "toggle",
    7: "set_brightness",
    8: "brighten_by",
    9: "dim_by",
    10: "set_color_levels",
    11: "request_status",
    28: "lock",
    29: "unlock",
    30: "open",
    31: "close",
}

# <VarAction> codes on variable action steps. Only 0 (set value) has been
# observed in the wild; other codes pass through as variable_action_code_<n>.
VARIABLE_ACTION_COMMANDS = {
    0: "set_value",
}

# ---------------------------------------------------------------------------
# <Trigger> "Class" codes (TriggerList)
# ---------------------------------------------------------------------------

TRIGGER_CLASS_KINDS = {
    501: "device_state_change",
    502: "variable_change",
    509: "server_startup",
    598: "plugin_event",
}

# <DeviceStateChange> codes — indigo.kStateChange values.
STATE_CHANGE_TYPES = {
    110: "becomes_true",
    111: "becomes_false",
    112: "becomes_equal",
    113: "becomes_not_equal",
    114: "becomes_greater_than",
    115: "becomes_less_than",
    116: "changes",
}

# <VarChange> codes — indigo.kVarChange values.
VAR_CHANGE_TYPES = {
    0: "becomes_true",
    1: "becomes_false",
    2: "becomes_equal",
    3: "becomes_not_equal",
    4: "becomes_greater_than",
    5: "becomes_less_than",
    6: "changes",
}

# ---------------------------------------------------------------------------
# Schedule (TDTrigger) timing codes — indigo.kTimeType / indigo.kDateType.
# ---------------------------------------------------------------------------

TIME_TYPES = {
    0: "absolute",
    1: "sunrise",
    2: "sunset",
    3: "countdown",
}

DATE_TYPES = {
    0: "every_day",
    1: "days_of_week",
    2: "absolute",
    3: "days_of_month",
    4: "days_of_month_interval",
}

# ---------------------------------------------------------------------------
# <Condition> "Type" codes (inside ConditionList/Conditions vectors)
# ---------------------------------------------------------------------------

CONDITION_TYPE_KINDS = {
    3: "variable_compare",
    5: "time_date_compare",
    7: "device_state_compare",
}

# Container-level <Condition Type=...>: 0 = no conditions, 100 = condition list.
CONDITION_CONTAINER_NONE = 0
CONDITION_CONTAINER_LIST = 100

# <Logic> on a ConditionList. Verified: 1 = "all" (AND). 0 is presumed "any"
# (OR) from UI ordering; conditions always carry raw codes alongside.
CONDITION_LOGIC = {
    0: "or",
    1: "and",
}

# Comparison operator codes on condition items (<VarState>, <DevComp>).
# Inferred from the Indigo condition-editor operator ordering, which mirrors
# kVarChange without the "becomes" semantics. Raw codes are always passed
# through alongside the label.
CONDITION_COMPARISONS = {
    0: "is_true",
    1: "is_false",
    2: "equals",
    3: "not_equal",
    4: "greater_than",
    5: "less_than",
}


def lookup(table: dict, code, prefix: str) -> str:
    """Decode a code via table, falling back to '<prefix>_<code>'."""
    try:
        code = int(code)
    except (TypeError, ValueError):
        return f"{prefix}_unknown"
    return table.get(code, f"{prefix}_{code}")
