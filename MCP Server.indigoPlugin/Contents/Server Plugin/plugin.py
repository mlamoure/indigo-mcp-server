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
        
        # InfluxDB configuration
        self.enable_influxdb = plugin_prefs.get("enable_influxdb", False)
        self.influx_url = plugin_prefs.get("influx_url", "http://localhost")
        self.influx_port = plugin_prefs.get("influx_port", "8086")
        self.influx_login = plugin_prefs.get("influx_login", "")
        self.influx_password = plugin_prefs.get("influx_password", "")
        self.influx_database = plugin_prefs.get("influx_database", "indigo")
        
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
    
    def test_connections(self) -> bool:
        """
        Test connections to required and optional services.
        
        Returns:
            True if all required connections are successful, False otherwise
        """
        self.logger.info("Testing service connections...")
        all_required_connections_ok = True
        
        # Test OpenAI API key (required)
        self.logger.info("Testing OpenAI API connection...")
        try:
            import openai
            
            # Validate API key format
            if not self.openai_api_key or self.openai_api_key == "xxxxx-xxxxx-xxxxx-xxxxx":
                self.logger.error("OpenAI API key is not configured or is placeholder")
                all_required_connections_ok = False
            else:
                # Set API key temporarily for testing
                test_client = openai.OpenAI(api_key=self.openai_api_key)
                
                # Make a minimal API call to test connectivity
                try:
                    # Use a very small embedding request to test the connection
                    response = test_client.embeddings.create(
                        model="text-embedding-3-small",
                        input="test",
                        timeout=10.0
                    )
                    if response and response.data:
                        self.logger.info("✅ OpenAI API connection successful")
                    else:
                        self.logger.error("❌ OpenAI API returned invalid response")
                        all_required_connections_ok = False
                except Exception as api_error:
                    self.logger.error(f"❌ OpenAI API connection failed: {api_error}")
                    all_required_connections_ok = False
                    
        except ImportError:
            self.logger.error("❌ OpenAI library not available")
            all_required_connections_ok = False
        except Exception as e:
            self.logger.error(f"❌ OpenAI connection test failed: {e}")
            all_required_connections_ok = False
        
        # Test InfluxDB connection (optional, only if enabled)
        if self.enable_influxdb:
            self.logger.info("Testing InfluxDB connection...")
            try:
                from influxdb import InfluxDBClient
                
                # Validate InfluxDB configuration
                if not self.influx_url or not self.influx_port:
                    self.logger.warning("⚠️ InfluxDB enabled but URL or port not configured")
                else:
                    try:
                        port = int(self.influx_port)
                        client = InfluxDBClient(
                            host=self.influx_url.replace("http://", "").replace("https://", ""),
                            port=port,
                            username=self.influx_login if self.influx_login else None,
                            password=self.influx_password if self.influx_password else None,
                            database=self.influx_database,
                            timeout=10
                        )
                        
                        # Test connection with ping
                        result = client.ping()
                        if result:
                            self.logger.info("✅ InfluxDB connection successful")
                            
                            # Test database access
                            try:
                                client.get_list_database()
                                self.logger.info("✅ InfluxDB database access successful")
                            except Exception as db_error:
                                self.logger.warning(f"⚠️ InfluxDB database access failed: {db_error}")
                                
                        else:
                            self.logger.warning("⚠️ InfluxDB ping failed - historical data analysis will be unavailable")
                            
                        client.close()
                        
                    except ValueError as ve:
                        self.logger.warning(f"⚠️ InfluxDB port configuration error: {ve}")
                    except Exception as influx_error:
                        self.logger.warning(f"⚠️ InfluxDB connection failed: {influx_error}")
                        self.logger.warning("Historical data analysis will be unavailable")
                        
            except ImportError:
                self.logger.warning("⚠️ InfluxDB library not available - historical data analysis will be unavailable")
            except Exception as e:
                self.logger.warning(f"⚠️ InfluxDB connection test failed: {e}")
        else:
            self.logger.info("InfluxDB disabled - historical data analysis will not be available")
        
        return all_required_connections_ok

    ########################################
    def startup(self) -> None:
        """
        Called after __init__ when the plugin is starting up.
        """
        self.logger.info("MCP Server plugin starting up...")
        
        # Test connections before proceeding
        if not self.test_connections():
            self.logger.error("Required service connections failed. Plugin startup aborted.")
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
            
        # Set InfluxDB environment variables if enabled
        if self.enable_influxdb:
            os.environ["INFLUXDB_HOST"] = self.influx_url.replace("http://", "").replace("https://", "")
            os.environ["INFLUXDB_PORT"] = str(self.influx_port)
            os.environ["INFLUXDB_USERNAME"] = self.influx_login
            os.environ["INFLUXDB_PASSWORD"] = self.influx_password
            os.environ["INFLUXDB_DATABASE"] = self.influx_database
            os.environ["INFLUXDB_ENABLED"] = "true"
            self.logger.info("InfluxDB environment variables configured")
        else:
            os.environ["INFLUXDB_ENABLED"] = "false"
            
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
        
        # Validate log level
        try:
            log_level = int(values_dict.get("log_level", 20))
            if log_level not in [5, 10, 20, 30, 40, 50]:
                errors_dict["log_level"] = "Invalid log level"
        except (ValueError, TypeError):
            errors_dict["log_level"] = "Log level must be a valid number"
        
        # Validate InfluxDB configuration if enabled
        if values_dict.get("enable_influxdb", False):
            influx_url = values_dict.get("influx_url", "").strip()
            influx_port = values_dict.get("influx_port", "").strip()
            influx_database = values_dict.get("influx_database", "").strip()
            
            if not influx_url:
                errors_dict["influx_url"] = "InfluxDB URL is required when InfluxDB is enabled"
            elif not (influx_url.startswith("http://") or influx_url.startswith("https://")):
                errors_dict["influx_url"] = "InfluxDB URL must start with http:// or https://"
            
            if not influx_port:
                errors_dict["influx_port"] = "InfluxDB port is required when InfluxDB is enabled"
            else:
                try:
                    port = int(influx_port)
                    if port < 1 or port > 65535:
                        errors_dict["influx_port"] = "InfluxDB port must be between 1 and 65535"
                except (ValueError, TypeError):
                    errors_dict["influx_port"] = "InfluxDB port must be a valid number"
            
            if not influx_database:
                errors_dict["influx_database"] = "InfluxDB database name is required when InfluxDB is enabled"
        
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
            log_level = int(values_dict.get("log_level", 20))
            self.logger.setLevel(log_level)
            
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
            
            # InfluxDB configuration
            new_enable_influxdb = values_dict.get("enable_influxdb", False)
            new_influx_url = values_dict.get("influx_url", "http://localhost")
            new_influx_port = values_dict.get("influx_port", "8086")
            new_influx_login = values_dict.get("influx_login", "")
            new_influx_password = values_dict.get("influx_password", "")
            new_influx_database = values_dict.get("influx_database", "indigo")
            
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
            
            # Check InfluxDB configuration changes
            if (new_enable_influxdb != self.enable_influxdb or
                new_influx_url != self.influx_url or
                new_influx_port != self.influx_port or
                new_influx_login != self.influx_login or
                new_influx_password != self.influx_password or
                new_influx_database != self.influx_database):
                
                self.enable_influxdb = new_enable_influxdb
                self.influx_url = new_influx_url
                self.influx_port = new_influx_port
                self.influx_login = new_influx_login
                self.influx_password = new_influx_password
                self.influx_database = new_influx_database
                
                # Update InfluxDB environment variables
                if self.enable_influxdb:
                    os.environ["INFLUXDB_HOST"] = self.influx_url.replace("http://", "").replace("https://", "")
                    os.environ["INFLUXDB_PORT"] = str(self.influx_port)
                    os.environ["INFLUXDB_USERNAME"] = self.influx_login
                    os.environ["INFLUXDB_PASSWORD"] = self.influx_password
                    os.environ["INFLUXDB_DATABASE"] = self.influx_database
                    os.environ["INFLUXDB_ENABLED"] = "true"
                else:
                    os.environ["INFLUXDB_ENABLED"] = "false"
                
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