"""
Security configuration for MCP server including access modes and SSL settings.
"""

import os
import logging
from typing import Optional, Dict, Any
from enum import Enum


class AccessMode(Enum):
    """Access modes for the MCP server."""
    LOCAL_ONLY = "local_only"
    REMOTE_ACCESS = "remote_access"


class SecurityConfig:
    """Manages security configuration for the MCP server."""
    
    def __init__(self, 
                 base_path: str,
                 access_mode: AccessMode = AccessMode.LOCAL_ONLY,
                 bearer_token: Optional[str] = None,
                 logger: Optional[logging.Logger] = None):
        """
        Initialize security configuration.
        
        Args:
            base_path: Base path for storing certificates and security data
            access_mode: Server access mode (local only or remote access)
            bearer_token: Bearer token for authentication
            logger: Optional logger instance
        """
        self.base_path = base_path
        self.access_mode = access_mode
        self.bearer_token = bearer_token
        self.logger = logger or logging.getLogger("Plugin")
        
        # Create base directory if it doesn't exist
        os.makedirs(base_path, exist_ok=True)
        
        # SSL certificate directory
        self.ssl_cert_dir = os.path.join(base_path, "ssl_certs")
        os.makedirs(self.ssl_cert_dir, exist_ok=True)
    
    def get_host_address(self) -> str:
        """
        Get the host address based on access mode.
        
        Returns:
            Host address string
        """
        if self.access_mode == AccessMode.LOCAL_ONLY:
            return "127.0.0.1"
        else:
            return "0.0.0.0"
    
    def is_ssl_enabled(self) -> bool:
        """
        Check if SSL should be enabled.
        
        Returns:
            False - SSL disabled for Claude Desktop compatibility with self-signed certificates
        """
        # SSL disabled for Claude Desktop compatibility - self-signed certs don't work
        # Original logic: return self.access_mode == AccessMode.REMOTE_ACCESS
        return False
    
    def get_server_url(self, port: int) -> str:
        """
        Get the complete server URL.
        
        Args:
            port: Server port number
            
        Returns:
            Complete server URL
        """
        protocol = "https" if self.is_ssl_enabled() else "http"
        host = self.get_host_address()
        return f"{protocol}://{host}:{port}"
    
    def get_client_url(self, port: int) -> str:
        """
        Get the client-accessible URL (for documentation).
        
        Args:
            port: Server port number
            
        Returns:
            Client-accessible URL
        """
        if self.access_mode == AccessMode.LOCAL_ONLY:
            return f"http://127.0.0.1:{port}"
        else:
            # For remote access, use the machine's actual hostname/IP
            return f"https://YOUR_SERVER_IP:{port}"
    
    def get_ssl_cert_dir(self) -> str:
        """
        Get the SSL certificate directory path.
        
        Returns:
            SSL certificate directory path
        """
        return self.ssl_cert_dir
    
    def get_claude_desktop_config(self, port: int) -> Dict[str, Any]:
        """
        Generate Claude Desktop configuration dictionary.
        
        Args:
            port: Server port number
            
        Returns:
            Dictionary containing Claude Desktop MCP configuration
        """
        client_url = self.get_client_url(port)
        
        config = {
            "mcpServers": {
                "indigo": {
                    "command": "npx",
                    "args": ["mcp-remote", client_url + "/mcp"]
                }
            }
        }
        
        # Add bearer token environment variable if authentication is enabled
        if self.bearer_token:
            config["mcpServers"]["indigo"]["env"] = {
                "BEARER_TOKEN": self.bearer_token
            }
        
        return config
    
    def get_status_info(self, port: int) -> Dict[str, Any]:
        """
        Get comprehensive status information for logging.
        
        Args:
            port: Server port number
            
        Returns:
            Dictionary containing status information
        """
        return {
            "access_mode": self.access_mode.value,
            "host_address": self.get_host_address(),
            "server_url": self.get_server_url(port),
            "client_url": self.get_client_url(port),
            "ssl_enabled": self.is_ssl_enabled(),
            "ssl_cert_dir": self.ssl_cert_dir,
            "bearer_token": self.bearer_token,
            "authentication_enabled": bool(self.bearer_token)
        }