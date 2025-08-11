"""
Tests for response utilities that handle various OpenAI response formats.
"""

import pytest
from unittest.mock import Mock

from mcp_server.common.response_utils import (
    extract_text_content,
    is_tool_call_response,
    extract_tool_calls
)


class TestResponseUtils:
    """Test response utility functions."""

    def test_extract_text_from_string(self):
        """Test extracting text from string response."""
        response = "hello world"
        result = extract_text_content(response, "test")
        assert result == "hello world"

    def test_extract_text_from_empty_string(self):
        """Test extracting text from empty string."""
        response = ""
        result = extract_text_content(response, "test")
        assert result == ""

    def test_extract_text_from_none(self):
        """Test extracting text from None response."""
        response = None
        result = extract_text_content(response, "test")
        assert result == ""

    def test_extract_text_from_chat_completion(self):
        """Test extracting text from ChatCompletion response."""
        # Mock ChatCompletion response
        mock_message = Mock()
        mock_message.content = "chat completion content"
        
        mock_choice = Mock()
        mock_choice.message = mock_message
        
        mock_response = Mock()
        mock_response.choices = [mock_choice]
        
        result = extract_text_content(mock_response, "test")
        assert result == "chat completion content"

    def test_extract_text_from_reasoning_item(self):
        """Test extracting text from ResponseReasoningItem-like object."""
        # Create simple classes instead of Mock objects
        class MockContentItem:
            def __init__(self):
                self.text = "reasoning content"
        
        class MockReasoningItem:
            def __init__(self):
                self.content = [MockContentItem()]
        
        mock_reasoning = MockReasoningItem()
        result = extract_text_content(mock_reasoning, "test")
        assert result == "reasoning content"

    def test_extract_text_from_object_with_text_attribute(self):
        """Test extracting text from object with text attribute."""
        class MockTextObj:
            def __init__(self):
                self.text = "object text content"
        
        mock_obj = MockTextObj()
        result = extract_text_content(mock_obj, "test")
        assert result == "object text content"

    def test_extract_text_from_list_response(self):
        """Test extracting text from list response."""
        class MockListItem:
            def __init__(self):
                self.text = "list item content"
        
        mock_item = MockListItem()
        response = [mock_item]
        result = extract_text_content(response, "test")
        assert result == "list item content"

    def test_extract_text_from_empty_list(self):
        """Test extracting text from empty list."""
        response = []
        result = extract_text_content(response, "test")
        assert result == ""

    def test_is_tool_call_response_with_tool_calls(self):
        """Test detecting tool call response."""
        mock_tool_call = Mock()
        mock_tool_call.function.name = "test_function"
        mock_tool_call.function.arguments = "{}"
        
        mock_message = Mock()
        mock_message.tool_calls = [mock_tool_call]
        
        mock_choice = Mock()
        mock_choice.message = mock_message
        
        mock_response = Mock()
        mock_response.choices = [mock_choice]
        
        assert is_tool_call_response(mock_response) is True

    def test_is_tool_call_response_without_tool_calls(self):
        """Test detecting non-tool-call response."""
        mock_message = Mock()
        mock_message.tool_calls = None
        mock_message.function_call = None
        
        mock_choice = Mock()
        mock_choice.message = mock_message
        
        mock_response = Mock()
        mock_response.choices = [mock_choice]
        
        assert is_tool_call_response(mock_response) is False

    def test_is_tool_call_response_with_dict(self):
        """Test detecting tool call in dict format."""
        response = {"tool_calls": [{"function": {"name": "test", "arguments": "{}"}}]}
        assert is_tool_call_response(response) is True

    def test_extract_tool_calls_from_dict(self):
        """Test extracting tool calls from dict response."""
        response = {
            "tool_calls": [
                {"function": {"name": "test_function", "arguments": "{}"}}
            ]
        }
        
        result = extract_tool_calls(response)
        assert len(result) == 1
        assert result[0]["function"]["name"] == "test_function"

    def test_extract_tool_calls_from_chat_completion(self):
        """Test extracting tool calls from ChatCompletion response."""
        mock_tool_call = Mock()
        mock_tool_call.function.name = "test_function"
        mock_tool_call.function.arguments = "{}"
        
        mock_message = Mock()
        mock_message.tool_calls = [mock_tool_call]
        
        mock_choice = Mock()
        mock_choice.message = mock_message
        
        mock_response = Mock()
        mock_response.choices = [mock_choice]
        
        result = extract_tool_calls(mock_response)
        assert len(result) == 1
        assert result[0]["function"]["name"] == "test_function"

    def test_extract_tool_calls_empty(self):
        """Test extracting tool calls from response without tools."""
        mock_message = Mock()
        mock_message.tool_calls = None
        mock_message.function_call = None
        
        mock_choice = Mock()
        mock_choice.message = mock_message
        
        mock_response = Mock()
        mock_response.choices = [mock_choice]
        
        result = extract_tool_calls(mock_response)
        assert result == []