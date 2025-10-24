"""
Tests for plugin control functionality.
"""

import json
import logging
import os
import plistlib
import tempfile
import time
from unittest.mock import MagicMock, Mock, patch

import pytest

# Import the modules to test
from mcp_server.tools.plugin_control.plugin_scanner import PluginScanner
from mcp_server.tools.plugin_control.plugin_control_handler import PluginControlHandler


class MockPlugin:
    """Mock Indigo plugin object."""

    def __init__(self, plugin_id, enabled=True, display_name="Test Plugin"):
        self.pluginId = plugin_id
        self._enabled = enabled
        self.pluginDisplayName = display_name

    def isEnabled(self):
        return self._enabled

    def restart(self):
        if not self._enabled:
            raise RuntimeError("Cannot restart disabled plugin")


@pytest.fixture
def logger():
    """Create a logger for testing."""
    return logging.getLogger("test")


@pytest.fixture
def mock_data_provider():
    """Create a mock data provider."""
    provider = Mock()
    return provider


@pytest.fixture
def plugin_scanner(logger):
    """Create a plugin scanner instance."""
    return PluginScanner(logger)


@pytest.fixture
def plugin_control_handler(mock_data_provider, logger):
    """Create a plugin control handler instance."""
    return PluginControlHandler(mock_data_provider, logger)


@pytest.fixture
def temp_plugin_dir():
    """Create a temporary plugin directory structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create enabled plugins directory
        enabled_dir = os.path.join(tmpdir, "Plugins")
        os.makedirs(enabled_dir)

        # Create disabled plugins directory
        disabled_dir = os.path.join(tmpdir, "Plugins (Disabled)")
        os.makedirs(disabled_dir)

        # Create a test plugin bundle
        plugin_bundle = os.path.join(enabled_dir, "TestPlugin.indigoPlugin")
        os.makedirs(plugin_bundle)
        contents_dir = os.path.join(plugin_bundle, "Contents")
        os.makedirs(contents_dir)

        # Create Info.plist
        plist_data = {
            "CFBundleIdentifier": "com.test.plugin",
            "CFBundleDisplayName": "Test Plugin",
            "CFBundleVersion": "1.0.0",
        }
        plist_path = os.path.join(contents_dir, "Info.plist")
        with open(plist_path, "wb") as f:
            plistlib.dump(plist_data, f)

        # Create a disabled plugin
        disabled_bundle = os.path.join(disabled_dir, "DisabledPlugin.indigoPlugin")
        os.makedirs(disabled_bundle)
        disabled_contents = os.path.join(disabled_bundle, "Contents")
        os.makedirs(disabled_contents)

        disabled_plist = {
            "CFBundleIdentifier": "com.test.disabled",
            "CFBundleDisplayName": "Disabled Plugin",
            "CFBundleVersion": "2.0.0",
        }
        disabled_plist_path = os.path.join(disabled_contents, "Info.plist")
        with open(disabled_plist_path, "wb") as f:
            plistlib.dump(disabled_plist, f)

        yield tmpdir


class TestPluginScanner:
    """Tests for PluginScanner class."""

    def test_scan_plugins_enabled_only(self, plugin_scanner, temp_plugin_dir):
        """Test scanning for enabled plugins only."""
        plugins = plugin_scanner.scan_plugins(temp_plugin_dir, include_disabled=False)

        assert len(plugins) == 1
        assert plugins[0]["id"] == "com.test.plugin"
        assert plugins[0]["name"] == "Test Plugin"
        assert plugins[0]["version"] == "1.0.0"
        assert plugins[0]["enabled"] is True

    def test_scan_plugins_include_disabled(self, plugin_scanner, temp_plugin_dir):
        """Test scanning for all plugins including disabled."""
        plugins = plugin_scanner.scan_plugins(temp_plugin_dir, include_disabled=True)

        assert len(plugins) == 2

        # Check enabled plugin
        enabled = [p for p in plugins if p["id"] == "com.test.plugin"][0]
        assert enabled["name"] == "Test Plugin"
        assert enabled["enabled"] is True

        # Check disabled plugin
        disabled = [p for p in plugins if p["id"] == "com.test.disabled"][0]
        assert disabled["name"] == "Disabled Plugin"
        assert disabled["enabled"] is False

    def test_scan_empty_directory(self, plugin_scanner):
        """Test scanning an empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugins_dir = os.path.join(tmpdir, "Plugins")
            os.makedirs(plugins_dir)

            plugins = plugin_scanner.scan_plugins(tmpdir, include_disabled=False)
            assert len(plugins) == 0

    def test_scan_malformed_plist(self, plugin_scanner):
        """Test handling of malformed Info.plist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugins_dir = os.path.join(tmpdir, "Plugins")
            os.makedirs(plugins_dir)

            # Create plugin with malformed plist
            bundle = os.path.join(plugins_dir, "BadPlugin.indigoPlugin")
            os.makedirs(bundle)
            contents = os.path.join(bundle, "Contents")
            os.makedirs(contents)

            plist_path = os.path.join(contents, "Info.plist")
            with open(plist_path, "w") as f:
                f.write("malformed data")

            plugins = plugin_scanner.scan_plugins(tmpdir, include_disabled=False)
            # Should skip malformed plugins
            assert len(plugins) == 0

    def test_parse_info_plist(self, plugin_scanner, temp_plugin_dir):
        """Test parsing Info.plist file."""
        plist_path = os.path.join(
            temp_plugin_dir,
            "Plugins",
            "TestPlugin.indigoPlugin",
            "Contents",
            "Info.plist",
        )

        result = plugin_scanner.parse_info_plist(plist_path)

        assert result is not None
        assert result["id"] == "com.test.plugin"
        assert result["name"] == "Test Plugin"
        assert result["version"] == "1.0.0"

    def test_parse_info_plist_missing_file(self, plugin_scanner):
        """Test parsing non-existent Info.plist."""
        result = plugin_scanner.parse_info_plist("/nonexistent/path/Info.plist")
        assert result is None


class TestPluginControlHandler:
    """Tests for PluginControlHandler class."""

    @patch("mcp_server.tools.plugin_control.plugin_control_handler.indigo")
    def test_list_plugins_success(
        self, mock_indigo, plugin_control_handler, temp_plugin_dir
    ):
        """Test successful plugin listing."""
        # Mock indigo.server.getInstallFolderPath
        mock_indigo.server.getInstallFolderPath.return_value = temp_plugin_dir

        result = plugin_control_handler.list_plugins(include_disabled=False)

        assert result["success"] is True
        assert result["count"] == 1
        assert len(result["plugins"]) == 1
        assert result["plugins"][0]["id"] == "com.test.plugin"

    @patch("mcp_server.tools.plugin_control.plugin_control_handler.indigo")
    def test_list_plugins_with_disabled(
        self, mock_indigo, plugin_control_handler, temp_plugin_dir
    ):
        """Test listing plugins including disabled ones."""
        mock_indigo.server.getInstallFolderPath.return_value = temp_plugin_dir

        result = plugin_control_handler.list_plugins(include_disabled=True)

        assert result["success"] is True
        assert result["count"] == 2
        assert result["include_disabled"] is True

    @patch("mcp_server.tools.plugin_control.plugin_control_handler.indigo")
    def test_list_plugins_caching(
        self, mock_indigo, plugin_control_handler, temp_plugin_dir
    ):
        """Test plugin list caching behavior."""
        mock_indigo.server.getInstallFolderPath.return_value = temp_plugin_dir

        # First call - should scan file system
        result1 = plugin_control_handler.list_plugins(include_disabled=False)
        assert result1["success"] is True

        # Second call within cache duration - should use cache
        result2 = plugin_control_handler.list_plugins(include_disabled=False)
        assert result2["success"] is True
        assert result2 == result1

        # Cache should be used
        assert len(plugin_control_handler._plugin_cache) > 0

    @patch("mcp_server.tools.plugin_control.plugin_control_handler.indigo")
    def test_list_plugins_cache_expiration(
        self, mock_indigo, plugin_control_handler, temp_plugin_dir, monkeypatch
    ):
        """Test plugin cache expiration after 60 minutes."""
        mock_indigo.server.getInstallFolderPath.return_value = temp_plugin_dir

        # First call
        result1 = plugin_control_handler.list_plugins(include_disabled=False)
        assert result1["success"] is True

        # Simulate time passing (61 minutes)
        original_time = time.time
        monkeypatch.setattr(
            time,
            "time",
            lambda: original_time() + 3660,  # 61 minutes
        )

        # Should rescan due to cache expiration
        result2 = plugin_control_handler.list_plugins(include_disabled=False)
        assert result2["success"] is True

    @patch("mcp_server.tools.plugin_control.plugin_control_handler.indigo")
    def test_get_plugin_by_id_success(self, mock_indigo, plugin_control_handler):
        """Test successful plugin retrieval by ID."""
        mock_plugin = MockPlugin("com.test.plugin", enabled=True)
        mock_indigo.server.getPlugin.return_value = mock_plugin
        mock_indigo.server.getInstallFolderPath.return_value = "/tmp"

        # Mock scanner to return empty list
        with patch.object(plugin_control_handler.scanner, "scan_plugins", return_value=[]):
            result = plugin_control_handler.get_plugin_by_id("com.test.plugin")

        assert result["success"] is True
        assert result["plugin"]["id"] == "com.test.plugin"
        assert result["plugin"]["enabled"] is True

    @patch("mcp_server.tools.plugin_control.plugin_control_handler.indigo")
    def test_get_plugin_by_id_not_found(self, mock_indigo, plugin_control_handler):
        """Test plugin not found error."""
        mock_indigo.server.getPlugin.side_effect = AttributeError("Plugin not found")

        result = plugin_control_handler.get_plugin_by_id("com.invalid.plugin")

        assert result["success"] is False
        assert "not found" in result["error"]
        assert "suggestion" in result

    @patch("mcp_server.tools.plugin_control.plugin_control_handler.indigo")
    def test_restart_plugin_success(self, mock_indigo, plugin_control_handler):
        """Test successful plugin restart."""
        mock_plugin = MockPlugin("com.test.plugin", enabled=True)
        mock_indigo.server.getPlugin.return_value = mock_plugin

        result = plugin_control_handler.restart_plugin("com.test.plugin")

        assert result["success"] is True
        assert "restarted successfully" in result["message"]
        assert result["plugin_id"] == "com.test.plugin"

    @patch("mcp_server.tools.plugin_control.plugin_control_handler.indigo")
    def test_restart_plugin_disabled(self, mock_indigo, plugin_control_handler):
        """Test restarting a disabled plugin."""
        mock_plugin = MockPlugin("com.test.plugin", enabled=False)
        mock_indigo.server.getPlugin.return_value = mock_plugin

        result = plugin_control_handler.restart_plugin("com.test.plugin")

        assert result["success"] is False
        assert "not enabled" in result["error"]
        assert "suggestion" in result

    @patch("mcp_server.tools.plugin_control.plugin_control_handler.indigo")
    def test_restart_plugin_invalidates_cache(
        self, mock_indigo, plugin_control_handler, temp_plugin_dir
    ):
        """Test that restarting a plugin invalidates the cache."""
        mock_indigo.server.getInstallFolderPath.return_value = temp_plugin_dir

        # Populate cache
        plugin_control_handler.list_plugins(include_disabled=False)
        assert len(plugin_control_handler._plugin_cache) > 0

        # Restart plugin
        mock_plugin = MockPlugin("com.test.plugin", enabled=True)
        mock_indigo.server.getPlugin.return_value = mock_plugin
        plugin_control_handler.restart_plugin("com.test.plugin")

        # Cache should be cleared
        assert len(plugin_control_handler._plugin_cache) == 0

    @patch("mcp_server.tools.plugin_control.plugin_control_handler.indigo")
    def test_get_plugin_status_success(self, mock_indigo, plugin_control_handler):
        """Test successful plugin status retrieval."""
        mock_plugin = MockPlugin("com.test.plugin", enabled=True, display_name="Test")
        mock_indigo.server.getPlugin.return_value = mock_plugin
        mock_indigo.server.getInstallFolderPath.return_value = "/tmp"

        with patch.object(plugin_control_handler.scanner, "scan_plugins", return_value=[]):
            result = plugin_control_handler.get_plugin_status("com.test.plugin")

        assert result["success"] is True
        assert result["status"]["id"] == "com.test.plugin"
        assert result["status"]["enabled"] is True
        assert result["status"]["displayName"] == "Test"

    @patch("mcp_server.tools.plugin_control.plugin_control_handler.indigo")
    def test_get_plugin_status_not_found(self, mock_indigo, plugin_control_handler):
        """Test status for non-existent plugin."""
        mock_indigo.server.getPlugin.side_effect = AttributeError("Not found")

        result = plugin_control_handler.get_plugin_status("com.invalid.plugin")

        assert result["success"] is False
        assert "not found" in result["error"]

    def test_cache_separate_keys(self, plugin_control_handler, temp_plugin_dir):
        """Test that enabled and disabled plugin lists have separate cache keys."""
        with patch("mcp_server.tools.plugin_control.plugin_control_handler.indigo") as mock_indigo:
            mock_indigo.server.getInstallFolderPath.return_value = temp_plugin_dir

            # List enabled only
            result1 = plugin_control_handler.list_plugins(include_disabled=False)
            assert result1["count"] == 1

            # List all (including disabled)
            result2 = plugin_control_handler.list_plugins(include_disabled=True)
            assert result2["count"] == 2

            # Should have two separate cache entries
            assert len(plugin_control_handler._plugin_cache) == 2
            assert "plugins_False" in plugin_control_handler._plugin_cache
            assert "plugins_True" in plugin_control_handler._plugin_cache


class TestPluginControlIntegration:
    """Integration tests for plugin control."""

    @patch("mcp_server.tools.plugin_control.plugin_control_handler.indigo")
    def test_end_to_end_workflow(
        self, mock_indigo, plugin_control_handler, temp_plugin_dir
    ):
        """Test complete workflow: list -> get -> restart -> status."""
        mock_indigo.server.getInstallFolderPath.return_value = temp_plugin_dir

        # 1. List plugins
        list_result = plugin_control_handler.list_plugins(include_disabled=False)
        assert list_result["success"] is True
        plugin_id = list_result["plugins"][0]["id"]

        # 2. Get plugin by ID
        mock_plugin = MockPlugin(plugin_id, enabled=True)
        mock_indigo.server.getPlugin.return_value = mock_plugin
        get_result = plugin_control_handler.get_plugin_by_id(plugin_id)
        assert get_result["success"] is True

        # 3. Restart plugin
        restart_result = plugin_control_handler.restart_plugin(plugin_id)
        assert restart_result["success"] is True

        # 4. Check status
        status_result = plugin_control_handler.get_plugin_status(plugin_id)
        assert status_result["success"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
