"""
Utilities for handling OpenAI response structures consistently.
Provides robust text extraction from various response types including GPT-5 reasoning items.
"""

import logging
from typing import Any, Union, List, Optional

logger = logging.getLogger("Plugin")


def extract_text_content(response: Any, context_name: str = "response") -> str:
    """
    Extract text content from various OpenAI response types.
    
    Handles:
    - Standard OpenAI ChatCompletion responses
    - String responses
    - List responses (from some LLM configurations)
    - ResponseReasoningItem objects (GPT-5 reasoning models)
    - Tool call responses
    - Various other response object types
    
    Args:
        response: Response object from OpenAI API
        context_name: Context name for error logging
        
    Returns:
        Extracted text content as string, empty string if extraction fails
    """
    try:
        logger.debug(f"🔍 Extracting text from {type(response).__name__} for {context_name}")
        
        # Handle None or empty responses
        if response is None:
            logger.debug(f"❌ None response for {context_name}")
            return ""
        
        # Handle string responses directly
        if isinstance(response, str):
            logger.debug(f"✅ Direct string response for {context_name}")
            return response.strip()
        
        # Handle ChatCompletion responses (standard OpenAI format)
        if hasattr(response, 'choices') and response.choices:
            choice = response.choices[0]
            if hasattr(choice, 'message') and choice.message:
                content = choice.message.content
                if content:
                    logger.debug(f"✅ Extracted content from ChatCompletion for {context_name}")
                    return content.strip()
        
        # Handle list responses (common with some LLM configurations)
        if isinstance(response, list):
            logger.debug(f"📋 Processing list response with {len(response)} items for {context_name}")
            
            if not response:
                logger.warning(f"⚠️ Empty list response for {context_name}")
                return ""
            
            # Try to extract content from first valid item in list
            for i, item in enumerate(response):
                logger.debug(f"🔍 Trying list item {i}: {type(item).__name__}")
                
                # Recursively extract from list items
                extracted = _extract_from_single_object(item, f"{context_name}-item-{i}")
                if extracted:
                    logger.debug(f"✅ Extracted text from list item {i} for {context_name}")
                    return extracted
            
            logger.warning(f"⚠️ No valid content found in list response for {context_name}")
            return ""
        
        # Handle single response objects (including ResponseReasoningItem)
        return _extract_from_single_object(response, context_name)
        
    except Exception as e:
        logger.error(f"💥 Exception in text extraction for {context_name}: {e}")
        return ""


def _extract_from_single_object(response_obj: Any, context_name: str) -> str:
    """
    Extract text content from a single response object.
    
    Args:
        response_obj: Single response object (not a list)
        context_name: Context name for error logging
        
    Returns:
        Extracted text content as string
    """
    try:
        # Handle string responses directly
        if isinstance(response_obj, str):
            logger.debug(f"✅ Direct string response for {context_name}")
            return response_obj.strip()
        
        # Check for content attribute (ResponseReasoningItem, etc.)
        if hasattr(response_obj, 'content'):
            content = response_obj.content
            if content is not None:
                # Handle content as a list of content items
                if isinstance(content, list):
                    logger.debug(f"📋 Processing content list with {len(content)} items for {context_name}")
                    for i, content_item in enumerate(content):
                        if hasattr(content_item, 'text') and content_item.text:
                            logger.debug(f"✅ Extracted text from content item {i} for {context_name}")
                            return str(content_item.text).strip()
                # Handle content as a string
                elif isinstance(content, str):
                    logger.debug(f"✅ Extracted content string from {type(response_obj).__name__} for {context_name}")
                    return content.strip()
                # Handle content as an object with text
                elif hasattr(content, 'text') and content.text:
                    logger.debug(f"✅ Extracted text from content object for {context_name}")
                    return str(content.text).strip()
                # Fallback to string conversion of content
                else:
                    content_str = str(content).strip()
                    if content_str and content_str != "None":
                        logger.debug(f"✅ String-converted content from {type(response_obj).__name__} for {context_name}")
                        return content_str
        
        # Check for text attribute
        if hasattr(response_obj, 'text') and response_obj.text:
            logger.debug(f"✅ Extracted text from {type(response_obj).__name__} for {context_name}")
            return str(response_obj.text).strip()
        
        # Check for message attribute
        if hasattr(response_obj, 'message') and response_obj.message:
            logger.debug(f"✅ Extracted message from {type(response_obj).__name__} for {context_name}")
            return str(response_obj.message).strip()
        
        # Check for output attribute (some response formats)
        if hasattr(response_obj, 'output') and response_obj.output:
            logger.debug(f"✅ Extracted output from {type(response_obj).__name__} for {context_name}")
            return str(response_obj.output).strip()
        
        # For ResponseReasoningItem and similar objects, try string conversion as fallback
        response_str = str(response_obj)
        if response_str and not response_str.startswith(f"{type(response_obj).__name__}("):
            logger.debug(f"✅ String-converted {type(response_obj).__name__} for {context_name}")
            return response_str.strip()
        
        # Final fallback - log the object structure for debugging
        logger.warning(f"❓ Could not extract text from {type(response_obj).__name__} for {context_name}")
        logger.debug(f"📊 Object attributes: {[attr for attr in dir(response_obj) if not attr.startswith('_')]}")
        return ""
        
    except Exception as e:
        logger.error(f"💥 Exception in single object text extraction for {context_name}: {e}")
        return ""


def is_tool_call_response(response: Any) -> bool:
    """
    Check if a response contains tool calls.
    
    Args:
        response: Response object to check
        
    Returns:
        True if response contains tool calls, False otherwise
    """
    try:
        # Check ChatCompletion response format
        if hasattr(response, 'choices') and response.choices:
            message = response.choices[0].message
            if hasattr(message, 'tool_calls') and message.tool_calls:
                return True
            if hasattr(message, 'function_call') and message.function_call:
                return True
        
        # Check dict format (from perform_completion)
        if isinstance(response, dict) and response.get('tool_calls'):
            return True
        
        return False
        
    except Exception as e:
        logger.debug(f"Error checking tool calls: {e}")
        return False


def extract_tool_calls(response: Any) -> List[dict]:
    """
    Extract tool calls from a response.
    
    Args:
        response: Response object containing tool calls
        
    Returns:
        List of tool call dictionaries
    """
    try:
        # Handle dict format (from perform_completion)
        if isinstance(response, dict) and response.get('tool_calls'):
            return response['tool_calls']
        
        # Handle ChatCompletion response format
        if hasattr(response, 'choices') and response.choices:
            message = response.choices[0].message
            tool_calls = []
            
            # Handle newer tool_calls format
            if hasattr(message, 'tool_calls') and message.tool_calls:
                for tc in message.tool_calls:
                    tool_calls.append({
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                    })
            
            # Handle older function_call format
            elif hasattr(message, 'function_call') and message.function_call:
                tool_calls.append({
                    "function": {
                        "name": message.function_call.name,
                        "arguments": message.function_call.arguments,
                    }
                })
            
            return tool_calls
        
        return []
        
    except Exception as e:
        logger.error(f"Error extracting tool calls: {e}")
        return []