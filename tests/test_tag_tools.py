"""
Tests for Indigo 2026.1 tag support: the tag rules, the data provider's IOM
tag calls (fake `indigo`), manage_tags / tag_objects, the confirmation-tag gate
on control_* / update_*, the tag filters on list_triggers / list_schedules, and
tags in get_*_details.
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

plugin_path = Path(__file__).parent.parent / "MCP Advanced Tools.indigoPlugin/Contents/Server Plugin"
sys.path.insert(0, str(plugin_path))

import mcp_server.adapters.indigo_data_provider as idp_module  # noqa: E402
from mcp_server.adapters.indigo_data_provider import IndigoDataProvider  # noqa: E402
from mcp_server.tool_registry import WRITE_TOOLS, get_tool_schemas  # noqa: E402
from mcp_server.tools.automation.automation_handler import AutomationHandler  # noqa: E402
from mcp_server.tools.tags.tag_handler import (  # noqa: E402
    BULK_REMOVE_CONFIRM_THRESHOLD,
    MAX_OBJECTS_PER_CALL,
    TagHandler,
)
from mcp_server.tools.tags.tag_rules import (  # noqa: E402
    matches_tags,
    normalize_color,
    normalize_tag_filter,
    tag_name_error,
)


# ----------------------------------------------------------------------
# Rules


@pytest.mark.parametrize("name", ["kitchen", "holiday-lighting", "a-b-c"])
def test_valid_tag_names(name):
    assert tag_name_error(name) is None


@pytest.mark.parametrize("name", ["Kitchen", "kitchen1", "-kitchen", "kitchen-", "a--b", "a b", "", None, 5])
def test_invalid_tag_names(name):
    assert tag_name_error(name)


@pytest.mark.parametrize(
    "color,expected",
    [("4A90D9", "4A90D9"), ("#4a90d9", "4A90D9"), (" ff8800 ", "FF8800"),
     ("fff", None), ("#GG0000", None), ("4A90D9FF", None), (None, None)],
)
def test_normalize_color(color, expected):
    assert normalize_color(color) == expected


def test_normalize_tag_filter():
    assert normalize_tag_filter(None) == ([], "all", None)
    assert normalize_tag_filter("kitchen") == (["kitchen"], "all", None)
    assert normalize_tag_filter(["a", "b", "a"], "any") == (["a", "b"], "any", None)
    assert normalize_tag_filter(["Kitchen"])[2]
    assert normalize_tag_filter(["a"], "some")[2]
    assert normalize_tag_filter(5)[2]


def test_matches_tags():
    assert matches_tags(["a", "b"], ["a", "b"])
    assert not matches_tags(["a"], ["a", "b"])
    assert matches_tags(["a"], ["a", "b"], "any")
    assert not matches_tags([], ["a"], "any")
    assert matches_tags(None, [])


# ----------------------------------------------------------------------
# Data provider over a fake IOM


class _Obj(SimpleNamespace):
    pass


class _Coll(dict):
    """indigo.devices-like: `in`, [id], iteration over objects."""

    def __iter__(self):
        return iter(list(self.values()))


class _Namespace:
    def __init__(self, coll, library, readonly=()):
        self.coll, self.library, self.readonly = coll, library, set(readonly)

    def add_tag(self, obj_id, tag):
        if tag not in self.library:
            raise ValueError(f"tag {tag} not in library")
        if obj_id in self.readonly:
            raise ValueError("variable is read-only")
        if tag not in self.coll[obj_id].tags:
            self.coll[obj_id].tags.append(tag)

    def remove_tag(self, obj_id, tag):
        if tag in self.coll[obj_id].tags:
            self.coll[obj_id].tags.remove(tag)


def make_fake_indigo():
    library = {}
    fake = SimpleNamespace()
    names = {
        "device": "devices", "variable": "variables", "trigger": "triggers",
        "schedule": "schedules", "actionGroup": "actionGroups", "controlPage": "controlPages",
    }
    for ns, coll in names.items():
        setattr(fake, coll, _Coll())
        setattr(fake, ns, _Namespace(getattr(fake, coll), library, readonly={99} if ns == "variable" else ()))

    def create_tag(name, color):
        if name in library:
            raise ValueError("exists")
        library[name] = {"color": color, "text_color": "111111", "border_color": "222222"}

    def update_tag(name, new_tag=None, new_color=None):
        record = dict(library.pop(name))
        if new_color:
            record["color"] = new_color
        library[new_tag or name] = record
        if new_tag:
            for coll in names.values():
                for obj in getattr(fake, coll).values():
                    obj.tags = [new_tag if t == name else t for t in obj.tags]

    def delete_tag(name):
        del library[name]
        for coll in names.values():
            for obj in getattr(fake, coll).values():
                obj.tags = [t for t in obj.tags if t != name]

    fake.server = type("Server", (), {
        "tags": property(lambda self: {k: dict(v) for k, v in library.items()}),
        "create_tag": staticmethod(create_tag),
        "update_tag": staticmethod(update_tag),
        "delete_tag": staticmethod(delete_tag),
    })()
    fake._library = library
    return fake


@pytest.fixture
def fake_indigo():
    fake = make_fake_indigo()
    fake.devices[1] = _Obj(id=1, name="Bar Pendants", tags=[])
    fake.devices[2] = _Obj(id=2, name="Rack Power", tags=["ask-first"])
    fake.variables[3] = _Obj(id=3, name="alarm_enabled", tags=[])
    fake.variables[99] = _Obj(id=99, name="isDaylight", tags=[])
    fake.triggers[4] = _Obj(id=4, name="Auto lock", tags=["ask-first"])
    fake.actionGroups[5] = _Obj(id=5, name="Bedtime", tags=[])
    fake._library["ask-first"] = {"color": "B71C1C", "text_color": "FFFFFF", "border_color": "000000"}
    with patch.object(idp_module, "indigo", fake, create=True):
        yield fake


@pytest.fixture
def provider(fake_indigo):
    return IndigoDataProvider(logger=Mock())


class TestProviderTagCalls:
    def test_library_and_object_tags(self, provider):
        assert provider.get_tag_library()["ask-first"]["color"] == "B71C1C"
        assert provider.get_object_tags("trigger", 4) == ["ask-first"]
        assert provider.get_object_tags("device", 404) is None
        assert provider.get_object_tags("widget", 1) is None
        assert provider.get_object_name("action_group", 5) == "Bedtime"

    def test_create_update_delete(self, provider, fake_indigo):
        assert provider.create_tag("basement", "546E7A") == {"success": True}
        assert provider.create_tag("basement", "546E7A")["error"]
        provider.add_object_tag("device", 1, "basement")
        assert provider.update_tag("basement", new_name="lower-level") == {"success": True}
        assert fake_indigo.devices[1].tags == ["lower-level"]
        assert provider.delete_tag("lower-level") == {"success": True}
        assert fake_indigo.devices[1].tags == []

    def test_add_remove_dispatch_per_type(self, provider, fake_indigo):
        assert provider.add_object_tag("action_group", 5, "ask-first") == {"success": True}
        assert fake_indigo.actionGroups[5].tags == ["ask-first"]
        assert provider.remove_object_tag("action_group", 5, "ask-first") == {"success": True}
        assert provider.add_object_tag("variable", 99, "ask-first")["error"] == "variable is read-only"
        assert provider.add_object_tag("widget", 1, "ask-first")["error"]

    def test_find_objects_with_tag(self, provider):
        found = provider.find_objects_with_tag("ask-first")
        assert {(f["type"], f["id"]) for f in found} == {("device", 2), ("trigger", 4)}


# ----------------------------------------------------------------------
# manage_tags / tag_objects


def make_tag_handler(provider, delete_enabled=False, gate_tag="ask-first"):
    return TagHandler(
        data_provider=provider,
        logger=Mock(),
        delete_enabled_supplier=lambda: delete_enabled,
        confirm_tag_supplier=lambda: gate_tag,
    )


class TestManageTags:
    def test_create_normalizes_color(self, provider, fake_indigo):
        result = make_tag_handler(provider).manage_tags("create", "basement", color="#546e7a")
        assert result["success"] and result["record"]["color"] == "546E7A"
        assert fake_indigo._library["basement"]["color"] == "546E7A"

    @pytest.mark.parametrize("tag,color", [("Basement", "546E7A"), ("basement", None), ("basement", "blue")])
    def test_create_rejects_bad_input(self, provider, fake_indigo, tag, color):
        result = make_tag_handler(provider).manage_tags("create", tag, color=color)
        assert result["success"] is False
        assert "basement" not in fake_indigo._library

    def test_create_existing_is_an_error(self, provider):
        result = make_tag_handler(provider).manage_tags("create", "ask-first", color="B71C1C")
        assert result["success"] is False and "already exists" in result["error"]

    def test_update_rename_counts_objects(self, provider, fake_indigo):
        provider.create_tag("upstairs", "90A4AE")
        provider.add_object_tag("device", 1, "upstairs")
        result = make_tag_handler(provider).manage_tags("update", "upstairs", new_tag="second-floor")
        assert result["success"] and result["objects_affected"] == 1
        assert result["before"]["tag"] == "upstairs" and result["after"]["tag"] == "second-floor"
        assert fake_indigo.devices[1].tags == ["second-floor"]

    def test_update_recolor_only(self, provider, fake_indigo):
        result = make_tag_handler(provider).manage_tags("update", "ask-first", color="ff0000")
        assert result["success"] and result["after"]["color"] == "FF0000"
        assert "objects_affected" not in result

    def test_update_needs_a_change_and_a_free_name(self, provider):
        handler = make_tag_handler(provider)
        provider.create_tag("upstairs", "90A4AE")
        assert handler.manage_tags("update", "upstairs")["success"] is False
        assert "already exists" in handler.manage_tags("update", "upstairs", new_tag="ask-first")["error"]
        assert "not in the tag library" in handler.manage_tags("update", "nope", color="000000")["error"]

    def test_renaming_the_confirmation_tag_needs_confirm(self, provider, fake_indigo):
        handler = make_tag_handler(provider)
        result = handler.manage_tags("update", "ask-first", new_tag="careful")
        assert result["requires_confirmation"] and "ask-first" in fake_indigo._library
        assert handler.manage_tags("update", "ask-first", new_tag="careful", confirm=True)["success"]
        assert "careful" in fake_indigo._library

    def test_delete_gated_by_pref_then_confirm(self, provider, fake_indigo):
        result = make_tag_handler(provider).manage_tags("delete", "ask-first", confirm=True)
        assert result["success"] is False and "disabled" in result["error"]

        handler = make_tag_handler(provider, delete_enabled=True)
        challenge = handler.manage_tags("delete", "ask-first")
        assert challenge["requires_confirmation"] and challenge["objects_affected"] == 2
        assert "ask-first" in fake_indigo._library

        done = handler.manage_tags("delete", "ask-first", confirm=True)
        assert done["success"] and done["removed_from"] == 2
        assert "ask-first" not in fake_indigo._library
        assert fake_indigo.devices[2].tags == []

    def test_invalid_action(self, provider):
        assert make_tag_handler(provider).manage_tags("list", "x")["success"] is False


def _objs(*pairs):
    return [{"type": t, "id": i} for t, i in pairs]


class TestTagObjects:
    def test_add_outcomes(self, provider, fake_indigo):
        provider.create_tag("basement", "546E7A")
        fake_indigo.devices[2].tags.append("basement")
        result = make_tag_handler(provider).tag_objects(
            "basement", "add",
            _objs(("device", 1), ("device", 2), ("device", 404), ("variable", 99), ("device", 1)),
        )
        outcomes = {(r["type"], r["id"]): r["outcome"] for r in result["results"]}
        assert outcomes == {
            ("device", 1): "added", ("device", 2): "already",
            ("device", 404): "not_found", ("variable", 99): "error",
        }
        assert result["success"] is False  # the read-only variable
        assert result["counts"] == {"added": 1, "already": 1, "not_found": 1, "error": 1}
        assert fake_indigo.devices[1].tags == ["basement"]

    def test_dry_run_writes_nothing(self, provider, fake_indigo):
        provider.create_tag("basement", "546E7A")
        result = make_tag_handler(provider).tag_objects(
            "basement", "add", _objs(("device", 1)), dry_run=True)
        assert result["results"][0]["outcome"] == "would_add"
        assert fake_indigo.devices[1].tags == []

    def test_unknown_tag_is_never_created(self, provider, fake_indigo):
        result = make_tag_handler(provider).tag_objects("basement", "add", _objs(("device", 1)))
        assert result["success"] is False and "not in the tag library" in result["error"]
        assert "basement" not in fake_indigo._library

    @pytest.mark.parametrize("objects", [
        [], "device 1", [{"type": "widget", "id": 1}], [{"type": "device", "id": "x"}],
        [{"type": "device", "id": i} for i in range(MAX_OBJECTS_PER_CALL + 1)],
    ])
    def test_rejects_bad_object_lists(self, provider, objects):
        assert make_tag_handler(provider).tag_objects("ask-first", "add", objects)["success"] is False

    def test_bulk_remove_needs_confirm(self, provider, fake_indigo):
        provider.create_tag("basement", "546E7A")
        for i in range(100, 100 + BULK_REMOVE_CONFIRM_THRESHOLD + 1):
            fake_indigo.devices[i] = _Obj(id=i, name=f"D{i}", tags=["basement"])
        objects = _objs(*[("device", i) for i in range(100, 100 + BULK_REMOVE_CONFIRM_THRESHOLD + 1)])
        handler = make_tag_handler(provider)
        assert handler.tag_objects("basement", "remove", objects)["requires_confirmation"]
        assert fake_indigo.devices[100].tags == ["basement"]
        assert handler.tag_objects("basement", "remove", objects, dry_run=True)["counts"] == {
            "would_remove": BULK_REMOVE_CONFIRM_THRESHOLD + 1}
        done = handler.tag_objects("basement", "remove", objects, confirm=True)
        assert done["counts"] == {"removed": BULK_REMOVE_CONFIRM_THRESHOLD + 1}

    def test_removing_the_confirmation_tag_needs_confirm(self, provider, fake_indigo):
        handler = make_tag_handler(provider)
        challenge = handler.tag_objects("ask-first", "remove", _objs(("trigger", 4)))
        assert challenge["requires_confirmation"] and fake_indigo.triggers[4].tags == ["ask-first"]
        assert challenge["objects"][0]["name"] == "Auto lock"
        assert handler.tag_objects("ask-first", "remove", _objs(("trigger", 4)), confirm=True)["success"]
        assert fake_indigo.triggers[4].tags == []

    def test_gate_off_when_no_confirmation_tag(self, provider, fake_indigo):
        handler = make_tag_handler(provider, gate_tag="")
        assert handler.tag_objects("ask-first", "remove", _objs(("trigger", 4)))["success"]


# ----------------------------------------------------------------------
# Confirmation gate and tag filters on the automation tools


@pytest.fixture
def automation(fake_indigo, provider):
    provider.get_all_triggers = Mock(return_value=[
        {"id": 4, "name": "Auto lock", "type": "server_startup", "tags": ["ask-first", "security"]},
        {"id": 6, "name": "Auto lights", "type": "server_startup", "tags": ["lighting"]},
        {"id": 7, "name": "Untagged", "type": "server_startup"},
    ])
    provider.get_all_schedules = Mock(return_value=[
        {"id": 8, "name": "Night", "tags": ["security"], "next_execution": None},
        {"id": 9, "name": "Day", "tags": [], "next_execution": None},
    ])
    provider.automation_command = Mock(return_value={"success": True})
    provider.update_automation_fields = Mock(return_value={"success": True, "before": {}, "after": {}})
    store = Mock()
    store.lookup_name.return_value = "Auto lock"
    return AutomationHandler(
        data_provider=provider, structure_store=store, logger=Mock(),
        confirm_tag_supplier=lambda: "ask-first",
    )


class TestConfirmationGate:
    def test_control_on_tagged_trigger_challenges(self, automation, provider):
        result = automation.control("trigger", 4, "disable")
        assert result["requires_confirmation"] and "ask-first" in result["error"]
        provider.automation_command.assert_not_called()
        assert automation.control("trigger", 4, "disable", confirm=True)["success"]
        provider.automation_command.assert_called_once()

    def test_untagged_element_needs_no_confirm(self, automation, provider):
        assert automation.control("action_group", 5, "duplicate")["success"]

    def test_update_on_tagged_trigger_challenges(self, automation, provider):
        result = automation.update("trigger", 4, {"name": "x"})
        assert result["requires_confirmation"]
        provider.update_automation_fields.assert_not_called()
        assert automation.update("trigger", 4, {"name": "x"}, confirm=True)["success"]

    def test_gate_off(self, automation, provider):
        automation.confirm_tag_supplier = lambda: ""
        assert automation.control("trigger", 4, "disable")["success"]


class TestListTagFilters:
    def test_triggers_all_and_any(self, automation):
        names = lambda r: [t["name"] for t in r["triggers"]]  # noqa: E731
        assert names(automation.list_triggers(tags=["security"])) == ["Auto lock"]
        assert names(automation.list_triggers(tags=["security", "lighting"])) == []
        assert names(automation.list_triggers(tags=["security", "lighting"], tag_match="any")) == [
            "Auto lights", "Auto lock"]
        assert automation.list_triggers()["total_count"] == 3

    def test_schedules_and_bad_filter(self, automation):
        assert [s["name"] for s in automation.list_schedules(tags="security")["schedules"]] == ["Night"]
        assert automation.list_schedules(tags=["Security"])["success"] is False


class TestProviderRecordsCarryTags:
    def test_trigger_schedule_records_and_folder_names(self, fake_indigo, provider):
        trigger = type("ServerStartupTrigger", (), {})()
        trigger.__dict__.update(id=4, name="Auto lock", description="", enabled=True, folderId=70,
                                tags=["ask-first"])
        folder = SimpleNamespace(id=70, name="Security")
        fake_indigo.triggers = type("C", (dict,), {"folders": [folder]})({4: trigger})
        record = provider.get_trigger(4)
        assert record["tags"] == ["ask-first"]
        assert record["folderName"] == "Security"


# ----------------------------------------------------------------------
# Registry


def test_tag_tools_registered_as_writes_with_filters():
    tools = get_tool_schemas({name: Mock() for name in (
        "search_entities", "query_event_log", "list_triggers", "list_schedules",
        "get_trigger_details", "get_schedule_details", "get_action_group_details",
        "find_automation_references", "investigate_event", "control_trigger",
        "control_schedule", "control_action_group", "update_trigger", "update_schedule",
        "update_action_group", "manage_tags", "tag_objects")})
    assert {"manage_tags", "tag_objects"} <= WRITE_TOOLS
    for name in ("search_entities", "list_triggers", "list_schedules"):
        props = tools[name]["inputSchema"]["properties"]
        assert props["tags"]["type"] == "array" and props["tag_match"]["enum"] == ["all", "any"]
    for name in ("update_trigger", "update_schedule", "update_action_group"):
        assert "confirm" in tools[name]["inputSchema"]["properties"]
    assert tools["tag_objects"]["inputSchema"]["properties"]["objects"]["maxItems"] == MAX_OBJECTS_PER_CALL
