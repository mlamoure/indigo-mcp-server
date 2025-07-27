"""
LangSmith configuration and utilities for proper trace management.
This module provides centralized configuration for LangSmith tracing to ensure
that all operations are properly consolidated under single traces per question.
"""

import os
from typing import Optional, Dict, Any


class LangSmithConfig:
    """Centralized configuration for LangSmith tracing."""
    
    def __init__(self):
        self.enabled = self._get_enabled()
        self.endpoint = self._get_endpoint()
        self.api_key = self._get_api_key()
        self.project = self._get_project()
        self._setup_environment()
    
    def _get_enabled(self) -> bool:
        """Get whether LangSmith tracing is enabled."""
        return os.getenv("LANGSMITH_TRACING", "false").lower() == "true"
    
    def _get_endpoint(self) -> str:
        """Get the LangSmith endpoint URL."""
        return os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
    
    def _get_api_key(self) -> Optional[str]:
        """Get the LangSmith API key."""
        return os.getenv("LANGSMITH_API_KEY")
    
    def _get_project(self) -> Optional[str]:
        """Get the LangSmith project name."""
        return os.getenv("LANGSMITH_PROJECT")
    
    def _setup_environment(self):
        """Set up environment variables for LangSmith."""
        if self.enabled:
            # Set environment variables that LangSmith will use
            os.environ["LANGSMITH_TRACING"] = "true"
            if self.endpoint:
                os.environ["LANGSMITH_ENDPOINT"] = self.endpoint
            if self.api_key:
                os.environ["LANGSMITH_API_KEY"] = self.api_key
            if self.project:
                os.environ["LANGSMITH_PROJECT"] = self.project
            
            # Set additional configuration for better trace consolidation
            os.environ["LANGSMITH_TRACING_V2"] = "true"
    
    def get_metadata(self, session_id: str, question_text: str = "") -> Dict[str, Any]:
        """Get standardized metadata for traces."""
        metadata = {
            "session_id": session_id,
            "project": self.project,
            "tracing_enabled": self.enabled
        }
        
        if question_text:
            metadata["question"] = question_text[:200]  # Truncate for metadata
        
        return metadata
    
    def get_tags(self, additional_tags: Optional[list] = None) -> list:
        """Get standardized tags for traces."""
        base_tags = ["hello-indigo", "agent-system"]
        
        if additional_tags:
            base_tags.extend(additional_tags)
        
        return base_tags


# Global configuration instance
_langsmith_config = None

def get_langsmith_config() -> LangSmithConfig:
    """Get the global LangSmith configuration instance."""
    global _langsmith_config
    if _langsmith_config is None:
        _langsmith_config = LangSmithConfig()
    return _langsmith_config

def is_langsmith_enabled() -> bool:
    """Check if LangSmith tracing is enabled."""
    config = get_langsmith_config()
    return config.enabled

def get_langsmith_metadata(session_id: str, question_text: str = "") -> Dict[str, Any]:
    """Get standardized metadata for traces."""
    config = get_langsmith_config()
    return config.get_metadata(session_id, question_text)

def get_langsmith_tags(additional_tags: Optional[list] = None) -> list:
    """Get standardized tags for traces."""
    config = get_langsmith_config()
    return config.get_tags(additional_tags) 