"""
Tag authoring tools for Indigo 2026.1: manage_tags (the server-wide tag
library) and tag_objects (put a tag on, or take it off, objects of any type).

Indigo's built-in MCP Control only reads tags (list_tags, the tag filter on
its list_* tools); creating, editing and assigning them is what this adds.
Everything goes through the documented IOM calls (indigo.server.create_tag /
update_tag / delete_tag, indigo.<type>.add_tag / remove_tag) via the data
provider.
"""

import logging
from typing import Any, Callable, Dict, List, Optional

from ...adapters.data_provider import DataProvider
from ..base_handler import BaseToolHandler
from .tag_rules import (
    OBJECT_TYPES,
    confirm_challenge,
    is_valid_tag_name,
    normalize_color,
    tag_name_error,
)

MANAGE_ACTIONS = ("create", "update", "delete")
TAG_OBJECT_ACTIONS = ("add", "remove")

# Objects per tag_objects call, and how many removals go through without confirm
MAX_OBJECTS_PER_CALL = 200
BULK_REMOVE_CONFIRM_THRESHOLD = 25

# Objects listed in a delete confirmation challenge
SAMPLE_SIZE = 20


class TagHandler(BaseToolHandler):
    """Handler for manage_tags and tag_objects."""

    def __init__(
        self,
        data_provider: DataProvider,
        logger: Optional[logging.Logger] = None,
        delete_enabled_supplier: Optional[Callable[[], bool]] = None,
        confirm_tag_supplier: Optional[Callable[[], str]] = None,
    ):
        super().__init__(tool_name="tags", logger=logger)
        self.data_provider = data_provider
        self.delete_enabled_supplier = delete_enabled_supplier or (lambda: False)
        self.confirm_tag_supplier = confirm_tag_supplier or (lambda: "")

    def _gate_tag(self) -> str:
        tag = (self.confirm_tag_supplier() or "").strip()
        return tag if is_valid_tag_name(tag) else ""

    # ------------------------------------------------------------------
    # manage_tags
    # ------------------------------------------------------------------

    def manage_tags(
        self,
        action: str,
        tag: str,
        new_tag: Optional[str] = None,
        color: Optional[str] = None,
        confirm: bool = False,
    ) -> Dict[str, Any]:
        try:
            if action not in MANAGE_ACTIONS:
                return {
                    "error": f"Invalid action {action!r}. Valid actions: {', '.join(MANAGE_ACTIONS)}",
                    "success": False,
                }
            if action == "create":
                return self._create(tag, color)
            if action == "update":
                return self._update(tag, new_tag, color, confirm)
            return self._delete(tag, confirm)
        except Exception as e:
            return self.handle_exception(e, f"{action} tag {tag!r}")

    def _create(self, tag: str, color: Optional[str]) -> Dict[str, Any]:
        error = tag_name_error(tag)
        if error:
            return {"error": error, "success": False}
        normalized = normalize_color(color)
        if normalized is None:
            return {
                "error": f"create needs color: six hex digits such as '4A90D9' (a leading # is fine), not {color!r}",
                "success": False,
            }
        if tag in self.data_provider.get_tag_library():
            return {"error": f"Tag '{tag}' already exists", "success": False}

        result = self.data_provider.create_tag(tag, normalized)
        if result.get("error"):
            self.error_log(f"create tag '{tag}' failed: {result['error']}")
            return result
        record = self.data_provider.get_tag_library().get(tag)
        self.activity_log(f"tag '{tag}' created (#{normalized})")
        return {"success": True, "action": "create", "tag": tag, "record": record}

    def _update(
        self, tag: str, new_tag: Optional[str], color: Optional[str], confirm: bool
    ) -> Dict[str, Any]:
        library = self.data_provider.get_tag_library()
        if tag not in library:
            return _unknown_tag(tag)
        if new_tag is None and color is None:
            return {"error": "update needs new_tag, color, or both", "success": False}
        if new_tag is not None:
            error = tag_name_error(new_tag)
            if error:
                return {"error": error, "success": False}
            if new_tag != tag and new_tag in library:
                return {"error": f"Tag '{new_tag}' already exists", "success": False}
        normalized = None
        if color is not None:
            normalized = normalize_color(color)
            if normalized is None:
                return {
                    "error": f"color must be six hex digits such as '4A90D9', not {color!r}",
                    "success": False,
                }

        renaming = new_tag is not None and new_tag != tag
        carriers = self.data_provider.find_objects_with_tag(tag) if renaming else []
        gate_tag = self._gate_tag()
        if renaming and tag == gate_tag and not confirm:
            # The gate follows the configured name, so a rename turns it off
            return confirm_challenge(
                gate_tag, carriers or [{"type": "tag", "id": tag, "name": tag}],
                f"rename the '{tag}' tag to '{new_tag}', which stops the confirmation gate "
                f"until the plugin's confirmation tag preference is changed to match",
            )

        result = self.data_provider.update_tag(tag, new_name=new_tag, new_color=normalized)
        if result.get("error"):
            self.error_log(f"update tag '{tag}' failed: {result['error']}")
            return result
        final_name = new_tag or tag
        after = self.data_provider.get_tag_library().get(final_name)
        changes = []
        if renaming:
            changes.append(f"renamed to '{new_tag}' on {len(carriers)} objects")
        if normalized is not None:
            changes.append(f"recolored #{library[tag].get('color')} -> #{normalized}")
        self.activity_log(f"tag '{tag}' {', '.join(changes) or 'unchanged'}")
        response = {
            "success": True,
            "action": "update",
            "tag": final_name,
            "before": {"tag": tag, **library[tag]},
            "after": {"tag": final_name, **(after or {})},
        }
        if renaming:
            response["objects_affected"] = len(carriers)
        return response

    def _delete(self, tag: str, confirm: bool) -> Dict[str, Any]:
        if tag not in self.data_provider.get_tag_library():
            return _unknown_tag(tag)
        if not self.delete_enabled_supplier():
            return {
                "error": "Deleting tags via MCP is disabled. Enable 'Allow AI to delete tags' "
                "in the MCP Advanced Tools plugin preferences to permit it.",
                "success": False,
            }
        carriers = self.data_provider.find_objects_with_tag(tag)
        if not confirm:
            return {
                "success": False,
                "requires_confirmation": True,
                "objects_affected": len(carriers),
                "objects": carriers[:SAMPLE_SIZE],
                "error": (
                    f"Deleting tag '{tag}' removes it from all {len(carriers)} objects "
                    f"carrying it and cannot be undone. Call again with confirm=true only if "
                    f"the user asked for this deletion."
                ),
            }
        result = self.data_provider.delete_tag(tag)
        if result.get("error"):
            self.error_log(f"delete tag '{tag}' failed: {result['error']}")
            return result
        self.activity_log(f"tag '{tag}' deleted (was on {len(carriers)} objects)")
        return {
            "success": True,
            "action": "delete",
            "tag": tag,
            "removed_from": len(carriers),
            "objects": carriers[:SAMPLE_SIZE],
        }

    # ------------------------------------------------------------------
    # tag_objects
    # ------------------------------------------------------------------

    def tag_objects(
        self,
        tag: str,
        action: str,
        objects: List[Dict[str, Any]],
        dry_run: bool = False,
        confirm: bool = False,
    ) -> Dict[str, Any]:
        try:
            if action not in TAG_OBJECT_ACTIONS:
                return {
                    "error": f"Invalid action {action!r}. Valid actions: add, remove",
                    "success": False,
                }
            error = tag_name_error(tag)
            if error:
                return {"error": error, "success": False}
            if tag not in self.data_provider.get_tag_library():
                return _unknown_tag(tag)

            targets, error = _parse_objects(objects)
            if error:
                return {"error": error, "success": False}

            # Plan every object first: nothing is written until the gates pass
            plan: List[Dict[str, Any]] = []
            for object_type, object_id in targets:
                entry = {"type": object_type, "id": object_id}
                current = self.data_provider.get_object_tags(object_type, object_id)
                if current is None:
                    entry["outcome"] = "not_found"
                    plan.append(entry)
                    continue
                entry["name"] = self.data_provider.get_object_name(object_type, object_id)
                has_tag = tag in current
                if action == "add":
                    entry["outcome"] = "already" if has_tag else "add"
                else:
                    entry["outcome"] = "remove" if has_tag else "not_present"
                plan.append(entry)

            changing = [e for e in plan if e["outcome"] in ("add", "remove")]
            if not dry_run and not confirm:
                gate_tag = self._gate_tag()
                if action == "remove" and tag == gate_tag and changing:
                    return confirm_challenge(
                        gate_tag,
                        [{k: e[k] for k in ("type", "id", "name")} for e in changing],
                        f"remove the '{tag}' tag from {len(changing)} objects",
                    )
                if action == "remove" and len(changing) > BULK_REMOVE_CONFIRM_THRESHOLD:
                    return {
                        "success": False,
                        "requires_confirmation": True,
                        "objects_affected": len(changing),
                        "error": (
                            f"Removing '{tag}' from {len(changing)} objects (more than "
                            f"{BULK_REMOVE_CONFIRM_THRESHOLD}) needs confirm=true. Use dry_run=true "
                            f"to see the list first."
                        ),
                    }

            results = []
            for entry in plan:
                outcome = entry["outcome"]
                if outcome in ("add", "remove"):
                    if dry_run:
                        entry["outcome"] = f"would_{outcome}"
                    else:
                        call = (
                            self.data_provider.add_object_tag
                            if outcome == "add"
                            else self.data_provider.remove_object_tag
                        )
                        result = call(entry["type"], entry["id"], tag)
                        if result.get("error"):
                            entry["outcome"] = "error"
                            entry["error"] = result["error"]
                        else:
                            entry["outcome"] = "added" if outcome == "add" else "removed"
                results.append(entry)

            counts: Dict[str, int] = {}
            for entry in results:
                counts[entry["outcome"]] = counts.get(entry["outcome"], 0) + 1
            if not dry_run:
                done = counts.get("added", 0) + counts.get("removed", 0)
                verb = "added to" if action == "add" else "removed from"
                summary = f"tag '{tag}' {verb} {done} objects"
                if counts.get("error"):
                    summary += f", {counts['error']} errors"
                self.activity_log(summary)
            return {
                "success": not counts.get("error"),
                "tag": tag,
                "action": action,
                "dry_run": bool(dry_run),
                "counts": counts,
                "results": results,
            }
        except Exception as e:
            return self.handle_exception(e, f"{action} tag {tag!r} on objects")


def _unknown_tag(tag: str) -> Dict[str, Any]:
    return {
        "error": f"Tag '{tag}' is not in the tag library. Create it with manage_tags "
        f"(action=create) first, or check the names with MCP Control's list_tags.",
        "success": False,
    }


def _parse_objects(objects: Any):
    """[{type, id}] -> ([(type, id)], error). Duplicates are dropped."""
    if not isinstance(objects, list) or not objects:
        return [], "objects must be a non-empty list of {type, id}"
    if len(objects) > MAX_OBJECTS_PER_CALL:
        return [], f"At most {MAX_OBJECTS_PER_CALL} objects per call (got {len(objects)})"
    targets = []
    for item in objects:
        if not isinstance(item, dict):
            return [], f"Each object must be {{type, id}}, not {item!r}"
        object_type = item.get("type")
        if object_type not in OBJECT_TYPES:
            return [], f"Invalid object type {object_type!r}. Valid types: {', '.join(OBJECT_TYPES)}"
        try:
            object_id = int(item.get("id"))
        except (TypeError, ValueError):
            return [], f"Invalid object id {item.get('id')!r}"
        if (object_type, object_id) not in targets:
            targets.append((object_type, object_id))
    return targets, None
