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
from common.vector_store_manager import VectorStoreManager
from interfaces.indigo_data_provider import IndigoDataProvider
from mcp_server.core import MCPServerCore

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
        
        # Component instances
        self.data_provider = None
        self.vector_store_manager = None
        self.mcp_server_core = None
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
        
        # Set OpenAI API key in environment for the modules to use
        os.environ["OPENAI_API_KEY"] = self.openai_api_key
        
        # Initialize data provider
        try:
            self.data_provider = IndigoDataProvider(logger=self.logger)
            self.logger.info("Data provider initialized")
        except Exception as e:
            self.logger.error(f"Failed to initialize data provider: {e}")
            return
        
        # Initialize vector store manager
        try:
            db_path = os.path.join(
                indigo.server.getInstallFolderPath(),
                "Preferences/Plugins/com.vtmikel.mcp_server/vector_db"
            )
            self.vector_store_manager = VectorStoreManager(
                data_provider=self.data_provider,
                db_path=db_path,
                logger=self.logger,
                update_interval=300  # 5 minutes
            )
            self.vector_store_manager.start()
            self.logger.info("Vector store manager started")
        except Exception as e:
            self.logger.error(f"Failed to initialize vector store manager: {e}")
            return
        
        # Initialize and start MCP server
        try:
            self.mcp_server_core = MCPServerCore(
                data_provider=self.data_provider,
                vector_store=self.vector_store_manager.get_vector_store(),
                server_name="indigo-mcp-server",
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
        
        if self.vector_store_manager:
            self.vector_store_manager.stop()

    
    
    
    
    ########################################
    # Menu Actions
    ########################################
    
    def show_mcp_status_menu(self) -> None:
        """Menu action to show MCP server status."""
        if self.mcp_server_core and self.mcp_server_core.is_running:
            self.logger.info(f"MCP Server Status: Running on http://127.0.0.1:{self.server_port}")
            if self.vector_store_manager:
                stats = self.vector_store_manager.get_stats()
                self.logger.info(f"Vector Store Stats: {stats}")
        else:
            self.logger.info("MCP Server Status: Not running")
    
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
            
            # Check if API key or port changed
            new_api_key = values_dict.get("openai_api_key", "")
            new_port = int(values_dict.get("server_port", 8080))
            
            restart_needed = False
            
            if new_api_key != self.openai_api_key:
                self.openai_api_key = new_api_key
                os.environ["OPENAI_API_KEY"] = self.openai_api_key
                restart_needed = True
                
            if new_port != self.server_port:
                self.server_port = new_port
                restart_needed = True
                
            if restart_needed:
                # Restart MCP server with new configuration
                self.logger.info("Configuration changed, restarting MCP server...")
                if self.mcp_server_core:
                    self.mcp_server_core.stop()
                    # Reinitialize with new configuration
                    self.mcp_server_core = MCPServerCore(
                        data_provider=self.data_provider,
                        vector_store=self.vector_store_manager.get_vector_store(),
                        server_name="indigo-mcp-server",
                        logger=self.logger
                    )
                    self.mcp_server_core.start()