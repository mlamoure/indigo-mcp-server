"""
Test suite for log query operations.
"""

import pytest
from unittest.mock import Mock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'MCP Server.indigoPlugin', 'Contents', 'Server Plugin'))

from mcp_server.tools.log_query import LogQueryHandler
from tests.mocks.mock_data_provider import MockDataProvider


class TestLogQueryHandler:
    """Test log query handler functionality."""

    @pytest.fixture
    def handler(self):
        """Create a log query handler with mock data provider."""
        data_provider = MockDataProvider()
        logger = Mock()
        return LogQueryHandler(data_provider, logger)

    @pytest.fixture
    def mock_log_entries(self):
        """Create mock log entries."""
        return [
            "2025-01-15 10:30:45  Device 'Living Room Lamp' on",
            "2025-01-15 10:30:50  Device 'Bedroom Light' off",
            "2025-01-15 10:31:00  Variable 'house_mode' set to 'away'",
            "2025-01-15 10:31:15  Action group 'Good Morning' executed",
            "2025-01-15 10:31:30  Error: Device 'Garage Door' communication failure"
        ]

    def test_query_default_parameters(self, handler, mock_log_entries):
        """Test querying log with default parameters."""
        # Arrange
        handler.data_provider.get_event_log_list = Mock(return_value=mock_log_entries)

        # Act
        result = handler.query()

        # Assert
        assert result["success"] is True
        assert result["count"] == 5
        assert result["entries"] == mock_log_entries
        assert result["parameters"]["line_count"] == 20
        assert result["parameters"]["show_timestamp"] is True
        handler.data_provider.get_event_log_list.assert_called_once_with(
            line_count=20,
            show_timestamp=True
        )

    def test_query_custom_line_count(self, handler, mock_log_entries):
        """Test querying log with custom line count."""
        # Arrange
        custom_entries = mock_log_entries[:3]
        handler.data_provider.get_event_log_list = Mock(return_value=custom_entries)

        # Act
        result = handler.query(line_count=3)

        # Assert
        assert result["success"] is True
        assert result["count"] == 3
        assert result["entries"] == custom_entries
        assert result["parameters"]["line_count"] == 3
        handler.data_provider.get_event_log_list.assert_called_once_with(
            line_count=3,
            show_timestamp=True
        )

    def test_query_without_timestamps(self, handler):
        """Test querying log without timestamps."""
        # Arrange
        entries_no_timestamp = [
            "Device 'Living Room Lamp' on",
            "Device 'Bedroom Light' off",
            "Variable 'house_mode' set to 'away'"
        ]
        handler.data_provider.get_event_log_list = Mock(return_value=entries_no_timestamp)

        # Act
        result = handler.query(show_timestamp=False)

        # Assert
        assert result["success"] is True
        assert result["count"] == 3
        assert result["entries"] == entries_no_timestamp
        assert result["parameters"]["show_timestamp"] is False
        handler.data_provider.get_event_log_list.assert_called_once_with(
            line_count=20,
            show_timestamp=False
        )

    def test_query_custom_parameters(self, handler, mock_log_entries):
        """Test querying log with both custom parameters."""
        # Arrange
        handler.data_provider.get_event_log_list = Mock(return_value=mock_log_entries)

        # Act
        result = handler.query(line_count=5, show_timestamp=False)

        # Assert
        assert result["success"] is True
        assert result["count"] == 5
        assert result["parameters"]["line_count"] == 5
        assert result["parameters"]["show_timestamp"] is False
        handler.data_provider.get_event_log_list.assert_called_once_with(
            line_count=5,
            show_timestamp=False
        )

    def test_query_empty_log(self, handler):
        """Test querying log when no entries exist."""
        # Arrange
        handler.data_provider.get_event_log_list = Mock(return_value=[])

        # Act
        result = handler.query()

        # Assert
        assert result["success"] is True
        assert result["count"] == 0
        assert result["entries"] == []

    def test_query_single_entry(self, handler):
        """Test querying log with single entry."""
        # Arrange
        single_entry = ["2025-01-15 10:30:45  Device 'Test Device' on"]
        handler.data_provider.get_event_log_list = Mock(return_value=single_entry)

        # Act
        result = handler.query(line_count=1)

        # Assert
        assert result["success"] is True
        assert result["count"] == 1
        assert result["entries"] == single_entry

    def test_query_large_line_count(self, handler, mock_log_entries):
        """Test querying log with large line count."""
        # Arrange
        large_entries = mock_log_entries * 100  # 500 entries
        handler.data_provider.get_event_log_list = Mock(return_value=large_entries)

        # Act
        result = handler.query(line_count=500)

        # Assert
        assert result["success"] is True
        assert result["count"] == 500
        assert len(result["entries"]) == 500

    def test_query_invalid_line_count_negative(self, handler):
        """Test querying log with negative line count."""
        # Act
        result = handler.query(line_count=-5)

        # Assert
        assert "error" in result
        assert result["success"] is False
        assert "line_count must be a positive integer" in result["error"]

    def test_query_invalid_line_count_zero(self, handler):
        """Test querying log with zero line count."""
        # Act
        result = handler.query(line_count=0)

        # Assert
        assert "error" in result
        assert result["success"] is False
        assert "line_count must be a positive integer" in result["error"]

    def test_query_invalid_line_count_string(self, handler):
        """Test querying log with string line count."""
        # Act
        result = handler.query(line_count="ten")

        # Assert
        assert "error" in result
        assert result["success"] is False
        assert "line_count must be a positive integer" in result["error"]

    def test_query_none_line_count(self, handler, mock_log_entries):
        """Test querying log with None line count (should use default)."""
        # Arrange
        handler.data_provider.get_event_log_list = Mock(return_value=mock_log_entries)

        # Act
        result = handler.query(line_count=None)

        # Assert
        assert result["success"] is True
        assert result["parameters"]["line_count"] is None
        handler.data_provider.get_event_log_list.assert_called_once_with(
            line_count=None,
            show_timestamp=True
        )

    def test_query_special_characters_in_log(self, handler):
        """Test querying log entries with special characters."""
        # Arrange
        special_entries = [
            "2025-01-15 10:30:45  Device 'Test <>&\"' on",
            "2025-01-15 10:30:50  Variable 'test_var' set to 'value with \\n newline'",
            "2025-01-15 10:31:00  Action group 'Test 🌟' executed"
        ]
        handler.data_provider.get_event_log_list = Mock(return_value=special_entries)

        # Act
        result = handler.query()

        # Assert
        assert result["success"] is True
        assert result["count"] == 3
        assert result["entries"] == special_entries

    def test_query_multiline_log_entries(self, handler):
        """Test querying log with multiline entries."""
        # Arrange
        multiline_entries = [
            "2025-01-15 10:30:45  Error: Device 'Test'\n  Stack trace: ...",
            "2025-01-15 10:30:50  Warning: Multiple lines\n  Line 2\n  Line 3"
        ]
        handler.data_provider.get_event_log_list = Mock(return_value=multiline_entries)

        # Act
        result = handler.query()

        # Assert
        assert result["success"] is True
        assert result["count"] == 2
        assert result["entries"] == multiline_entries

    def test_exception_handling(self, handler):
        """Test exception handling in query."""
        # Arrange
        handler.data_provider.get_event_log_list = Mock(
            side_effect=Exception("Log retrieval error")
        )

        # Act
        result = handler.query()

        # Assert
        assert "error" in result
        assert "Log retrieval error" in result["error"]
        assert result["success"] is False

    def test_logging_success(self, handler, mock_log_entries):
        """Test that successful operations are logged."""
        # Arrange
        handler.data_provider.get_event_log_list = Mock(return_value=mock_log_entries)

        # Act
        result = handler.query()

        # Assert
        assert result["success"] is True
        handler.logger.info.assert_called_once()
        # Verify the log message includes operation success and entry count
        log_message = handler.logger.info.call_args[0][0]
        assert "query" in log_message.lower()
        assert "completed successfully" in log_message
        assert str(len(mock_log_entries)) in log_message

    def test_logging_error(self, handler):
        """Test that errors are logged."""
        # Arrange
        handler.data_provider.get_event_log_list = Mock(
            side_effect=Exception("Test error")
        )

        # Act
        result = handler.query()

        # Assert
        assert "error" in result
        handler.logger.error.assert_called_once()

    def test_query_various_log_types(self, handler):
        """Test querying different types of log entries."""
        # Arrange
        various_entries = [
            "2025-01-15 10:30:45  Device state change",
            "2025-01-15 10:30:46  Variable update",
            "2025-01-15 10:30:47  Action group executed",
            "2025-01-15 10:30:48  Plugin started",
            "2025-01-15 10:30:49  Error occurred",
            "2025-01-15 10:30:50  Warning issued",
            "2025-01-15 10:30:51  Info message"
        ]
        handler.data_provider.get_event_log_list = Mock(return_value=various_entries)

        # Act
        result = handler.query(line_count=10)

        # Assert
        assert result["success"] is True
        assert result["count"] == 7
        assert result["entries"] == various_entries
