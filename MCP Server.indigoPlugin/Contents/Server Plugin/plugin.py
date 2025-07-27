####################
# MCP Server Plugin for Indigo Domotics
# Provides Model Context Protocol (MCP) support for AI assistants to interact with Indigo
####################

try:
    import indigo
except ImportError:
    pass

import logging
import os
from typing import Optional

# Import our modules
from mcp_server.adapters.indigo_data_provider import IndigoDataProvider
from mcp_server.core import MCPServerCore
from mcp_server.common.openai_client.langsmith_config import get_langsmith_config
from mcp_server.security import AuthManager, AccessMode

################################################################################
class Plugin(indigo.PluginBase):
    ########################################
    def __init__(
            self,
            plugin_id: str,
            plugin_display_name: str,
            plugin_version: str,
            plugin_prefs: indigo.Dict,
            **kwargs: dict
    ) -> None:
        """
        Initialize the MCP Server plugin.
        
        :param plugin_id: the ID string of the plugin from Info.plist
        :param plugin_display_name: the name string of the plugin from Info.plist
        :param plugin_version: the version string from Info.plist
        :param plugin_prefs: an indigo.Dict containing the prefs for the plugin
        :param kwargs: passthrough for any other keyword args
        """
        super().__init__(plugin_id, plugin_display_name, plugin_version, plugin_prefs, **kwargs)
        
        # Plugin configuration
        self.debug = plugin_prefs.get("showDebugInfo", False)
        self.openai_api_key = plugin_prefs.get("openai_api_key", "")
        self.large_model = plugin_prefs.get("large_model", "gpt-4o")
        self.small_model = plugin_prefs.get("small_model", "gpt-4o-mini")
        
        # LangSmith configuration
        self.enable_langsmith = plugin_prefs.get("enable_langsmith", False)
        self.langsmith_endpoint = plugin_prefs.get("langsmith_endpoint", "https://api.smith.langchain.com")
        self.langsmith_api_key = plugin_prefs.get("langsmith_api_key", "")
        self.langsmith_project = plugin_prefs.get("langsmith_project", "")
        
        # Security configuration
        self.access_mode = plugin_prefs.get("access_mode", "local_only")
        self.bearer_token = plugin_prefs.get("bearer_token", "")
        
        # Component instances
        self.data_provider = None
        self.mcp_server_core = None
        self.auth_manager = AuthManager(logger=self.logger)
        self.server_port = plugin_prefs.get("server_port", 8080)
        
        # Set up logging
        self.logger.setLevel(logging.DEBUG if self.debug else logging.INFO)

    ########################################
    def startup(self) -> None:
        """
        Called after __init__ when the plugin is starting up.
        """
        self.logger.info("MCP Server plugin starting up...")
        
        # Validate configuration
        if not self.openai_api_key or self.openai_api_key == "xxxxx-xxxxx-xxxxx-xxxxx":
            self.logger.error("OpenAI API key not configured. Please set it in plugin configuration.")
            return
        
        # Generate bearer token if not set
        if not self.bearer_token:
            self.bearer_token = self.auth_manager.generate_bearer_token()
            # Save to plugin preferences
            plugin_prefs = self.pluginPrefs
            plugin_prefs["bearer_token"] = self.bearer_token
            self.logger.info("Generated new bearer token for MCP server authentication")
        
        # Set OpenAI API key in environment for the modules to use
        os.environ["OPENAI_API_KEY"] = self.openai_api_key
        
        # Set model environment variables
        os.environ["LARGE_MODEL"] = self.large_model
        os.environ["SMALL_MODEL"] = self.small_model
        os.environ["OPENAI_EMBEDDING_MODEL"] = "text-embedding-3-small"
        
        # Set LangSmith environment variables
        if self.enable_langsmith:
            os.environ["LANGSMITH_TRACING"] = "true"
            os.environ["LANGSMITH_ENDPOINT"] = self.langsmith_endpoint
            os.environ["LANGSMITH_API_KEY"] = self.langsmith_api_key
            os.environ["LANGSMITH_PROJECT"] = self.langsmith_project
        else:
            os.environ["LANGSMITH_TRACING"] = "false"
            
        # Initialize LangSmith configuration
        self.langsmith_config = get_langsmith_config()
        
        # Set DB_FILE environment variable for vector store
        db_path = os.path.join(
            indigo.server.getInstallFolderPath(),
            "Preferences/Plugins/com.vtmikel.mcp_server/vector_db"
        )
        os.environ["DB_FILE"] = db_path
        
        # Initialize data provider
        try:
            self.data_provider = IndigoDataProvider(logger=self.logger)
            self.logger.info("Data provider initialized")
        except Exception as e:
            self.logger.error(f"Failed to initialize data provider: {e}")
            return
        
        # Initialize and start MCP server
        try:
            # Convert access mode string to enum
            access_mode = AccessMode.REMOTE_ACCESS if self.access_mode == "remote_access" else AccessMode.LOCAL_ONLY
            
            self.mcp_server_core = MCPServerCore(
                data_provider=self.data_provider,
                server_name="indigo-mcp-server",
                port=self.server_port,
                access_mode=access_mode,
                bearer_token=self.bearer_token,
                logger=self.logger
            )
            self.mcp_server_core.start()
            self.logger.info("MCP server core started")
        except Exception as e:
            self.logger.error(f"Failed to start MCP server core: {e}")
            return

    def shutdown(self) -> None:
        """
        Called when the plugin is being shut down.
        """
        self.logger.info("MCP Server plugin shutting down...")
        
        if self.mcp_server_core:
            self.mcp_server_core.stop()

    
    
    
    
    ########################################
    # Menu Actions
    ########################################
    
    def show_mcp_status_menu(self) -> None:
        """Menu action to show MCP server status."""
        if self.mcp_server_core and self.mcp_server_core.is_running:
            security_config = self.mcp_server_core.get_security_config()
            status_info = security_config.get_status_info(self.server_port)
            
            status_lines = [
                f"MCP Server Status: Running",
                f"  Server URL: {status_info['server_url']}",
                f"  Access Mode: {status_info['access_mode'].replace('_', ' ').title()}",
                f"  SSL Enabled: {status_info['ssl_enabled']}",
                f"  Authentication: {'Enabled' if status_info['authentication_enabled'] else 'Disabled'}"
            ]
            
            if hasattr(self.mcp_server_core, 'vector_store_manager'):
                stats = self.mcp_server_core.vector_store_manager.get_stats()
                status_lines.append(f"  Vector Store Stats: {stats}")
            
            self.logger.info("\n".join(status_lines))
        else:
            self.logger.info("MCP Server Status: Not running")
    
    def regenerate_bearer_token_menu(self) -> None:
        """Menu action to regenerate bearer token."""
        try:
            # Generate new token
            new_token = self.auth_manager.generate_bearer_token()
            
            # Update instance variable
            self.bearer_token = new_token
            
            # Save to plugin preferences
            plugin_prefs = self.pluginPrefs
            plugin_prefs["bearer_token"] = new_token
            
            self.logger.info(f"New bearer token generated: {new_token}")
            self.logger.info("Restart the plugin to apply the new token to the MCP server")
            
        except Exception as e:
            self.logger.error(f"Failed to regenerate bearer token: {e}")
    
    def regenerate_bearer_token_button(self, values_dict: indigo.Dict) -> indigo.Dict:
        """Button action to regenerate bearer token."""
        try:
            # Generate new token
            new_token = self.auth_manager.generate_bearer_token()
            
            # Update values dict
            values_dict["bearer_token"] = new_token
            
            self.logger.info("New bearer token generated")
            
        except Exception as e:
            self.logger.error(f"Failed to regenerate bearer token: {e}")
        
        return values_dict
    
    ########################################
    # Configuration UI Validation
    ########################################
    
    def validatePrefsConfigUi(self, values_dict: indigo.Dict) -> tuple:
        """
        Validate plugin configuration.
        
        :param values_dict: the values dictionary to validate
        :return: (True/False, values_dict, errors_dict)
        """
        errors_dict = indigo.Dict()
        
        # Validate OpenAI API key
        api_key = values_dict.get("openai_api_key", "")
        if not api_key or api_key == "xxxxx-xxxxx-xxxxx-xxxxx":
            errors_dict["openai_api_key"] = "Please enter a valid OpenAI API key"
        
        # Validate server port
        try:
            port = int(values_dict.get("server_port", 8080))
            if port < 1024 or port > 65535:
                errors_dict["server_port"] = "Port must be between 1024 and 65535"
        except (ValueError, TypeError):
            errors_dict["server_port"] = "Port must be a valid number"
        
        return (len(errors_dict) == 0, values_dict, errors_dict)
    
    def closedPrefsConfigUi(self, values_dict: indigo.Dict, user_cancelled: bool) -> None:
        """
        Called when the plugin configuration dialog is closed.
        
        :param values_dict: the values dictionary
        :param user_cancelled: True if the user cancelled the dialog
        """
        if not user_cancelled:
            # Update configuration
            self.debug = values_dict.get("showDebugInfo", False)
            self.logger.setLevel(logging.DEBUG if self.debug else logging.INFO)
            
            # Check if API key, models, LangSmith, security, or port changed
            new_api_key = values_dict.get("openai_api_key", "")
            new_large_model = values_dict.get("large_model", "gpt-4o")
            new_small_model = values_dict.get("small_model", "gpt-4o-mini")
            new_port = int(values_dict.get("server_port", 8080))
            
            # Security configuration
            new_access_mode = values_dict.get("access_mode", "local_only")
            new_bearer_token = values_dict.get("bearer_token", "")
            
            # LangSmith configuration
            new_enable_langsmith = values_dict.get("enable_langsmith", False)
            new_langsmith_endpoint = values_dict.get("langsmith_endpoint", "https://api.smith.langchain.com")
            new_langsmith_api_key = values_dict.get("langsmith_api_key", "")
            new_langsmith_project = values_dict.get("langsmith_project", "")
            
            restart_needed = False
            
            if new_api_key != self.openai_api_key:
                self.openai_api_key = new_api_key
                os.environ["OPENAI_API_KEY"] = self.openai_api_key
                restart_needed = True
                
            if new_large_model != self.large_model:
                self.large_model = new_large_model
                os.environ["LARGE_MODEL"] = self.large_model
                restart_needed = True
                
            if new_small_model != self.small_model:
                self.small_model = new_small_model
                os.environ["SMALL_MODEL"] = self.small_model
                restart_needed = True
                
            if new_port != self.server_port:
                self.server_port = new_port
                restart_needed = True
                
            # Check security configuration changes
            if new_access_mode != self.access_mode:
                self.access_mode = new_access_mode
                restart_needed = True
                
            if new_bearer_token != self.bearer_token:
                self.bearer_token = new_bearer_token
                restart_needed = True
                
            # Check LangSmith configuration changes
            if (new_enable_langsmith != self.enable_langsmith or
                new_langsmith_endpoint != self.langsmith_endpoint or
                new_langsmith_api_key != self.langsmith_api_key or
                new_langsmith_project != self.langsmith_project):
                
                self.enable_langsmith = new_enable_langsmith
                self.langsmith_endpoint = new_langsmith_endpoint
                self.langsmith_api_key = new_langsmith_api_key
                self.langsmith_project = new_langsmith_project
                
                # Update LangSmith environment variables
                if self.enable_langsmith:
                    os.environ["LANGSMITH_TRACING"] = "true"
                    os.environ["LANGSMITH_ENDPOINT"] = self.langsmith_endpoint
                    os.environ["LANGSMITH_API_KEY"] = self.langsmith_api_key
                    os.environ["LANGSMITH_PROJECT"] = self.langsmith_project
                else:
                    os.environ["LANGSMITH_TRACING"] = "false"
                
                # Reinitialize LangSmith configuration with new settings
                self.langsmith_config = get_langsmith_config()
                
                restart_needed = True
                
            if restart_needed:
                # Restart MCP server with new configuration
                self.logger.info("Configuration changed, restarting MCP server...")
                if self.mcp_server_core:
                    self.mcp_server_core.stop()
                    # Reinitialize with new configuration
                    access_mode = AccessMode.REMOTE_ACCESS if self.access_mode == "remote_access" else AccessMode.LOCAL_ONLY
                    self.mcp_server_core = MCPServerCore(
                        data_provider=self.data_provider,
                        server_name="indigo-mcp-server",
                        port=self.server_port,
                        access_mode=access_mode,
                        bearer_token=self.bearer_token,
                        logger=self.logger
                    )
                    self.mcp_server_core.start()