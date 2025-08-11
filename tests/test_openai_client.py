"""
Tests for OpenAI client functionality, including structured output handling.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import List
from pydantic import BaseModel

# Import the module under test
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'MCP Server.indigoPlugin', 'Contents', 'Server Plugin'))

from mcp_server.common.openai_client.main import perform_completion


# Test BaseModel for structured output testing
class MockMockTestResponse(BaseModel):
    """Test response model for structured output tests."""
    items: List[str]
    count: int


class TestOpenAIClient:
    """Test OpenAI client functionality."""

    @pytest.fixture
    def mock_openai_client(self):
        """Mock OpenAI client with proper structure."""
        mock_client = Mock()
        mock_completion = Mock()
        mock_completion.choices = [Mock()]
        mock_completion.choices[0].message.content = "Test response"
        
        # Mock both create and parse methods
        mock_client.chat.completions.create.return_value = mock_completion
        mock_client.chat.completions.parse.return_value = mock_completion
        
        return mock_client

    @patch('mcp_server.common.openai_client.main._get_client')
    def test_perform_completion_standard(self, mock_client_func, mock_openai_client):
        """Test standard completion without structured output."""
        mock_client_func.return_value = mock_openai_client
        
        messages = [{"role": "user", "content": "Test message"}]
        result = perform_completion(messages=messages, model="gpt-5-mini")
        
        # Should use create() method for standard completion
        mock_openai_client.chat.completions.create.assert_called_once()
        mock_openai_client.chat.completions.parse.assert_not_called()
        assert result == "Test response"

    @patch('mcp_server.common.openai_client.main._get_client')
    def test_perform_completion_structured_output_success(self, mock_client_func, mock_openai_client):
        """Test structured output using parse() method - success case."""
        mock_client_func.return_value = mock_openai_client
        
        messages = [{"role": "user", "content": "Test message"}]
        result = perform_completion(
            messages=messages, 
            model="gpt-5-mini",
            response_model=MockTestResponse
        )
        
        # Should use parse() method for structured output
        mock_openai_client.chat.completions.parse.assert_called_once_with(
            model="gpt-5-mini",
            messages=messages,
            response_format=MockTestResponse
        )
        mock_openai_client.chat.completions.create.assert_not_called()
        assert result == "Test response"

    @patch('mcp_server.common.openai_client.main._get_client')
    def test_perform_completion_structured_output_fallback(self, mock_client_func, mock_openai_client):
        """Test structured output fallback when parse() fails."""
        mock_client_func.return_value = mock_openai_client
        
        # Make parse() fail, but create() succeed
        mock_openai_client.chat.completions.parse.side_effect = Exception("Parse failed")
        
        messages = [{"role": "user", "content": "Test message"}]
        result = perform_completion(
            messages=messages, 
            model="gpt-5-mini",
            response_model=MockTestResponse
        )
        
        # Should first try parse(), then fallback to create()
        mock_openai_client.chat.completions.parse.assert_called_once()
        mock_openai_client.chat.completions.create.assert_called_once_with(
            model="gpt-5-mini", 
            messages=messages
        )
        assert result == "Test response"

    @patch('mcp_server.common.openai_client.main._get_client')
    def test_perform_completion_with_tools(self, mock_client_func, mock_openai_client):
        """Test completion with tools (should use create() method)."""
        mock_client_func.return_value = mock_openai_client
        
        messages = [{"role": "user", "content": "Test message"}]
        tools = [{"type": "function", "function": {"name": "test_tool"}}]
        
        result = perform_completion(
            messages=messages, 
            model="gpt-5-mini",
            tools=tools
        )
        
        # Should use create() method for tool calls
        mock_openai_client.chat.completions.create.assert_called_once()
        mock_openai_client.chat.completions.parse.assert_not_called()
        assert result == "Test response"

    @patch('mcp_server.common.openai_client.main._get_client')
    def test_perform_completion_empty_response(self, mock_client_func, mock_openai_client):
        """Test handling of empty response."""
        mock_client_func.return_value = mock_openai_client
        
        # Mock empty response
        mock_openai_client.chat.completions.create.return_value = None
        
        messages = [{"role": "user", "content": "Test message"}]
        result = perform_completion(messages=messages, model="gpt-5-mini")
        
        assert result == ""

    @patch('mcp_server.common.openai_client.main._get_client')
    def test_perform_completion_no_choices(self, mock_client_func, mock_openai_client):
        """Test handling of response with no choices."""
        mock_client_func.return_value = mock_openai_client
        
        # Mock response with no choices
        mock_completion = Mock()
        mock_completion.choices = []
        mock_openai_client.chat.completions.create.return_value = mock_completion
        
        messages = [{"role": "user", "content": "Test message"}]
        result = perform_completion(messages=messages, model="gpt-5-mini")
        
        assert result == ""

    @patch('mcp_server.common.openai_client.main._get_client')
    def test_perform_completion_no_content(self, mock_client_func, mock_openai_client):
        """Test handling of response with no content."""
        mock_client_func.return_value = mock_openai_client
        
        # Mock response with None content
        mock_completion = Mock()
        mock_completion.choices = [Mock()]
        mock_completion.choices[0].message.content = None
        mock_openai_client.chat.completions.create.return_value = mock_completion
        
        messages = [{"role": "user", "content": "Test message"}]
        result = perform_completion(messages=messages, model="gpt-5-mini")
        
        assert result == ""

    @patch('mcp_server.common.openai_client.main._get_client')
    def test_perform_completion_client_exception(self, mock_client_func):
        """Test handling of client initialization failure."""
        mock_client_func.return_value = None
        
        messages = [{"role": "user", "content": "Test message"}]
        result = perform_completion(messages=messages, model="gpt-5-mini")
        
        assert result == ""

    @patch('mcp_server.common.openai_client.main._get_client')
    def test_perform_completion_api_exception(self, mock_client_func, mock_openai_client):
        """Test handling of API call exceptions."""
        mock_client_func.return_value = mock_openai_client
        
        # Make both methods fail
        mock_openai_client.chat.completions.create.side_effect = Exception("API Error")
        mock_openai_client.chat.completions.parse.side_effect = Exception("Parse Error")
        
        messages = [{"role": "user", "content": "Test message"}]
        
        # Should handle exception gracefully for standard completion
        result = perform_completion(messages=messages, model="gpt-5-mini")
        assert result == ""
        
        # Should handle exception gracefully for structured output
        result = perform_completion(
            messages=messages, 
            model="gpt-5-mini",
            response_model=MockTestResponse
        )
        assert result == ""


class TestStructuredOutputIntegration:
    """Integration tests for structured output functionality."""
    
    @patch('mcp_server.common.openai_client.main._get_client')
    def test_batch_keywords_response_simulation(self, mock_client_func):
        """Test simulation of BatchKeywordsResponse structured output."""
        # Import the actual model used in the error
        from mcp_server.common.vector_store.semantic_keywords import BatchKeywordsResponse
        
        mock_client = Mock()
        mock_client_func.return_value = mock_client
        
        # Mock successful parse response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = '{"devices": [{"device_number": 1, "keywords": ["test"]}]}'
        mock_client.chat.completions.parse.return_value = mock_response
        
        messages = [{"role": "user", "content": "Generate keywords"}]
        result = perform_completion(
            messages=messages,
            model="gpt-5-mini",
            response_model=BatchKeywordsResponse
        )
        
        # Should successfully call parse() method
        mock_client.chat.completions.parse.assert_called_once_with(
            model="gpt-5-mini",
            messages=messages,
            response_format=BatchKeywordsResponse
        )
        assert result == '{"devices": [{"device_number": 1, "keywords": ["test"]}]}'

    @patch('mcp_server.common.openai_client.main._get_client')
    def test_batch_keywords_response_fallback(self, mock_client_func):
        """Test fallback behavior when BatchKeywordsResponse parse fails."""
        from mcp_server.common.vector_store.semantic_keywords import BatchKeywordsResponse
        
        mock_client = Mock()
        mock_client_func.return_value = mock_client
        
        # Mock parse failure, but create success
        mock_client.chat.completions.parse.side_effect = Exception("You tried to pass a `BaseModel` class")
        
        mock_fallback_response = Mock()
        mock_fallback_response.choices = [Mock()]
        mock_fallback_response.choices[0].message.content = "Fallback response"
        mock_client.chat.completions.create.return_value = mock_fallback_response
        
        messages = [{"role": "user", "content": "Generate keywords"}]
        result = perform_completion(
            messages=messages,
            model="gpt-5-mini", 
            response_model=BatchKeywordsResponse
        )
        
        # Should first try parse(), then fallback to create()
        mock_client.chat.completions.parse.assert_called_once()
        mock_client.chat.completions.create.assert_called_once_with(
            model="gpt-5-mini",
            messages=messages
        )
        assert result == "Fallback response"