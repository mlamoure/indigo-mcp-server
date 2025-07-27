####################
# MCP Server Plugin for Indigo Domotics
# Provides Model Context Protocol (MCP) support for AI assistants to interact with Indigo
####################

try:
    import indigo
except ImportError:
    pass

import asyncio
import json
import logging
import os
import sys
import threading
from typing import Dict, List, Optional, Any


from mcp.server.fastmcp import FastMCP

# Import our modules
from common.vector_store import VectorStore
from search_entities.search_tool import SearchEntitiesTool

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
        
        # FastMCP Server instance
        self.mcp_server = None
        self.mcp_thread = None
        self.vector_store = None
        self.search_tool = None
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
        
        # Initialize vector store
        try:
            db_path = os.path.join(
                indigo.server.getInstallFolderPath(),
                "Preferences/Plugins/com.vtmikel.mcp_server/vector_db"
            )
            self.vector_store = VectorStore(db_path, logger=self.logger)
            self.logger.info(f"Vector store initialized at: {db_path}")
        except Exception as e:
            self.logger.error(f"Failed to initialize vector store: {e}")
            return
        
        # Initialize search tool
        try:
            self.search_tool = SearchEntitiesTool(self.vector_store, logger=self.logger)
            self.logger.info("Search tool initialized")
        except Exception as e:
            self.logger.error(f"Failed to initialize search tool: {e}")
            return
        
        # Start MCP server
        self._start_mcp_server()
        
        # Initial vector store update
        self._update_vector_store()

    def shutdown(self) -> None:
        """
        Called when the plugin is being shut down.
        """
        self.logger.info("MCP Server plugin shutting down...")
        
        if self.mcp_server:
            # Stop the MCP server
            self._stop_mcp_server()
        
        if self.vector_store:
            self.vector_store.close()

    ########################################
    # MCP Server Management
    ########################################
    
    def _start_mcp_server(self) -> None:
        """Start the FastMCP server."""
        try:
            # Create FastMCP instance
            self.mcp_server = FastMCP("indigo-mcp-server")
            
            # Register tools and resources
            self._register_tools()
            self._register_resources()
            
            # Start server in separate thread
            self.mcp_thread = threading.Thread(
                target=self._run_mcp_server,
                daemon=True,
                name="FastMCP-Server-Thread"
            )
            self.mcp_thread.start()
            
            self.logger.info(f"FastMCP server started on port {self.server_port}")
            
        except Exception as e:
            self.logger.error(f"Failed to start FastMCP server: {e}")
    
    def _stop_mcp_server(self) -> None:
        """Stop the FastMCP server."""
        try:
            # Signal server to stop
            if hasattr(self, '_mcp_loop') and self._mcp_loop:
                self._mcp_loop.call_soon_threadsafe(self._mcp_loop.stop)
            
            # Wait for thread to finish
            if hasattr(self, 'mcp_thread') and self.mcp_thread and self.mcp_thread.is_alive():
                self.mcp_thread.join(timeout=5.0)
            
            self.logger.info("FastMCP server stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping FastMCP server: {e}")
    
    def _run_mcp_server(self) -> None:
        """Run the FastMCP server."""
        try:
            # Create new event loop for this thread
            self._mcp_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._mcp_loop)
            
            # Run the server (transport is handled by the SDK)
            self._mcp_loop.run_until_complete(
                self.mcp_server.run()
            )
            
        except Exception as e:
            self.logger.error(f"FastMCP server error: {e}")
        finally:
            if hasattr(self, '_mcp_loop'):
                self._mcp_loop.close()
    
    ########################################
    # MCP Tools Registration
    ########################################
    
    def _register_tools(self) -> None:
        """Register FastMCP tools."""
        
        @self.mcp_server.tool()
        def search_entities(query: str) -> str:
            """
            Search for Indigo devices, variables, and actions using natural language.
            
            Args:
                query: Natural language search query
                
            Returns:
                JSON string with search results
            """
            try:
                results = self.search_tool.search(query)
                return json.dumps(results, indent=2)
                
            except Exception as e:
                self.logger.error(f"Search error: {e}")
                return json.dumps({"error": str(e)})
    
    ########################################
    # MCP Resources Registration
    ########################################
    
    def _register_resources(self) -> None:
        """Register FastMCP resources for read-only access to Indigo entities."""
        
        @self.mcp_server.resource("devices")
        def list_devices() -> str:
            """List all Indigo devices."""
            try:
                devices = []
                for dev_id in indigo.devices:
                    dev = indigo.devices[dev_id]
                    devices.append({
                        "id": dev.id,
                        "name": dev.name,
                        "address": dev.address,
                        "enabled": dev.enabled,
                        "deviceTypeId": dev.deviceTypeId,
                        "states": dict(dev.states) if hasattr(dev, 'states') else {}
                    })
                
                return json.dumps(devices, indent=2)
                
            except Exception as e:
                self.logger.error(f"Error listing devices: {e}")
                return json.dumps({"error": str(e)})
        
        @self.mcp_server.resource("devices/{device_id}")
        def get_device(device_id: str) -> str:
            """Get details for a specific device."""
            try:
                dev_id = int(device_id)
                if dev_id in indigo.devices:
                    dev = indigo.devices[dev_id]
                    device_info = {
                        "id": dev.id,
                        "name": dev.name,
                        "address": dev.address,
                        "enabled": dev.enabled,
                        "deviceTypeId": dev.deviceTypeId,
                        "model": dev.model,
                        "protocol": dev.protocol,
                        "states": dict(dev.states) if hasattr(dev, 'states') else {},
                        "description": dev.description
                    }
                    return json.dumps(device_info, indent=2)
                else:
                    return json.dumps({"error": f"Device {device_id} not found"})
                    
            except Exception as e:
                self.logger.error(f"Error getting device {device_id}: {e}")
                return json.dumps({"error": str(e)})
        
        @self.mcp_server.resource("variables")
        def list_variables() -> str:
            """List all Indigo variables."""
            try:
                variables = []
                for var_id in indigo.variables:
                    var = indigo.variables[var_id]
                    variables.append({
                        "id": var.id,
                        "name": var.name,
                        "value": var.value,
                        "folderId": var.folderId
                    })
                
                return json.dumps(variables, indent=2)
                
            except Exception as e:
                self.logger.error(f"Error listing variables: {e}")
                return json.dumps({"error": str(e)})
        
        @self.mcp_server.resource("variables/{variable_id}")
        def get_variable(variable_id: str) -> str:
            """Get details for a specific variable."""
            try:
                var_id = int(variable_id)
                if var_id in indigo.variables:
                    var = indigo.variables[var_id]
                    variable_info = {
                        "id": var.id,
                        "name": var.name,
                        "value": var.value,
                        "folderId": var.folderId,
                        "readOnly": var.readOnly
                    }
                    return json.dumps(variable_info, indent=2)
                else:
                    return json.dumps({"error": f"Variable {variable_id} not found"})
                    
            except Exception as e:
                self.logger.error(f"Error getting variable {variable_id}: {e}")
                return json.dumps({"error": str(e)})
        
        @self.mcp_server.resource("actions")
        def list_actions() -> str:
            """List all Indigo action groups."""
            try:
                actions = []
                for action_id in indigo.actionGroups:
                    action = indigo.actionGroups[action_id]
                    actions.append({
                        "id": action.id,
                        "name": action.name,
                        "folderId": action.folderId
                    })
                
                return json.dumps(actions, indent=2)
                
            except Exception as e:
                self.logger.error(f"Error listing actions: {e}")
                return json.dumps({"error": str(e)})
        
        @self.mcp_server.resource("actions/{action_id}")
        def get_action(action_id: str) -> str:
            """Get details for a specific action group."""
            try:
                act_id = int(action_id)
                if act_id in indigo.actionGroups:
                    action = indigo.actionGroups[act_id]
                    action_info = {
                        "id": action.id,
                        "name": action.name,
                        "folderId": action.folderId,
                        "description": action.description if hasattr(action, 'description') else ""
                    }
                    return json.dumps(action_info, indent=2)
                else:
                    return json.dumps({"error": f"Action group {action_id} not found"})
                    
            except Exception as e:
                self.logger.error(f"Error getting action {action_id}: {e}")
                return json.dumps({"error": str(e)})
    
    ########################################
    # Vector Store Management
    ########################################
    
    def _update_vector_store(self) -> None:
        """Update the vector store with current Indigo entities."""
        try:
            self.logger.info("Updating vector store...")
            
            # Collect all entities
            devices_data = self._get_all_devices()
            variables_data = self._get_all_variables()
            actions_data = self._get_all_actions()
            
            # Update vector store
            self.vector_store.update_embeddings(
                devices=devices_data,
                variables=variables_data, 
                actions=actions_data
            )
            
            self.logger.info("Vector store update complete")
            
        except Exception as e:
            self.logger.error(f"Failed to update vector store: {e}")
    
    def _get_all_devices(self) -> List[Dict[str, Any]]:
        """Get all devices for vector store."""
        devices = []
        for dev_id in indigo.devices:
            dev = indigo.devices[dev_id]
            devices.append({
                "id": dev.id,
                "name": dev.name,
                "description": dev.description,
                "model": dev.model,
                "type": dev.deviceTypeId,
                "address": dev.address
            })
        return devices
    
    def _get_all_variables(self) -> List[Dict[str, Any]]:
        """Get all variables for vector store."""
        variables = []
        for var_id in indigo.variables:
            var = indigo.variables[var_id]
            variables.append({
                "id": var.id,
                "name": var.name,
                "value": var.value,
                "folderId": var.folderId
            })
        return variables
    
    def _get_all_actions(self) -> List[Dict[str, Any]]:
        """Get all action groups for vector store."""
        actions = []
        for action_id in indigo.actionGroups:
            action = indigo.actionGroups[action_id]
            actions.append({
                "id": action.id,
                "name": action.name,
                "folderId": action.folderId,
                "description": action.description if hasattr(action, 'description') else ""
            })
        return actions
    
    ########################################
    # Menu Actions
    ########################################
    
    def update_vector_store_menu(self) -> None:
        """Menu action to manually update the vector store."""
        self._update_vector_store()
    
    def show_mcp_status_menu(self) -> None:
        """Menu action to show FastMCP server status."""
        if self.mcp_server and self.mcp_thread and self.mcp_thread.is_alive():
            self.logger.info(f"FastMCP Server Status: Running on http://127.0.0.1:{self.server_port}")
            if self.vector_store:
                stats = self.vector_store.get_stats()
                self.logger.info(f"Vector Store Stats: {stats}")
        else:
            self.logger.info("FastMCP Server Status: Not running")
    
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
                # Restart FastMCP server with new configuration
                self.logger.info("Configuration changed, restarting FastMCP server...")
                self._stop_mcp_server()
                self._start_mcp_server()