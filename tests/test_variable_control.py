"""
Test suite for variable control operations.
"""

import pytest
from unittest.mock import Mock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'MCP Server.indigoPlugin', 'Contents', 'Server Plugin'))

from mcp_server.tools.variable_control import VariableControlHandler
from tests.mocks.mock_data_provider import MockDataProvider


class TestVariableControlHandler:
    """Test variable control handler functionality."""
    
    @pytest.fixture
    def handler(self):
        """Create a variable control handler with mock data provider."""
        data_provider = MockDataProvider()
        logger = Mock()
        return VariableControlHandler(data_provider, logger)
    
    @pytest.fixture
    def mock_variable(self):
        """Create a mock variable."""
        return {
            "id": 54321,
            "name": "Test Variable",
            "value": "initial_value",
            "folderId": 1,
            "readOnly": False
        }
    
    def test_update_variable_string_success(self, handler):
        """Test successfully updating a variable with string value."""
        # Arrange
        variable_id = 54321
        new_value = "new_string_value"
        handler.data_provider.update_variable = Mock(return_value={
            "previous": "initial_value",
            "current": "new_string_value"
        })
        
        # Act
        result = handler.update(variable_id, new_value)
        
        # Assert
        assert result["previous"] == "initial_value"
        assert result["current"] == "new_string_value"
        assert "error" not in result
        handler.data_provider.update_variable.assert_called_once_with(variable_id, new_value)
    
    def test_update_variable_numeric_success(self, handler):
        """Test successfully updating a variable with numeric value."""
        # Arrange
        variable_id = 54321
        new_value = 42
        handler.data_provider.update_variable = Mock(return_value={
            "previous": "0",
            "current": "42"
        })
        
        # Act
        result = handler.update(variable_id, new_value)
        
        # Assert
        assert result["previous"] == "0"
        assert result["current"] == "42"
        assert "error" not in result
    
    def test_update_variable_boolean_success(self, handler):
        """Test successfully updating a variable with boolean value."""
        # Arrange
        variable_id = 54321
        new_value = True
        handler.data_provider.update_variable = Mock(return_value={
            "previous": "false",
            "current": "True"
        })
        
        # Act
        result = handler.update(variable_id, new_value)
        
        # Assert
        assert result["previous"] == "false"
        assert result["current"] == "True"
        assert "error" not in result
    
    def test_update_variable_float_success(self, handler):
        """Test successfully updating a variable with float value."""
        # Arrange
        variable_id = 54321
        new_value = 3.14159
        handler.data_provider.update_variable = Mock(return_value={
            "previous": "0.0",
            "current": "3.14159"
        })
        
        # Act
        result = handler.update(variable_id, new_value)
        
        # Assert
        assert result["previous"] == "0.0"
        assert result["current"] == "3.14159"
        assert "error" not in result
    
    def test_update_variable_same_value(self, handler):
        """Test updating a variable to the same value."""
        # Arrange
        variable_id = 54321
        same_value = "unchanged_value"
        handler.data_provider.update_variable = Mock(return_value={
            "previous": "unchanged_value",
            "current": "unchanged_value"
        })
        
        # Act
        result = handler.update(variable_id, same_value)
        
        # Assert
        assert result["previous"] == "unchanged_value"
        assert result["current"] == "unchanged_value"
        assert "error" not in result
    
    def test_update_variable_not_found(self, handler):
        """Test updating a non-existent variable."""
        # Arrange
        variable_id = 99999
        new_value = "test_value"
        handler.data_provider.update_variable = Mock(return_value={
            "error": f"Variable {variable_id} not found"
        })
        
        # Act
        result = handler.update(variable_id, new_value)
        
        # Assert
        assert "error" in result
        assert f"Variable {variable_id} not found" in result["error"]
    
    def test_update_variable_read_only(self, handler):
        """Test updating a read-only variable."""
        # Arrange
        variable_id = 54321
        new_value = "test_value"
        handler.data_provider.update_variable = Mock(return_value={
            "error": f"Variable {variable_id} is read-only"
        })
        
        # Act
        result = handler.update(variable_id, new_value)
        
        # Assert
        assert "error" in result
        assert "is read-only" in result["error"]
    
    def test_update_variable_invalid_id(self, handler):
        """Test updating with invalid variable ID."""
        # Act
        result = handler.update("not_an_int", "test_value")
        
        # Assert
        assert "error" in result
        assert "variable_id must be an integer" in result["error"]
    
    def test_update_variable_none_value(self, handler):
        """Test updating a variable with None value."""
        # Arrange
        variable_id = 54321
        new_value = None
        handler.data_provider.update_variable = Mock(return_value={
            "previous": "some_value",
            "current": "None"
        })
        
        # Act
        result = handler.update(variable_id, new_value)
        
        # Assert
        assert result["previous"] == "some_value"
        assert result["current"] == "None"
        assert "error" not in result
    
    def test_update_variable_empty_string(self, handler):
        """Test updating a variable with empty string."""
        # Arrange
        variable_id = 54321
        new_value = ""
        handler.data_provider.update_variable = Mock(return_value={
            "previous": "some_value",
            "current": ""
        })
        
        # Act
        result = handler.update(variable_id, new_value)
        
        # Assert
        assert result["previous"] == "some_value"
        assert result["current"] == ""
        assert "error" not in result
    
    def test_update_variable_long_string(self, handler):
        """Test updating a variable with a very long string."""
        # Arrange
        variable_id = 54321
        new_value = "x" * 1000  # Very long string
        handler.data_provider.update_variable = Mock(return_value={
            "previous": "short",
            "current": "x" * 1000
        })
        
        # Act
        result = handler.update(variable_id, new_value)
        
        # Assert
        assert result["previous"] == "short"
        assert result["current"] == "x" * 1000
        assert "error" not in result
    
    def test_update_variable_special_characters(self, handler):
        """Test updating a variable with special characters."""
        # Arrange
        variable_id = 54321
        new_value = "Special!@#$%^&*()_+-={}[]|\\:;\"'<>,.?/~`"
        handler.data_provider.update_variable = Mock(return_value={
            "previous": "normal",
            "current": new_value
        })
        
        # Act
        result = handler.update(variable_id, new_value)
        
        # Assert
        assert result["previous"] == "normal"
        assert result["current"] == new_value
        assert "error" not in result
    
    def test_update_variable_unicode_characters(self, handler):
        """Test updating a variable with unicode characters."""
        # Arrange
        variable_id = 54321
        new_value = "Unicode: 你好 🌟 café naïve résumé"
        handler.data_provider.update_variable = Mock(return_value={
            "previous": "ascii",
            "current": new_value
        })
        
        # Act
        result = handler.update(variable_id, new_value)
        
        # Assert
        assert result["previous"] == "ascii"
        assert result["current"] == new_value
        assert "error" not in result
    
    def test_exception_handling(self, handler):
        """Test exception handling in update."""
        # Arrange
        variable_id = 54321
        new_value = "test_value"
        handler.data_provider.update_variable = Mock(side_effect=Exception("Unexpected error"))
        
        # Act
        result = handler.update(variable_id, new_value)
        
        # Assert
        assert "error" in result
        assert "Unexpected error" in result["error"]
    
    def test_logging_success(self, handler):
        """Test that successful operations are logged."""
        # Arrange
        variable_id = 54321
        new_value = "test_value"
        handler.data_provider.update_variable = Mock(return_value={
            "previous": "old_value",
            "current": "test_value"
        })
        
        # Act
        result = handler.update(variable_id, new_value)
        
        # Assert
        assert "error" not in result
        handler.logger.info.assert_called()
        # Check that logging was called for both the attempt and success
        assert handler.logger.info.call_count >= 2
    
    def test_logging_error(self, handler):
        """Test that errors are logged."""
        # Arrange
        variable_id = 54321
        new_value = "test_value"
        error_message = "Variable not found"
        handler.data_provider.update_variable = Mock(return_value={
            "error": error_message
        })
        
        # Act
        result = handler.update(variable_id, new_value)
        
        # Assert
        assert "error" in result
        handler.logger.error.assert_called_once()