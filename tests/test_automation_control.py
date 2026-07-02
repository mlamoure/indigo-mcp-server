"""
Tests for the automation_control handler: entity/action matrix, exact
provider calls, and the delete gate (plugin pref + confirm).
"""

import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

plugin_path = Path(__file__).parent.parent / "MCP Server.indigoPlugin/Contents/Server Plugin"
sys.path.insert(0, str(plugin_path))

from mcp_server.adapters.indidb.store import IndiDbStructureStore  # noqa: E402
from mcp_server.tools.automation.automation_handler import AutomationHandler  # noqa: E402

DB_FIXTURE = Path(__file__).parent / "fixtures" / "sample_indidb.xml"


def make_handler(delete_enabled=False):
    provider = Mock()
    provider.automation_command.return_value = {"success": True}
    store = IndiDbStructureStore(db_path_supplier=lambda: str(DB_FIXTURE), logger=Mock())
    handler = AutomationHandler(
        data_provider=provider,
        structure_store=store,
        logger=Mock(),
        delete_enabled_supplier=lambda: delete_enabled,
    )
    return handler, provider


class TestControlMatrix:
    def test_disable_with_duration_maps_to_enable_false(self):
        handler, provider = make_handler()
        result = handler.control("trigger", 4000001, "disable", duration_seconds=7200)

        assert result["success"] is True
        assert result["action"] == "disable"
        assert result["name"] == "Front door opens at night"
        provider.automation_command.assert_called_once_with(
            "trigger", 4000001, "enable",
            value=False, delay=None, duration=7200,
            duplicate_name=None, folder_id=None,
        )

    def test_enable_action_group_is_invalid(self):
        handler, provider = make_handler()
        result = handler.control("action_group", 3000001, "enable")
        assert "error" in result
        provider.automation_command.assert_not_called()

    def test_remove_delayed_actions_invalid_for_action_group(self):
        handler, _ = make_handler()
        assert "error" in handler.control("action_group", 3000001, "remove_delayed_actions")

    def test_execute_schedule_with_delay(self):
        handler, provider = make_handler()
        handler.control("schedule", 5000001, "execute", delay_seconds=10)
        provider.automation_command.assert_called_once_with(
            "schedule", 5000001, "execute",
            value=None, delay=10, duration=None,
            duplicate_name=None, folder_id=None,
        )

    def test_duplicate_passes_name(self):
        handler, provider = make_handler()
        provider.automation_command.return_value = {
            "success": True, "new_id": 999, "new_name": "Copy"
        }
        result = handler.control(
            "trigger", 4000001, "duplicate", duplicate_name="Copy"
        )
        assert result["new_id"] == 999
        provider.automation_command.assert_called_once_with(
            "trigger", 4000001, "duplicate",
            value=None, delay=None, duration=None,
            duplicate_name="Copy", folder_id=None,
        )

    def test_move_requires_folder_id(self):
        handler, provider = make_handler()
        assert "error" in handler.control("trigger", 4000001, "move_to_folder")
        provider.automation_command.assert_not_called()

    def test_invalid_entity_and_action(self):
        handler, _ = make_handler()
        assert "error" in handler.control("widget", 1, "enable")
        assert "error" in handler.control("trigger", 1, "explode")

    def test_provider_error_passes_through(self):
        handler, provider = make_handler()
        provider.automation_command.return_value = {"error": "boom", "success": False}
        result = handler.control("trigger", 4000001, "execute")
        assert result["error"] == "boom"


class TestDeleteGate:
    def test_delete_blocked_when_pref_off(self):
        handler, provider = make_handler(delete_enabled=False)
        result = handler.control("trigger", 4000001, "delete", confirm=True)
        assert "error" in result
        assert "disabled" in result["error"]
        provider.automation_command.assert_not_called()

    def test_delete_requires_confirm(self):
        handler, provider = make_handler(delete_enabled=True)
        result = handler.control("trigger", 4000001, "delete")
        assert result.get("requires_confirmation") is True
        provider.automation_command.assert_not_called()

    def test_delete_with_pref_and_confirm(self):
        handler, provider = make_handler(delete_enabled=True)
        result = handler.control("trigger", 4000001, "delete", confirm=True)
        assert result["success"] is True
        provider.automation_command.assert_called_once_with(
            "trigger", 4000001, "delete",
            value=None, delay=None, duration=None,
            duplicate_name=None, folder_id=None,
        )


class TestProviderCommandMapping:
    """automation_command against a fake indigo module."""

    @pytest.fixture
    def provider_and_indigo(self):
        import mcp_server.adapters.indigo_data_provider as idp_module
        from unittest.mock import patch
        from mcp_server.adapters.indigo_data_provider import IndigoDataProvider

        fake = Mock()
        provider = IndigoDataProvider(logger=Mock())
        patcher = patch.object(idp_module, "indigo", fake, create=True)
        patcher.start()
        yield provider, fake
        patcher.stop()

    def test_enable_kwargs(self, provider_and_indigo):
        provider, fake = provider_and_indigo
        result = provider.automation_command(
            "trigger", 1, "enable", value=False, duration=7200
        )
        fake.trigger.enable.assert_called_once_with(1, value=False, duration=7200)
        assert result["enabled"] is False
        assert result["auto_reverts_after_seconds"] == 7200

    def test_duplicate_returns_new_identity(self, provider_and_indigo):
        provider, fake = provider_and_indigo
        fake.schedule.duplicate.return_value = Mock(id=42, name="Copy of X")
        result = provider.automation_command(
            "schedule", 1, "duplicate", duplicate_name="Copy of X"
        )
        fake.schedule.duplicate.assert_called_once_with(1, duplicateName="Copy of X")
        assert result["new_id"] == 42

    def test_action_group_delete(self, provider_and_indigo):
        provider, fake = provider_and_indigo
        result = provider.automation_command("action_group", 7, "delete")
        fake.actionGroup.delete.assert_called_once_with(7)
        assert result["success"] is True

    def test_exception_becomes_error(self, provider_and_indigo):
        provider, fake = provider_and_indigo
        fake.trigger.execute.side_effect = RuntimeError("nope")
        result = provider.automation_command("trigger", 1, "execute")
        assert result == {"error": "nope", "success": False}
