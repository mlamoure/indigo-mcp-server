"""
Test suite for list_variable_folders functionality.
"""

import pytest
from unittest.mock import Mock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'MCP Server.indigoPlugin', 'Contents', 'Server Plugin'))

from mcp_server.handlers.list_handlers import ListHandlers
from tests.mocks.mock_data_provider import MockDataProvider


class TestListVariableFolders:
    """Test list variable folders functionality."""

    @pytest.fixture
    def handler(self):
        """Create a list handlers instance with mock data provider."""
        data_provider = MockDataProvider()
        logger = Mock()
        return ListHandlers(data_provider, logger)

    def test_list_variable_folders_success(self, handler):
        """Test successfully listing all variable folders."""
        # Act
        result = handler.list_variable_folders()

        # Assert
        assert "folders" in result
        assert "count" in result
        assert "summary" in result
        assert result["count"] == 3
        assert len(result["folders"]) == 3

    def test_list_variable_folders_contains_folder_properties(self, handler):
        """Test that folders contain required properties."""
        # Act
        result = handler.list_variable_folders()

        # Assert
        folders = result["folders"]
        for folder in folders:
            assert "id" in folder
            assert "name" in folder
            assert "description" in folder
            assert isinstance(folder["id"], int)
            assert isinstance(folder["name"], str)
            assert isinstance(folder["description"], str)

    def test_list_variable_folders_contains_expected_folders(self, handler):
        """Test that expected folders are returned."""
        # Act
        result = handler.list_variable_folders()

        # Assert
        folders = result["folders"]
        folder_names = [f["name"] for f in folders]
        assert "System" in folder_names
        assert "Weather" in folder_names
        assert "Home Automation" in folder_names

    def test_list_variable_folders_has_correct_summary(self, handler):
        """Test that summary is correctly formatted."""
        # Act
        result = handler.list_variable_folders()

        # Assert
        assert result["summary"] == "Found 3 variable folders"

    def test_list_variable_folders_empty_list(self):
        """Test handling of empty folder list."""
        # Arrange
        data_provider = MockDataProvider()
        data_provider.variable_folders = []
        logger = Mock()
        handler = ListHandlers(data_provider, logger)

        # Act
        result = handler.list_variable_folders()

        # Assert
        assert result["count"] == 0
        assert len(result["folders"]) == 0
        assert result["summary"] == "Found 0 variable folders"

    def test_list_variable_folders_folder_ids(self, handler):
        """Test that folder IDs are correct."""
        # Act
        result = handler.list_variable_folders()

        # Assert
        folders = result["folders"]
        folder_ids = [f["id"] for f in folders]
        assert 1 in folder_ids
        assert 2 in folder_ids
        assert 3 in folder_ids

    def test_list_variable_folders_folder_descriptions(self, handler):
        """Test that folder descriptions are included."""
        # Act
        result = handler.list_variable_folders()

        # Assert
        folders = result["folders"]
        descriptions = [f["description"] for f in folders]
        assert "System variables" in descriptions
        assert "Weather-related variables" in descriptions
        assert "Home automation control variables" in descriptions

    def test_list_variable_folders_data_isolation(self, handler):
        """Test that returned data is isolated from internal data."""
        # Act
        result1 = handler.list_variable_folders()
        result2 = handler.list_variable_folders()

        # Modify result1
        result1["folders"][0]["name"] = "Modified"

        # Assert result2 is not affected
        assert result2["folders"][0]["name"] != "Modified"
        assert result2["folders"][0]["name"] == "System"

    def test_list_variable_folders_exception_handling(self):
        """Test exception handling in list_variable_folders."""
        # Arrange
        data_provider = MockDataProvider()
        data_provider.get_variable_folders = Mock(side_effect=Exception("Test error"))
        logger = Mock()
        handler = ListHandlers(data_provider, logger)

        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            handler.list_variable_folders()

        assert "Test error" in str(exc_info.value)
        handler.logger.error.assert_called_once()

    def test_list_variable_folders_logging(self, handler):
        """Test that errors are logged."""
        # Arrange - make get_variable_folders raise an exception
        handler.data_provider.get_variable_folders = Mock(side_effect=Exception("Test error"))

        # Act & Assert
        with pytest.raises(Exception):
            handler.list_variable_folders()

        # Assert logging occurred
        handler.logger.error.assert_called()
        error_call_args = str(handler.logger.error.call_args)
        assert "variable folders" in error_call_args.lower() or "Test error" in error_call_args
