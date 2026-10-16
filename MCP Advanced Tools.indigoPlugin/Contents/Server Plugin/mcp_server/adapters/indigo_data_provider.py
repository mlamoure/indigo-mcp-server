"""
Indigo data provider implementation for accessing Indigo entities.
"""

try:
    import indigo
except ImportError:
    pass

import logging
from typing import Dict, List, Any, Optional

from .data_provider import DataProvider
from ..common.json_encoder import filter_json, KEYS_TO_KEEP_MINIMAL_DEVICES


class IndigoDataProvider(DataProvider):
    """Data provider implementation for accessing Indigo entities."""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize the Indigo data provider.

        Args:
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger("Plugin")
    
    def get_all_devices(self) -> List[Dict[str, Any]]:
        """
        Get all devices from Indigo.
        
        Returns:
            List of device dictionaries with minimal fields
        """
        devices = []
        try:
            for dev_id in indigo.devices:
                dev = indigo.devices[dev_id]
                devices.append(dict(dev))
        except Exception as e:
            self.logger.debug(f"Error getting all devices: {e}", exc_info=True)
            
        # Apply filtering to return only minimal keys
        return filter_json(devices, KEYS_TO_KEEP_MINIMAL_DEVICES)
    
    def get_device(self, device_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a specific device by ID.
        
        Args:
            device_id: The device ID
            
        Returns:
            Device dictionary or None if not found
        """
        try:
            if device_id in indigo.devices:
                dev = indigo.devices[device_id]
                return dict(dev)
        except Exception as e:
            self.logger.debug(f"Error getting device {device_id}: {e}", exc_info=True)
            
        return None
    
    def get_all_variables(self) -> List[Dict[str, Any]]:
        """
        Get all variables from Indigo with minimal fields for listing.

        Returns:
            List of variable dictionaries with minimal fields:
            - id: Variable ID
            - name: Variable name
            - folderName: Folder name (only if not in root, i.e., folderId != 0)
        """
        variables = []
        try:
            # Build folder lookup map for efficient folder name resolution
            folder_map = {}
            try:
                for folder in indigo.variables.folders:
                    folder_map[folder.id] = folder.name
            except Exception as folder_error:
                self.logger.debug(f"Error building folder map: {folder_error}", exc_info=True)

            # Get all variables with filtered fields
            for var_id in indigo.variables:
                var = indigo.variables[var_id]

                # Build minimal variable dict
                minimal_var = {
                    "id": var.id,
                    "name": var.name
                }

                # Add folder name if variable is not in root (folderId != 0)
                if hasattr(var, 'folderId') and var.folderId != 0:
                    folder_name = folder_map.get(var.folderId, f"Unknown Folder ({var.folderId})")
                    minimal_var["folderName"] = folder_name

                variables.append(minimal_var)

        except Exception as e:
            self.logger.debug(f"Error getting all variables: {e}", exc_info=True)

        return variables
    
    def get_variable(self, variable_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a specific variable by ID.

        Args:
            variable_id: The variable ID

        Returns:
            Variable dictionary or None if not found
        """
        try:
            if variable_id in indigo.variables:
                var = indigo.variables[variable_id]
                return dict(var)
        except Exception as e:
            self.logger.debug(f"Error getting variable {variable_id}: {e}", exc_info=True)

        return None

    def get_all_variables_unfiltered(self) -> List[Dict[str, Any]]:
        """
        Get all variables from Indigo with complete data (unfiltered for vector store).

        Returns:
            List of complete variable dictionaries with all fields
        """
        variables = []
        try:
            for var_id in indigo.variables:
                var = indigo.variables[var_id]
                variables.append(dict(var))
        except Exception as e:
            self.logger.debug(f"Error getting all variables (unfiltered): {e}", exc_info=True)

        return variables

    def get_all_actions(self) -> List[Dict[str, Any]]:
        """
        Get all action groups from Indigo.
        
        Returns:
            List of action group dictionaries with standard fields
        """
        actions = []
        try:
            for action_id in indigo.actionGroups:
                action = indigo.actionGroups[action_id]
                actions.append(dict(action))
        except Exception as e:
            self.logger.debug(f"Error getting all actions: {e}", exc_info=True)
            
        return actions
    
    def get_action(self, action_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a specific action group by ID.
        
        Args:
            action_id: The action group ID
            
        Returns:
            Action group dictionary or None if not found
        """
        try:
            if action_id in indigo.actionGroups:
                action = indigo.actionGroups[action_id]
                return self._with_folder_name(dict(action), indigo.actionGroups)
        except Exception as e:
            self.logger.debug(f"Error getting action {action_id}: {e}", exc_info=True)
            
        return None
    
    def get_action_group(self, action_group_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a specific action group by ID.
        
        Args:
            action_group_id: The action group ID
            
        Returns:
            Action group dictionary or None if not found
        """
        return self.get_action(action_group_id)
    
    def get_all_devices_unfiltered(self) -> List[Dict[str, Any]]:
        """
        Get all devices from Indigo with complete data (unfiltered for vector store).
        
        Returns:
            List of complete device dictionaries
        """
        devices = []
        try:
            for dev_id in indigo.devices:
                dev = indigo.devices[dev_id]
                devices.append(dict(dev))
        except Exception as e:
            self.logger.debug(f"Error getting all devices (unfiltered): {e}", exc_info=True)
            
        return devices
    
    def get_all_entities_for_vector_store(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all entities formatted for vector store updates with complete data.

        Returns:
            Dictionary with 'devices', 'variables', 'actions', 'triggers',
            'schedules' keys
        """
        return {
            "devices": self.get_all_devices_unfiltered(),
            "variables": self.get_all_variables_unfiltered(),
            "actions": self.get_all_actions(),
            "triggers": self.get_all_triggers(),
            "schedules": self.get_all_schedules()
        }
    
    def get_event_log_list(
        self,
        line_count: Optional[int] = None,
        show_timestamp: bool = True
    ) -> List[str]:
        """
        Get recent event log entries from Indigo server.

        Args:
            line_count: Number of log entries to return (default: all recent entries)
            show_timestamp: Include timestamps in log entries (default: True)

        Returns:
            List of log entry strings
        """
        try:
            # Build parameters for getEventLogList
            params = {
                "returnAsList": True,  # Always return as list for structured data
                "showTimeStamp": show_timestamp
            }

            if line_count is not None:
                params["lineCount"] = line_count

            # Get log entries from Indigo server
            log_entries = indigo.server.getEventLogList(**params)

            return log_entries if log_entries else []

        except Exception as e:
            self.logger.debug(f"Error getting event log list: {e}", exc_info=True)
            return []

    # ------------------------------------------------------------------
    # Triggers and schedules
    # ------------------------------------------------------------------

    # IOM trigger class name -> normalized kind
    _TRIGGER_TYPE_MAP = {
        "DeviceStateChangeTrigger": "device_state_change",
        "VariableValueChangeTrigger": "variable_change",
        "PluginEventTrigger": "plugin_event",
        "ServerStartupTrigger": "server_startup",
        "ServerShutdownTrigger": "server_shutdown",
        "EmailReceivedTrigger": "email_received",
        "PowerFailureTrigger": "power_failure",
        "InterfaceFailureTrigger": "interface_failure",
        "InterfaceInitializedTrigger": "interface_initialized",
        "InsteonCommandReceivedTrigger": "insteon_command_received",
        "X10CommandReceivedTrigger": "x10_command_received",
    }

    @staticmethod
    def _enum_label(value) -> Optional[str]:
        """'BecomesEqual' -> 'becomes_equal'; None passes through."""
        if value is None:
            return None
        name = str(value).rsplit(".", 1)[-1]
        out = []
        for i, ch in enumerate(name):
            if ch.isupper() and i > 0:
                out.append("_")
            out.append(ch.lower())
        return "".join(out)

    @staticmethod
    def _iso_or_none(value) -> Optional[str]:
        """datetime -> ISO string; Indigo's year-1 'unset' sentinel -> None."""
        if value is None or getattr(value, "year", None) in (None, 1):
            return None
        return value.isoformat()

    def _folder_name_map(self, collection) -> Dict[int, str]:
        folder_map: Dict[int, str] = {}
        try:
            for folder in collection.folders:
                folder_map[folder.id] = folder.name
        except Exception as e:
            self.logger.debug(f"Error building folder map: {e}", exc_info=True)
        return folder_map

    def _with_folder_name(self, entry: Dict[str, Any], collection) -> Dict[str, Any]:
        """Add folderName to a single-object record in a folder (the list
        methods do this with one folder map for the whole collection)."""
        folder_id = entry.get("folderId")
        if folder_id:
            entry["folderName"] = self._folder_name_map(collection).get(
                folder_id, f"Unknown Folder ({folder_id})"
            )
        return entry

    def _trigger_to_dict(self, trigger, include_props: bool = False) -> Dict[str, Any]:
        """Build a plain dict from a typed IOM trigger object. dict(trigger)
        only carries base fields, so the event spec is read via getattr."""
        result = {
            "id": trigger.id,
            "name": trigger.name,
            "description": trigger.description,
            "enabled": trigger.enabled,
            "folderId": trigger.folderId,
            "tags": self._tags_of(trigger),
            "type": self._TRIGGER_TYPE_MAP.get(
                type(trigger).__name__, self._enum_label(type(trigger).__name__)
            ),
        }

        if hasattr(trigger, "deviceId"):
            result["deviceId"] = trigger.deviceId
            result["stateSelector"] = getattr(trigger, "stateSelector", None)
            result["stateChangeType"] = self._enum_label(getattr(trigger, "stateChangeType", None))
            result["stateValue"] = getattr(trigger, "stateValue", None)
        if hasattr(trigger, "variableId"):
            result["variableId"] = trigger.variableId
            result["variableChangeType"] = self._enum_label(getattr(trigger, "variableChangeType", None))
            result["variableValue"] = getattr(trigger, "variableValue", None)
        if hasattr(trigger, "pluginId"):
            result["pluginId"] = trigger.pluginId
            result["pluginTypeId"] = getattr(trigger, "pluginTypeId", None)
            if include_props:
                try:
                    result["pluginProps"] = self._to_plain(trigger.pluginProps)
                except Exception:
                    result["pluginProps"] = None

        return result

    def _schedule_to_dict(self, schedule) -> Dict[str, Any]:
        result = {
            "id": schedule.id,
            "name": schedule.name,
            "description": schedule.description,
            "enabled": schedule.enabled,
            "folderId": schedule.folderId,
            "tags": self._tags_of(schedule),
            "type": "schedule",
            "date_type": self._enum_label(getattr(schedule, "dateType", None)),
            "time_type": self._enum_label(getattr(schedule, "timeType", None)),
            "sun_delta_seconds": getattr(schedule, "sunDelta", None),
            "randomize_by_seconds": getattr(schedule, "randomizeBy", None),
            "auto_delete": getattr(schedule, "autoDelete", None),
            "next_execution": self._iso_or_none(getattr(schedule, "nextExecution", None)),
        }
        # absoluteTime is a datetime on a year-2000 base date; the year-1
        # sentinel means "unset" (non-absolute time types).
        absolute_time = getattr(schedule, "absoluteTime", None)
        result["absolute_time"] = (
            absolute_time.strftime("%H:%M:%S")
            if absolute_time is not None and absolute_time.year != 1
            else None
        )
        result["absolute_date"] = self._iso_or_none(getattr(schedule, "absoluteDate", None))
        return result

    @classmethod
    def _to_plain(cls, value) -> Any:
        """Recursively convert indigo.Dict/indigo.List containers to plain
        Python structures so they serialize to JSON."""
        try:
            keys = list(value.keys())
        except AttributeError:
            keys = None
        if keys is not None:
            return {key: cls._to_plain(value[key]) for key in keys}
        if isinstance(value, (list, tuple)) or type(value).__name__ == "List":
            return [cls._to_plain(item) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    def get_all_triggers(self) -> List[Dict[str, Any]]:
        """
        Get all triggers from Indigo with normalized event-spec fields.
        """
        triggers = []
        try:
            folder_map = self._folder_name_map(indigo.triggers)
            for trigger in indigo.triggers.iter():
                entry = self._trigger_to_dict(trigger)
                if entry["folderId"]:
                    entry["folderName"] = folder_map.get(
                        entry["folderId"], f"Unknown Folder ({entry['folderId']})"
                    )
                triggers.append(entry)
        except Exception as e:
            self.logger.debug(f"Error getting all triggers: {e}", exc_info=True)

        return triggers

    def get_trigger(self, trigger_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a specific trigger by ID, including plugin props for plugin-event
        triggers.
        """
        try:
            if trigger_id in indigo.triggers:
                entry = self._trigger_to_dict(indigo.triggers[trigger_id], include_props=True)
                return self._with_folder_name(entry, indigo.triggers)
        except Exception as e:
            self.logger.debug(f"Error getting trigger {trigger_id}: {e}", exc_info=True)

        return None

    def get_all_schedules(self) -> List[Dict[str, Any]]:
        """
        Get all schedules from Indigo including next execution times.
        """
        schedules = []
        try:
            folder_map = self._folder_name_map(indigo.schedules)
            for schedule in indigo.schedules.iter():
                entry = self._schedule_to_dict(schedule)
                if entry["folderId"]:
                    entry["folderName"] = folder_map.get(
                        entry["folderId"], f"Unknown Folder ({entry['folderId']})"
                    )
                schedules.append(entry)
        except Exception as e:
            self.logger.debug(f"Error getting all schedules: {e}", exc_info=True)

        return schedules

    def get_schedule(self, schedule_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a specific schedule by ID.
        """
        try:
            if schedule_id in indigo.schedules:
                entry = self._schedule_to_dict(indigo.schedules[schedule_id])
                return self._with_folder_name(entry, indigo.schedules)
        except Exception as e:
            self.logger.debug(f"Error getting schedule {schedule_id}: {e}", exc_info=True)

        return None

    # Namespaces whose getDependencies command serves each entity type.
    _DEPENDENCY_NAMESPACES = {
        "device": "device",
        "variable": "variable",
        "action_group": "actionGroup",
        "trigger": "trigger",
        "schedule": "schedule",
    }

    def get_dependencies(self, entity_type: str, entity_id: int) -> Dict[str, Any]:
        """
        Get the server-computed reverse dependency graph for an element.
        Slow on the server side — never call in a loop.
        """
        namespace_name = self._DEPENDENCY_NAMESPACES.get(entity_type)
        if namespace_name is None:
            return {"error": f"Unsupported entity_type: {entity_type}"}
        try:
            namespace = getattr(indigo, namespace_name)
            deps = namespace.getDependencies(entity_id)
            result: Dict[str, Any] = {}
            for indigo_key, out_key in (
                ("triggers", "triggers"),
                ("schedules", "schedules"),
                ("actionGroups", "action_groups"),
                ("devices", "devices"),
                ("variables", "variables"),
                ("controlPages", "control_pages"),
            ):
                entries = []
                try:
                    for item in deps[indigo_key]:
                        entries.append({"id": item["ID"], "name": item["Name"]})
                except Exception:
                    pass
                result[out_key] = entries
            return result
        except Exception as e:
            self.logger.debug(
                f"Error getting dependencies for {entity_type} {entity_id}: {e}", exc_info=True
            )
            return {"error": str(e)}

    # Command namespaces per automation entity type.
    _AUTOMATION_NAMESPACES = {
        "trigger": "trigger",
        "schedule": "schedule",
        "action_group": "actionGroup",
    }

    def automation_command(
        self,
        entity_type: str,
        entity_id: int,
        command: str,
        value: Optional[bool] = None,
        delay: Optional[int] = None,
        duration: Optional[int] = None,
        duplicate_name: Optional[str] = None,
        folder_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Run a lifecycle command against a trigger, schedule, or action group.
        """
        namespace_name = self._AUTOMATION_NAMESPACES.get(entity_type)
        if namespace_name is None:
            return {"error": f"Unsupported entity_type: {entity_type}"}
        try:
            namespace = getattr(indigo, namespace_name)
            result: Dict[str, Any] = {
                "success": True,
                "entity_type": entity_type,
                "id": entity_id,
                "command": command,
            }

            if command == "enable":
                kwargs = {"value": bool(value)}
                if delay:
                    kwargs["delay"] = int(delay)
                if duration:
                    kwargs["duration"] = int(duration)
                namespace.enable(entity_id, **kwargs)
                result["enabled"] = bool(value)
                if duration:
                    result["auto_reverts_after_seconds"] = int(duration)
            elif command == "duplicate":
                if duplicate_name:
                    duplicate = namespace.duplicate(entity_id, duplicateName=duplicate_name)
                else:
                    duplicate = namespace.duplicate(entity_id)
                result["new_id"] = duplicate.id
                result["new_name"] = duplicate.name
            elif command == "move_to_folder":
                namespace.moveToFolder(entity_id, value=int(folder_id or 0))
                result["folder_id"] = int(folder_id or 0)
            elif command == "remove_delayed_actions":
                namespace.removeDelayedActions(entity_id)
            elif command == "delete":
                namespace.delete(entity_id)
            else:
                return {"error": f"Unsupported command: {command}"}

            return result
        except Exception as e:
            self.logger.debug(
                f"Error running {command} on {entity_type} {entity_id}: {e}", exc_info=True
            )
            return {"error": str(e), "success": False}

    # Editable-field maps: normalized field name -> IOM attribute, with an
    # optional enum class name for values that need conversion. enabled and
    # folderId are deliberately absent (the enable / moveToFolder commands
    # handle those).
    _TRIGGER_EDIT_ATTRS = {
        "name": ("name", None),
        "description": ("description", None),
        "device_id": ("deviceId", None),
        "state_selector": ("stateSelector", None),
        "state_selector_index": ("stateSelectorIndex", None),
        "state_change_type": ("stateChangeType", "kStateChange"),
        "state_value": ("stateValue", None),
        "variable_id": ("variableId", None),
        "variable_change_type": ("variableChangeType", "kVarChange"),
        "variable_value": ("variableValue", None),
    }
    # Schedule timing attributes (dateType, timeType, absoluteTime, sunDelta,
    # randomizeBy, autoDelete) are READ-ONLY on IOM Schedule instances —
    # verified live on Indigo 2025.2 ("the attribute X is read-only on this
    # instance"). Only identity fields can be edited.
    _SCHEDULE_EDIT_ATTRS = {
        "name": ("name", None),
        "description": ("description", None),
    }
    _ACTION_GROUP_EDIT_ATTRS = {
        "name": ("name", None),
        "description": ("description", None),
    }
    _EDIT_ATTRS_BY_TYPE = {
        "trigger": _TRIGGER_EDIT_ATTRS,
        "schedule": _SCHEDULE_EDIT_ATTRS,
        "action_group": _ACTION_GROUP_EDIT_ATTRS,
    }

    @staticmethod
    def _to_indigo_enum(enum_name: str, value: str):
        """'becomes_true' -> indigo.kStateChange.BecomesTrue (etc.)."""
        enum_cls = getattr(indigo, enum_name)
        camel = "".join(part.capitalize() for part in str(value).split("_"))
        if not hasattr(enum_cls, camel):
            valid = [n for n in dir(enum_cls) if n[0].isupper()]
            raise ValueError(f"Invalid {enum_name} value {value!r}; valid: {valid}")
        return getattr(enum_cls, camel)

    def _snapshot_fields(self, elem, entity_type: str, field_names) -> Dict[str, Any]:
        attr_map = self._EDIT_ATTRS_BY_TYPE[entity_type]
        snapshot = {}
        for field in field_names:
            attr, enum_name = attr_map[field]
            value = getattr(elem, attr, None)
            if enum_name is not None:
                value = self._enum_label(value)
            snapshot[field] = value
        return snapshot

    def update_automation_fields(
        self, entity_type: str, entity_id: int, fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update whitelisted basic fields via replaceOnServer().
        """
        collections = {
            "trigger": "triggers",
            "schedule": "schedules",
            "action_group": "actionGroups",
        }
        collection_name = collections.get(entity_type)
        attr_map = self._EDIT_ATTRS_BY_TYPE.get(entity_type)
        if collection_name is None or attr_map is None:
            return {"error": f"Unsupported entity_type: {entity_type}"}

        unknown = [f for f in fields if f not in attr_map]
        if unknown:
            return {
                "error": f"Field(s) not editable for {entity_type}: {unknown}. "
                f"Editable: {sorted(attr_map)}"
            }
        if not fields:
            return {"error": "No fields provided"}

        try:
            collection = getattr(indigo, collection_name)
            if entity_id not in collection:
                return {"error": f"{entity_type} {entity_id} not found"}
            elem = collection[entity_id]

            before = self._snapshot_fields(elem, entity_type, fields.keys())

            for field, value in fields.items():
                attr, enum_name = attr_map[field]
                if enum_name is not None:
                    value = self._to_indigo_enum(enum_name, value)
                setattr(elem, attr, value)

            elem.replaceOnServer()

            refreshed = collection[entity_id]
            after = self._snapshot_fields(refreshed, entity_type, fields.keys())

            not_applied = {
                field: fields[field]
                for field in fields
                if before.get(field) == after.get(field)
                and str(fields[field]) != str(before.get(field))
            }
            result = {
                "success": True,
                "entity_type": entity_type,
                "id": entity_id,
                "before": before,
                "after": after,
            }
            if not_applied:
                result["warning"] = (
                    f"Some fields did not change on the server: {sorted(not_applied)}"
                )
            return result
        except Exception as e:
            self.logger.debug(
                f"Error updating {entity_type} {entity_id}: {e}", exc_info=True
            )
            return {"error": str(e), "success": False}

    # ------------------------------------------------------------------
    # Tags (Indigo 2026.1, API 3.9)
    # ------------------------------------------------------------------

    # object type -> (collection attribute, command namespace attribute)
    _TAG_NAMESPACES = {
        "device": ("devices", "device"),
        "variable": ("variables", "variable"),
        "trigger": ("triggers", "trigger"),
        "schedule": ("schedules", "schedule"),
        "action_group": ("actionGroups", "actionGroup"),
        "control_page": ("controlPages", "controlPage"),
    }

    @staticmethod
    def _tags_of(elem) -> List[str]:
        """An IOM object's tags as a plain list (indigo.List otherwise)."""
        return [str(tag) for tag in (getattr(elem, "tags", None) or [])]

    def _tag_object(self, object_type: str, object_id: int):
        collection_attr, _ = self._TAG_NAMESPACES[object_type]
        collection = getattr(indigo, collection_attr)
        if object_id not in collection:
            return None
        return collection[object_id]

    def get_tag_library(self) -> Dict[str, Dict[str, str]]:
        return {
            str(name): {key: str(value) for key, value in dict(record).items()}
            for name, record in dict(indigo.server.tags).items()
        }

    def create_tag(self, name: str, color: str) -> Dict[str, Any]:
        try:
            indigo.server.create_tag(name, color)
            return {"success": True}
        except Exception as e:
            return {"error": str(e), "success": False}

    def update_tag(
        self, name: str, new_name: Optional[str] = None, new_color: Optional[str] = None
    ) -> Dict[str, Any]:
        kwargs = {}
        if new_name is not None:
            kwargs["new_tag"] = new_name
        if new_color is not None:
            kwargs["new_color"] = new_color
        try:
            indigo.server.update_tag(name, **kwargs)
            return {"success": True}
        except Exception as e:
            return {"error": str(e), "success": False}

    def delete_tag(self, name: str) -> Dict[str, Any]:
        try:
            indigo.server.delete_tag(name)
            return {"success": True}
        except Exception as e:
            return {"error": str(e), "success": False}

    def get_object_tags(self, object_type: str, object_id: int) -> Optional[List[str]]:
        if object_type not in self._TAG_NAMESPACES:
            return None
        try:
            elem = self._tag_object(object_type, int(object_id))
        except Exception as e:
            self.logger.debug(f"Error reading tags of {object_type} {object_id}: {e}", exc_info=True)
            return None
        return None if elem is None else self._tags_of(elem)

    def get_object_name(self, object_type: str, object_id: int) -> Optional[str]:
        if object_type not in self._TAG_NAMESPACES:
            return None
        try:
            elem = self._tag_object(object_type, int(object_id))
        except Exception:
            return None
        return None if elem is None else elem.name

    def _object_tag_command(self, command: str, object_type: str, object_id: int, tag: str) -> Dict[str, Any]:
        if object_type not in self._TAG_NAMESPACES:
            return {"error": f"Unsupported object type: {object_type}", "success": False}
        try:
            namespace = getattr(indigo, self._TAG_NAMESPACES[object_type][1])
            getattr(namespace, command)(int(object_id), tag)
            return {"success": True}
        except Exception as e:
            return {"error": str(e), "success": False}

    def add_object_tag(self, object_type: str, object_id: int, tag: str) -> Dict[str, Any]:
        return self._object_tag_command("add_tag", object_type, object_id, tag)

    def remove_object_tag(self, object_type: str, object_id: int, tag: str) -> Dict[str, Any]:
        return self._object_tag_command("remove_tag", object_type, object_id, tag)

    def find_objects_with_tag(self, tag: str) -> List[Dict[str, Any]]:
        found = []
        for object_type, (collection_attr, _) in self._TAG_NAMESPACES.items():
            try:
                for elem in getattr(indigo, collection_attr):
                    if tag in self._tags_of(elem):
                        found.append({"type": object_type, "id": elem.id, "name": elem.name})
            except Exception as e:
                self.logger.debug(f"Error scanning {collection_attr} for tag {tag}: {e}", exc_info=True)
        return found

    def get_db_file_path(self) -> Optional[str]:
        """
        Get the filesystem path of Indigo's active database file.
        """
        try:
            return indigo.server.getDbFilePath()
        except Exception as e:
            self.logger.debug(f"Error getting db file path: {e}", exc_info=True)
            return None

    def get_logs_folder_path(self) -> Optional[str]:
        """
        Get the filesystem path of Indigo's Logs folder.
        """
        try:
            return indigo.server.getLogsFolderPath()
        except Exception as e:
            self.logger.debug(f"Error getting logs folder path: {e}", exc_info=True)
            return None
