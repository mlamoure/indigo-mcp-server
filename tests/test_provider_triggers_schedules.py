"""
Tests for IndigoDataProvider trigger/schedule/dependency methods with a fake
`indigo` module (see test_indigo_data_provider.py for the base pattern).
"""

import datetime
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

plugin_path = Path(__file__).parent.parent / "MCP Server.indigoPlugin/Contents/Server Plugin"
sys.path.insert(0, str(plugin_path))

import mcp_server.adapters.indigo_data_provider as idp_module  # noqa: E402
from mcp_server.adapters.indigo_data_provider import IndigoDataProvider  # noqa: E402


class _FakeElem:
    """Attribute bag mimicking a typed IOM object."""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


# The provider maps IOM class NAMES to normalized types, so the fakes must
# carry the real class names.
DeviceStateChangeTrigger = type("DeviceStateChangeTrigger", (_FakeElem,), {})
VariableValueChangeTrigger = type("VariableValueChangeTrigger", (_FakeElem,), {})
PluginEventTrigger = type("PluginEventTrigger", (_FakeElem,), {})
ServerStartupTrigger = type("ServerStartupTrigger", (_FakeElem,), {})
Schedule = type("Schedule", (_FakeElem,), {})


class FakeFolder(_FakeElem):
    pass


class FakeCollection:
    """Mimics indigo.triggers / indigo.schedules: in, [id], iter(), folders."""

    def __init__(self, elems, folders=()):
        self._elems = elems
        self.folders = list(folders)

    def __contains__(self, elem_id):
        return elem_id in self._elems

    def __getitem__(self, elem_id):
        return self._elems[elem_id]

    def iter(self):
        return iter(self._elems.values())


def make_trigger(cls=DeviceStateChangeTrigger, **overrides):
    base = dict(
        id=4000001,
        name="Front door opens at night",
        description="",
        enabled=True,
        folderId=0,
    )
    base.update(overrides)
    return cls(**base)


@pytest.fixture
def provider():
    return IndigoDataProvider(logger=Mock())


def with_indigo(fake):
    return patch.object(idp_module, "indigo", fake, create=True)


class TestGetAllTriggers:
    def test_typed_fields_and_folder_names(self, provider):
        trigger = make_trigger(
            deviceId=1000222,
            stateSelector="onOffState",
            stateSelectorIndex=0,
            stateChangeType="indigo.kStateChange.BecomesTrue",
            stateValue="",
            folderId=77,
        )
        fake = Mock()
        fake.triggers = FakeCollection(
            {4000001: trigger}, folders=[FakeFolder(id=77, name="Security")]
        )
        with with_indigo(fake):
            result = provider.get_all_triggers()

        assert len(result) == 1
        entry = result[0]
        assert entry["type"] == "device_state_change"
        assert entry["deviceId"] == 1000222
        assert entry["stateChangeType"] == "becomes_true"
        assert entry["folderName"] == "Security"
        assert "pluginProps" not in entry

    def test_variable_trigger_fields(self, provider):
        trigger = make_trigger(
            VariableValueChangeTrigger,
            variableId=2000888,
            variableChangeType="indigo.kVarChange.Changes",
            variableValue="",
        )
        fake = Mock()
        fake.triggers = FakeCollection({4000001: trigger})
        with with_indigo(fake):
            entry = provider.get_all_triggers()[0]

        assert entry["type"] == "variable_change"
        assert entry["variableId"] == 2000888
        assert entry["variableChangeType"] == "changes"

    def test_exception_returns_empty_list(self, provider):
        fake = Mock()
        fake.triggers = Mock(iter=Mock(side_effect=RuntimeError("down")), folders=[])
        with with_indigo(fake):
            assert provider.get_all_triggers() == []


class TestGetTrigger:
    def test_plugin_trigger_includes_props(self, provider):
        trigger = make_trigger(
            PluginEventTrigger,
            pluginId="com.example.camera",
            pluginTypeId="cameramotion",
            pluginProps={"sensitivity": 7},
        )
        fake = Mock()
        fake.triggers = FakeCollection({4000001: trigger})
        with with_indigo(fake):
            entry = provider.get_trigger(4000001)

        assert entry["type"] == "plugin_event"
        assert entry["pluginId"] == "com.example.camera"
        assert entry["pluginProps"] == {"sensitivity": 7}

    def test_missing_returns_none(self, provider):
        fake = Mock()
        fake.triggers = FakeCollection({})
        with with_indigo(fake):
            assert provider.get_trigger(99) is None


class TestGetSchedules:
    def test_schedule_fields(self, provider):
        sched = Schedule(
            id=5000001,
            name="Nightly",
            description="",
            enabled=True,
            folderId=0,
            dateType="EveryDay",
            timeType="Absolute",
            sunDelta=0,
            randomizeBy=0,
            autoDelete=False,
            nextExecution=datetime.datetime(2026, 7, 3, 9, 0),
            absoluteTime=datetime.datetime(2000, 1, 1, 21, 30),
            absoluteDate=datetime.datetime(1, 1, 1),
        )
        fake = Mock()
        fake.schedules = FakeCollection({5000001: sched})
        with with_indigo(fake):
            entry = provider.get_all_schedules()[0]

        assert entry["date_type"] == "every_day"
        assert entry["time_type"] == "absolute"
        assert entry["next_execution"] == "2026-07-03T09:00:00"
        assert entry["absolute_time"] == "21:30:00"
        assert entry["absolute_date"] is None  # year-1 sentinel

    def test_unset_next_execution_is_none(self, provider):
        sched = Schedule(
            id=1, name="x", description="", enabled=False, folderId=0,
            dateType="EveryDay", timeType="Sunset", sunDelta=-1200,
            randomizeBy=0, autoDelete=False,
            nextExecution=datetime.datetime(1, 1, 1),
            absoluteTime=datetime.datetime(1, 1, 1),
            absoluteDate=datetime.datetime(1, 1, 1),
        )
        fake = Mock()
        fake.schedules = FakeCollection({1: sched})
        with with_indigo(fake):
            entry = provider.get_schedule(1)

        assert entry["next_execution"] is None
        assert entry["absolute_time"] is None


class TestGetDependencies:
    def test_converts_server_dict(self, provider):
        deps = {
            "triggers": [{"ID": 1, "Name": "T"}],
            "schedules": [],
            "actionGroups": [{"ID": 2, "Name": "AG"}],
            "devices": [],
            "variables": [],
            "controlPages": [],
        }
        fake = Mock()
        fake.device.getDependencies.return_value = deps
        with with_indigo(fake):
            result = provider.get_dependencies("device", 42)

        assert result["triggers"] == [{"id": 1, "name": "T"}]
        assert result["action_groups"] == [{"id": 2, "name": "AG"}]
        fake.device.getDependencies.assert_called_once_with(42)

    def test_unsupported_type(self, provider):
        with with_indigo(Mock()):
            assert "error" in provider.get_dependencies("widget", 1)

    def test_exception_becomes_error(self, provider):
        fake = Mock()
        fake.trigger.getDependencies.side_effect = RuntimeError("slow down")
        with with_indigo(fake):
            result = provider.get_dependencies("trigger", 1)
        assert result == {"error": "slow down"}


class TestServerPaths:
    def test_paths(self, provider):
        fake = Mock()
        fake.server.getDbFilePath.return_value = "/x/Westwood.indiDb"
        fake.server.getLogsFolderPath.return_value = "/x/Logs"
        with with_indigo(fake):
            assert provider.get_db_file_path() == "/x/Westwood.indiDb"
            assert provider.get_logs_folder_path() == "/x/Logs"

    def test_exception_returns_none(self, provider):
        fake = Mock()
        fake.server.getDbFilePath.side_effect = RuntimeError("down")
        with with_indigo(fake):
            assert provider.get_db_file_path() is None


class TestVectorStoreEntities:
    def test_includes_triggers_and_schedules(self, provider):
        fake = Mock()
        fake.devices = FakeCollection({})
        fake.variables = FakeCollection({})
        fake.actionGroups = FakeCollection({})
        fake.triggers = FakeCollection({4000001: make_trigger()})
        fake.schedules = FakeCollection({})
        with with_indigo(fake):
            entities = provider.get_all_entities_for_vector_store()

        assert set(entities.keys()) == {
            "devices", "variables", "actions", "triggers", "schedules"
        }
        assert entities["triggers"][0]["id"] == 4000001
