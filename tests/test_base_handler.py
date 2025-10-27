"""
Tests for the base tool handler.
"""

import pytest
import logging
from unittest.mock import Mock, patch
from mcp_server.tools.base_handler import BaseToolHandler


class TestBaseToolHandler:
    """Test cases for BaseToolHandler."""
    
    def test_initialization(self):
        """Test base handler initialization."""
        handler = BaseToolHandler("test_tool")
        
        assert handler.tool_name == "test_tool"
        assert handler.logger is not None
    
    def test_initialization_with_logger(self):
        """Test base handler initialization with custom logger."""
        mock_logger = Mock(spec=logging.Logger)
        handler = BaseToolHandler("test_tool", mock_logger)
        
        assert handler.tool_name == "test_tool"
        assert handler.logger == mock_logger
    
    def test_info_log(self):
        """Test standardized info logging."""
        mock_logger = Mock(spec=logging.Logger)
        handler = BaseToolHandler("test_tool", mock_logger)
        
        handler.info_log("test message")
        
        mock_logger.info.assert_called_once_with("[test_tool]: test message")
    
    def test_debug_log(self):
        """Test debug logging with standardized format."""
        mock_logger = Mock(spec=logging.Logger)
        handler = BaseToolHandler("test_tool", mock_logger)

        handler.debug_log("debug message")

        # Should be called with format: [tool_name]: message
        assert mock_logger.debug.called
        call_args = mock_logger.debug.call_args[0][0]
        assert "[test_tool]" in call_args
        assert "debug message" in call_args
        # Verify the exact expected format
        assert call_args == "[test_tool]: debug message"
    
    def test_warning_log(self):
        """Test standardized warning logging."""
        mock_logger = Mock(spec=logging.Logger)
        handler = BaseToolHandler("test_tool", mock_logger)
        
        handler.warning_log("warning message")
        
        mock_logger.warning.assert_called_once_with("[test_tool]: warning message")
    
    def test_error_log(self):
        """Test standardized error logging."""
        mock_logger = Mock(spec=logging.Logger)
        handler = BaseToolHandler("test_tool", mock_logger)
        
        handler.error_log("error message")
        
        mock_logger.error.assert_called_once_with("[test_tool]: error message")
    
    def test_handle_exception(self):
        """Test exception handling with standardized error reporting."""
        mock_logger = Mock(spec=logging.Logger)
        handler = BaseToolHandler("test_tool", mock_logger)
        
        test_exception = ValueError("test error")
        result = handler.handle_exception(test_exception, "test context")
        
        # Should log the error
        assert mock_logger.error.called
        error_call = mock_logger.error.call_args[0][0]
        assert "[test_tool]" in error_call
        assert "test error" in error_call
        assert "test context" in error_call
        
        # Should return error dictionary
        assert result["error"] == "test error"
        assert result["tool"] == "test_tool"
        assert result["context"] == "test context"
        assert result["success"] is False
    
    def test_handle_exception_without_context(self):
        """Test exception handling without context."""
        mock_logger = Mock(spec=logging.Logger)
        handler = BaseToolHandler("test_tool", mock_logger)
        
        test_exception = RuntimeError("runtime error")
        result = handler.handle_exception(test_exception)
        
        assert result["error"] == "runtime error"
        assert result["tool"] == "test_tool"
        assert result["context"] == ""
        assert result["success"] is False
    
    def test_create_success_response(self):
        """Test creation of standardized success response."""
        mock_logger = Mock(spec=logging.Logger)
        handler = BaseToolHandler("test_tool", mock_logger)
        
        test_data = {"key": "value"}
        result = handler.create_success_response(test_data, "success message")
        
        # Should log the success message
        mock_logger.info.assert_called_once_with("[test_tool]: success message")
        
        # Should return success dictionary
        assert result["success"] is True
        assert result["tool"] == "test_tool"
        assert result["data"] == test_data
        assert result["message"] == "success message"
    
    def test_create_success_response_without_message(self):
        """Test success response without message."""
        handler = BaseToolHandler("test_tool")
        
        test_data = {"key": "value"}
        result = handler.create_success_response(test_data)
        
        assert result["success"] is True
        assert result["tool"] == "test_tool"
        assert result["data"] == test_data
        assert "message" not in result
    
    def test_validate_required_params_valid(self):
        """Test parameter validation with valid parameters."""
        handler = BaseToolHandler("test_tool")
        
        params = {"param1": "value1", "param2": "value2"}
        required = ["param1", "param2"]
        
        result = handler.validate_required_params(params, required)
        
        assert result is None  # Should return None for valid params
    
    def test_validate_required_params_missing(self):
        """Test parameter validation with missing parameters."""
        mock_logger = Mock(spec=logging.Logger)
        handler = BaseToolHandler("test_tool", mock_logger)
        
        params = {"param1": "value1"}
        required = ["param1", "param2", "param3"]
        
        result = handler.validate_required_params(params, required)
        
        # Should log error
        assert mock_logger.error.called
        
        # Should return error dictionary
        assert result is not None
        assert result["error"] == "Missing required parameters: param2, param3"
        assert result["tool"] == "test_tool"
        assert result["missing_parameters"] == ["param2", "param3"]
        assert result["success"] is False
    
    def test_validate_required_params_none_values(self):
        """Test parameter validation with None values."""
        handler = BaseToolHandler("test_tool")
        
        params = {"param1": "value1", "param2": None}
        required = ["param1", "param2"]
        
        result = handler.validate_required_params(params, required)
        
        # Should treat None as missing
        assert result is not None
        assert "param2" in result["missing_parameters"]
    
    def test_validate_required_params_empty_required(self):
        """Test parameter validation with no required parameters."""
        handler = BaseToolHandler("test_tool")
        
        params = {"param1": "value1"}
        required = []
        
        result = handler.validate_required_params(params, required)
        
        assert result is None  # Should return None for no requirements