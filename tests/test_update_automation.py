"""
Tests for update_automation: the editing gate, field whitelists, reference
validation, and the provider's replaceOnServer flow with enum conversion.
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

plugin_path = Path(__file__).parent.parent / "MCP Server.indigoPlugin/Contents/Server Plugin"
sys.path.insert(0, str(plugin_path))

import mcp_server.adapters.indigo_data_provider as idp_module  # noqa: E402
from mcp_server.adapters.indigo_data_provider import IndigoDataProvider  # noqa: E402
from mcp_server.adapters.indidb.store import IndiDbStructureStore  # noqa: E402
from mcp_server.tools.automation.automation_handler import AutomationHandler  # noqa: E402

DB_FIXTURE = Path(__file__).parent / "fixtures" / "sample_indidb.xml"


def make_handler(editing_enabled=True):
    provider = Mock()
    provider.update_automation_fields.return_value = {
        "success": True,
        "before": {"name": "Old"},
        "after": {"name": "New"},
    }
    store = IndiDbStructureStore(db_path_supplier=lambda: str(DB_FIXTURE), logger=Mock())
    handler = AutomationHandler(
        data_provider=provider,
        structure_store=store,
        logger=Mock(),
        editing_enabled_supplier=lambda: editing_enabled,
    )
    return handler, provider


class TestUpdateGate:
    def test_blocked_when_pref_off(self):
        handler, provider = make_handler(editing_enabled=False)
        result = handler.update("trigger", 4000001, {"name": "X"})
        assert "error" in result and "disabled" in result["error"]
        provider.update_automation_fields.assert_not_called()

    def test_requires_fields(self):
        handler, _ = make_handler()
        assert "error" in handler.update("trigger", 4000001, {})
        assert "error" in handler.update("trigger", 4000001, None)

    def test_happy_path_logs_diff(self):
        handler, provider = make_handler()
        result = handler.update("trigger", 4000001, {"name": "New"})
        assert result["success"] is True
        assert "note" in result
        provider.update_automation_fields.assert_called_once_with(
            "trigger", 4000001, {"name": "New"}
        )

    def test_device_reference_must_exist(self):
        handler, provider = make_handler()
        provider.get_device.return_value = None
        result = handler.update("trigger", 4000001, {"device_id": 42})
        assert "error" in result
        provider.update_automation_fields.assert_not_called()

    def test_device_reference_in_fixture_is_ok(self):
        handler, provider = make_handler()
        result = handler.update("trigger", 4000001, {"device_id": 1000111})
        assert result["success"] is True


class TestProviderUpdateFields:
    class FakeTrigger:
        def __init__(self):
            self.name = "Old name"
            self.description = ""
            self.deviceId = 1000222
            self.stateSelector = "onOffState"
            self.stateSelectorIndex = 0
            self.stateChangeType = "indigo.kStateChange.BecomesTrue"
            self.stateValue = ""
            self.replaced = False

        def replaceOnServer(self):
            self.replaced = True

    class FakeContainer:
        def __init__(self, elems):
            self._elems = elems

        def __contains__(self, elem_id):
            return elem_id in self._elems

        def __getitem__(self, elem_id):
            return self._elems[elem_id]

    @pytest.fixture
    def env(self):
        provider = IndigoDataProvider(logger=Mock())
        trigger = self.FakeTrigger()
        fake = Mock()
        fake.triggers = self.FakeContainer({4000001: trigger})
        fake.kStateChange = Mock(spec=["BecomesFalse", "BecomesTrue"])
        fake.kStateChange.BecomesFalse = "kStateChange.BecomesFalse"
        fake.kStateChange.BecomesTrue = "kStateChange.BecomesTrue"
        with patch.object(idp_module, "indigo", fake, create=True):
            yield provider, trigger

    def test_updates_and_diffs(self, env):
        provider, trigger = env
        result = provider.update_automation_fields(
            "trigger", 4000001,
            {"name": "New name", "state_change_type": "becomes_false"},
        )
        assert trigger.replaced is True
        assert trigger.name == "New name"
        assert trigger.stateChangeType == "kStateChange.BecomesFalse"
        assert result["before"]["name"] == "Old name"
        assert result["after"]["name"] == "New name"
        assert result["after"]["state_change_type"] == "becomes_false"

    def test_unknown_field_rejected(self, env):
        provider, trigger = env
        result = provider.update_automation_fields(
            "trigger", 4000001, {"enabled": True}
        )
        assert "error" in result and "not editable" in result["error"]
        assert trigger.replaced is False

    def test_invalid_enum_value(self, env):
        provider, trigger = env
        result = provider.update_automation_fields(
            "trigger", 4000001, {"state_change_type": "explodes"}
        )
        assert "error" in result
        assert trigger.replaced is False

    def test_missing_element(self, env):
        provider, _ = env
        assert "error" in provider.update_automation_fields(
            "trigger", 99, {"name": "X"}
        )


class TestScheduleWhitelist:
    def test_schedule_timing_fields_rejected(self):
        # Schedule timing attrs are read-only on IOM instances (verified live
        # on Indigo 2025.2) — the whitelist must reject them up front.
        provider = IndigoDataProvider(logger=Mock())
        fake = Mock()
        with patch.object(idp_module, "indigo", fake, create=True):
            for field in ("date_type", "time_type", "absolute_time",
                          "sun_delta_seconds", "randomize_by_seconds", "auto_delete"):
                result = provider.update_automation_fields("schedule", 1, {field: "x"})
                assert "not editable" in result["error"], field

    def test_enum_conversion(self):
        fake = Mock()
        fake.kVarChange = Mock(spec=["Changes", "BecomesTrue"])
        fake.kVarChange.Changes = "kVarChange.Changes"
        with patch.object(idp_module, "indigo", fake, create=True):
            value = IndigoDataProvider._to_indigo_enum("kVarChange", "changes")
        assert value == "kVarChange.Changes"
