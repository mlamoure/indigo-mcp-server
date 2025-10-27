"""
Test suite for action control operations.
"""

import pytest
from unittest.mock import Mock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'MCP Server.indigoPlugin', 'Contents', 'Server Plugin'))

from mcp_server.tools.action_control import ActionControlHandler
from tests.mocks.mock_data_provider import MockDataProvider


class TestActionControlHandler:
    """Test action control handler functionality."""
    
    @pytest.fixture
    def handler(self):
        """Create an action control handler with mock data provider."""
        data_provider = MockDataProvider()
        logger = Mock()
        return ActionControlHandler(data_provider, logger)
    
    @pytest.fixture
    def mock_action_group(self):
        """Create a mock action group."""
        return {
            "id": 67890,
            "name": "Test Action Group",
            "folderId": 1,
            "description": "Test action group for testing"
        }
    
    def test_execute_action_group_immediate_success(self, handler):
        """Test successfully executing an action group immediately."""
        # Arrange
        action_group_id = 67890
        handler.data_provider.execute_action_group = Mock(return_value={
            "success": True,
            "job_id": None
        })
        
        # Act
        result = handler.execute(action_group_id)
        
        # Assert
        assert result["success"] is True
        assert result["job_id"] is None
        assert "error" not in result
        handler.data_provider.execute_action_group.assert_called_once_with(action_group_id, None)
    
    def test_execute_action_group_with_delay_success(self, handler):
        """Test successfully executing an action group with delay."""
        # Arrange
        action_group_id = 67890
        delay = 5
        handler.data_provider.execute_action_group = Mock(return_value={
            "success": True,
            "job_id": None
        })
        
        # Act
        result = handler.execute(action_group_id, delay)
        
        # Assert
        assert result["success"] is True
        assert result["job_id"] is None
        assert "error" not in result
        handler.data_provider.execute_action_group.assert_called_once_with(action_group_id, delay)
    
    def test_execute_action_group_zero_delay(self, handler):
        """Test executing an action group with zero delay (should be immediate)."""
        # Arrange
        action_group_id = 67890
        delay = 0
        handler.data_provider.execute_action_group = Mock(return_value={
            "success": True,
            "job_id": None
        })
        
        # Act
        result = handler.execute(action_group_id, delay)
        
        # Assert
        assert result["success"] is True
        handler.data_provider.execute_action_group.assert_called_once_with(action_group_id, delay)
    
    def test_execute_action_group_large_delay(self, handler):
        """Test executing an action group with large delay."""
        # Arrange
        action_group_id = 67890
        delay = 3600  # 1 hour
        handler.data_provider.execute_action_group = Mock(return_value={
            "success": True,
            "job_id": None
        })
        
        # Act
        result = handler.execute(action_group_id, delay)
        
        # Assert
        assert result["success"] is True
        handler.data_provider.execute_action_group.assert_called_once_with(action_group_id, delay)
    
    def test_execute_action_group_not_found(self, handler):
        """Test executing a non-existent action group."""
        # Arrange
        action_group_id = 99999
        handler.data_provider.execute_action_group = Mock(return_value={
            "error": f"Action group {action_group_id} not found",
            "success": False
        })
        
        # Act
        result = handler.execute(action_group_id)
        
        # Assert
        assert result["success"] is False
        assert "error" in result
        assert f"Action group {action_group_id} not found" in result["error"]
    
    def test_execute_action_group_invalid_id(self, handler):
        """Test executing with invalid action group ID."""
        # Act
        result = handler.execute("not_an_int")
        
        # Assert
        assert result["success"] is False
        assert "error" in result
        assert "action_group_id must be an integer" in result["error"]
    
    def test_execute_action_group_invalid_delay_negative(self, handler):
        """Test executing with negative delay."""
        # Act
        result = handler.execute(67890, -5)
        
        # Assert
        assert result["success"] is False
        assert "error" in result
        assert "delay must be a non-negative integer" in result["error"]
    
    def test_execute_action_group_invalid_delay_non_integer(self, handler):
        """Test executing with non-integer delay."""
        # Act
        result = handler.execute(67890, "not_an_int")
        
        # Assert
        assert result["success"] is False
        assert "error" in result
        assert "delay must be a non-negative integer" in result["error"]
    
    def test_execute_action_group_invalid_delay_float(self, handler):
        """Test executing with float delay."""
        # Act
        result = handler.execute(67890, 5.5)
        
        # Assert
        assert result["success"] is False
        assert "error" in result
        assert "delay must be a non-negative integer" in result["error"]
    
    def test_execute_action_group_execution_failed(self, handler):
        """Test handling execution failure from data provider."""
        # Arrange
        action_group_id = 67890
        handler.data_provider.execute_action_group = Mock(return_value={
            "error": "Action group execution failed",
            "success": False
        })
        
        # Act
        result = handler.execute(action_group_id)
        
        # Assert
        assert result["success"] is False
        assert "error" in result
        assert "Action group execution failed" in result["error"]
    
    def test_execute_action_group_with_job_id(self, handler):
        """Test executing action group that returns a job ID."""
        # Arrange
        action_group_id = 67890
        job_id = "job_12345"
        handler.data_provider.execute_action_group = Mock(return_value={
            "success": True,
            "job_id": job_id
        })
        
        # Act
        result = handler.execute(action_group_id)
        
        # Assert
        assert result["success"] is True
        assert result["job_id"] == job_id
        assert "error" not in result
    
    def test_exception_handling(self, handler):
        """Test exception handling in execute."""
        # Arrange
        action_group_id = 67890
        handler.data_provider.execute_action_group = Mock(side_effect=Exception("Unexpected error"))
        
        # Act
        result = handler.execute(action_group_id)
        
        # Assert
        assert result["success"] is False
        assert "error" in result
        assert "Unexpected error" in result["error"]
    
    def test_logging_immediate_execution(self, handler):
        """Test that immediate execution is logged correctly."""
        # Arrange
        action_group_id = 67890
        handler.data_provider.get_action_group = Mock(return_value={
            "id": action_group_id,
            "name": "Test Action Group"
        })
        handler.data_provider.execute_action_group = Mock(return_value={
            "success": True,
            "job_id": None
        })

        # Act
        result = handler.execute(action_group_id)

        # Assert
        assert result["success"] is True
        handler.logger.info.assert_called()
        # Check that logging includes the action name with play emoji (no delay string)
        log_calls = [call.args[0] for call in handler.logger.info.call_args_list]
        assert any("▶️ Test Action Group" in call and "(delay:" not in call for call in log_calls)
    
    def test_logging_delayed_execution(self, handler):
        """Test that delayed execution is logged correctly."""
        # Arrange
        action_group_id = 67890
        delay = 10
        handler.data_provider.get_action_group = Mock(return_value={
            "id": action_group_id,
            "name": "Test Action Group"
        })
        handler.data_provider.execute_action_group = Mock(return_value={
            "success": True,
            "job_id": None
        })

        # Act
        result = handler.execute(action_group_id, delay)

        # Assert
        assert result["success"] is True
        handler.logger.info.assert_called()
        # Check that logging mentions the delay with current format
        log_calls = [call.args[0] for call in handler.logger.info.call_args_list]
        assert any(f"▶️ Test Action Group (delay: {delay}s)" in call for call in log_calls)
    
    def test_logging_error(self, handler):
        """Test that errors are logged."""
        # Arrange
        action_group_id = 67890
        error_message = "Action group not found"
        handler.data_provider.get_action_group = Mock(return_value={
            "id": action_group_id,
            "name": "Test Action Group"
        })
        handler.data_provider.execute_action_group = Mock(return_value={
            "error": error_message,
            "success": False
        })

        # Act
        result = handler.execute(action_group_id)

        # Assert
        assert result["success"] is False
        handler.logger.info.assert_called()
        # Check that logging includes error emoji and error message
        log_calls = [call.args[0] for call in handler.logger.info.call_args_list]
        assert any(f"❌ Test Action Group: {error_message}" in call for call in log_calls)
    
    def test_logging_exception(self, handler):
        """Test that exceptions are logged."""
        # Arrange
        action_group_id = 67890
        handler.data_provider.execute_action_group = Mock(side_effect=Exception("Unexpected error"))
        
        # Act
        result = handler.execute(action_group_id)
        
        # Assert
        assert result["success"] is False
        handler.logger.error.assert_called_once()
    
    def test_execute_multiple_action_groups_sequentially(self, handler):
        """Test executing multiple action groups in sequence."""
        # Arrange
        action_ids = [67890, 67891, 67892]
        handler.data_provider.execute_action_group = Mock(return_value={
            "success": True,
            "job_id": None
        })
        
        # Act & Assert
        for action_id in action_ids:
            result = handler.execute(action_id)
            assert result["success"] is True
            assert "error" not in result
        
        # Verify all were called
        assert handler.data_provider.execute_action_group.call_count == len(action_ids)