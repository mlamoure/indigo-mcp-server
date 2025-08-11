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

import openai

# Import our modules
from mcp_server.adapters.indigo_data_provider import IndigoDataProvider
from mcp_server.common.openai_client.langsmith_config import get_langsmith_config
from mcp_server.core import MCPServerCore
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
        **kwargs: dict,
    ) -> None:
        """
        Initialize the MCP Server plugin.

        :param plugin_id: the ID string of the plugin from Info.plist
        :param plugin_display_name: the name string of the plugin from Info.plist
        :param plugin_version: the version string from Info.plist
        :param plugin_prefs: an indigo.Dict containing the prefs for the plugin
        :param kwargs: passthrough for any other keyword args
        """
        super().__init__(
            plugin_id, plugin_display_name, plugin_version, plugin_prefs, **kwargs
        )

        # Plugin configuration
        self.openai_api_key = plugin_prefs.get("openai_api_key", "")
        self.large_model = plugin_prefs.get("large_model", "gpt-5")
        self.small_model = plugin_prefs.get("small_model", "gpt-5-mini")

        # LangSmith configuration
        self.enable_langsmith = plugin_prefs.get("enable_langsmith", False)
        self.langsmith_endpoint = plugin_prefs.get(
            "langsmith_endpoint", "https://api.smith.langchain.com"
        )
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

        # Device management
        self.mcp_server_device = None

        # Set up logging properly
        self.log_level = int(plugin_prefs.get("log_level", logging.INFO))
        self.indigo_log_handler.setLevel(self.log_level)
        self.plugin_file_handler.setLevel(self.log_level)
        logging.getLogger("Plugin").setLevel(self.log_level)

    def test_connections(self) -> bool:
        """
        Test connections to required and optional services.

        Returns:
            True if all required connections are successful, False otherwise
        """
        all_required_connections_ok = True

        # Test OpenAI API key (required)
        self.logger.info("Testing OpenAI API connection...")
        try:

            # Validate API key format
            if (
                not self.openai_api_key
                or self.openai_api_key == "xxxxx-xxxxx-xxxxx-xxxxx"
            ):
                self.logger.error("OpenAI API key is not configured or is placeholder")
                all_required_connections_ok = False
            else:
                # Set API key temporarily for testing
                test_client = openai.OpenAI(api_key=self.openai_api_key)

                # Make a minimal API call to test connectivity
                try:
                    # Use a very small embedding request to test the connection
                    response = test_client.embeddings.create(
                        model="text-embedding-3-small", input="test", timeout=10.0
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
                    self.logger.warning(
                        "⚠️ InfluxDB enabled but URL or port not configured"
                    )
                else:
                    try:
                        port = int(self.influx_port)
                        client = InfluxDBClient(
                            host=self.influx_url.replace("http://", "").replace(
                                "https://", ""
                            ),
                            port=port,
                            username=self.influx_login if self.influx_login else None,
                            password=(
                                self.influx_password if self.influx_password else None
                            ),
                            database=self.influx_database,
                            timeout=10,
                        )

                        # Test connection with ping
                        result = client.ping()
                        if result:
                            self.logger.info("✅ InfluxDB connection successful")

                            # Test database access
                            try:
                                client.get_list_database()
                                self.logger.info(
                                    "✅ InfluxDB database access successful"
                                )
                            except Exception as db_error:
                                self.logger.warning(
                                    f"⚠️ InfluxDB database access failed: {db_error}"
                                )

                        else:
                            self.logger.warning(
                                "⚠️ InfluxDB ping failed - historical data analysis will be unavailable"
                            )

                        client.close()

                    except ValueError as ve:
                        self.logger.warning(
                            f"⚠️ InfluxDB port configuration error: {ve}"
                        )
                    except Exception as influx_error:
                        self.logger.warning(
                            f"⚠️ InfluxDB connection failed: {influx_error}"
                        )
                        self.logger.warning(
                            "Historical data analysis will be unavailable"
                        )

            except ImportError:
                self.logger.warning(
                    "⚠️ InfluxDB library not available - historical data analysis will be unavailable"
                )
            except Exception as e:
                self.logger.warning(f"⚠️ InfluxDB connection test failed: {e}")
        else:
            self.logger.info(
                "InfluxDB disabled - historical data analysis will not be available"
            )

        return all_required_connections_ok

    ########################################
    def startup(self) -> None:
        """
        Called after __init__ when the plugin is starting up.
        """
        self.logger.info("MCP Server plugin starting up...")

        # Test connections before proceeding
        if not self.test_connections():
            self.logger.error(
                "Required service connections failed. Plugin startup aborted."
            )
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
            os.environ["INFLUXDB_HOST"] = self.influx_url.replace(
                "http://", ""
            ).replace("https://", "")
            os.environ["INFLUXDB_PORT"] = str(self.influx_port)
            os.environ["INFLUXDB_USERNAME"] = self.influx_login
            os.environ["INFLUXDB_PASSWORD"] = self.influx_password
            os.environ["INFLUXDB_DATABASE"] = self.influx_database
            os.environ["INFLUXDB_ENABLED"] = "true"
        else:
            os.environ["INFLUXDB_ENABLED"] = "false"

        # Initialize LangSmith configuration
        self.langsmith_config = get_langsmith_config()

        # Set DB_FILE environment variable for vector store
        db_path = os.path.join(
            indigo.server.getInstallFolderPath(),
            "Preferences/Plugins/com.vtmikel.mcp_server/vector_db",
        )
        os.environ["DB_FILE"] = db_path

        # Initialize data provider
        try:
            self.data_provider = IndigoDataProvider(logger=self.logger)
        except Exception as e:
            self.logger.error(f"Failed to initialize data provider: {e}")
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

    def show_mcp_client_info_menu(self) -> None:
        """Menu action to show Claude Desktop MCP client connection information."""
        if self.mcp_server_core and self.mcp_server_core.is_running:
            security_config = self.mcp_server_core.get_security_config()
            claude_config = security_config.get_claude_desktop_config(self.server_port)
            
            import json
            config_json = json.dumps(claude_config, indent=2)
            
            config_lines = [
                "Claude Desktop MCP Client Connection Information:",
                "",
                "Add the following configuration to your claude_desktop_config.json file:",
                "",
                config_json
            ]
            
            self.logger.info("\n".join(config_lines))
        else:
            self.logger.info("MCP Server is not running - start an MCP Server device first")

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
            self.logger.info(
                "Restart the plugin to apply the new token to the MCP server"
            )

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

    def test_connections_button(self, values_dict: indigo.Dict) -> indigo.Dict:
        """Button action to test connections with current configuration values."""
        self.logger.info("Testing connections with current configuration...")

        # Temporarily update instance variables with dialog values for testing
        old_api_key = self.openai_api_key
        old_enable_influxdb = self.enable_influxdb
        old_influx_url = self.influx_url
        old_influx_port = self.influx_port
        old_influx_login = self.influx_login
        old_influx_password = self.influx_password
        old_influx_database = self.influx_database

        try:
            # Apply values from dialog temporarily
            self.openai_api_key = values_dict.get("openai_api_key", "")
            self.enable_influxdb = values_dict.get("enable_influxdb", False)
            self.influx_url = values_dict.get("influx_url", "http://localhost")
            self.influx_port = values_dict.get("influx_port", "8086")
            self.influx_login = values_dict.get("influx_login", "")
            self.influx_password = values_dict.get("influx_password", "")
            self.influx_database = values_dict.get("influx_database", "indigo")

            # Test connections
            connections_ok = self.test_connections()

            if connections_ok:
                self.logger.info("✅ All required connections tested successfully!")
            else:
                self.logger.error(
                    "❌ Some required connections failed. Please check the logs above."
                )

        finally:
            # Restore original values
            self.openai_api_key = old_api_key
            self.enable_influxdb = old_enable_influxdb
            self.influx_url = old_influx_url
            self.influx_port = old_influx_port
            self.influx_login = old_influx_login
            self.influx_password = old_influx_password
            self.influx_database = old_influx_database

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
                errors_dict["influx_url"] = (
                    "InfluxDB URL is required when InfluxDB is enabled"
                )
            elif not (
                influx_url.startswith("http://") or influx_url.startswith("https://")
            ):
                errors_dict["influx_url"] = (
                    "InfluxDB URL must start with http:// or https://"
                )

            if not influx_port:
                errors_dict["influx_port"] = (
                    "InfluxDB port is required when InfluxDB is enabled"
                )
            else:
                try:
                    port = int(influx_port)
                    if port < 1 or port > 65535:
                        errors_dict["influx_port"] = (
                            "InfluxDB port must be between 1 and 65535"
                        )
                except (ValueError, TypeError):
                    errors_dict["influx_port"] = "InfluxDB port must be a valid number"

            if not influx_database:
                errors_dict["influx_database"] = (
                    "InfluxDB database name is required when InfluxDB is enabled"
                )

        return (len(errors_dict) == 0, values_dict, errors_dict)

    ########################################
    # Device Management
    ########################################

    def deviceStartComm(self, device: indigo.Device) -> None:
        """
        Called when a device should start communication.
        """
        if device.deviceTypeId == "mcpServer":
            self._start_mcp_server_from_device(device)

    def deviceStopComm(self, device: indigo.Device) -> None:
        """
        Called when a device should stop communication.
        """
        if device.deviceTypeId == "mcpServer":
            self.logger.info(
                f"Stopping communication for MCP Server device: {device.name}"
            )
            self._stop_mcp_server_from_device(device)

    def deviceUpdated(self, origDev: indigo.Device, newDev: indigo.Device) -> None:
        """
        Called when a device configuration is updated.
        """
        if newDev.deviceTypeId == "mcpServer":
            changes = []
            
            # Check property changes (actual configuration)
            for key in newDev.pluginProps:
                old_val = origDev.pluginProps.get(key)
                new_val = newDev.pluginProps.get(key)
                if old_val != new_val:
                    changes.append(f"property '{key}': '{old_val}' → '{new_val}'")
            
            # Check state changes (runtime status)
            for key in newDev.states:
                if key in origDev.states:
                    old_val = origDev.states[key]
                    new_val = newDev.states[key]
                    if old_val != new_val:
                        changes.append(f"state '{key}': '{old_val}' → '{new_val}'")
            
            # Check device name change
            if origDev.name != newDev.name:
                changes.append(f"device name: '{origDev.name}' → '{newDev.name}'")
            
            # Log specific changes at debug level
            if changes:
                self.logger.debug(f"MCP Server device '{newDev.name}' updated: {', '.join(changes)}")

            # Check if access mode changed (keep at INFO level - important configuration change)
            old_access_mode = origDev.pluginProps.get(
                "server_access_mode", "local_only"
            )
            new_access_mode = newDev.pluginProps.get("server_access_mode", "local_only")

            # Check if server port changed
            old_server_port = origDev.pluginProps.get("serverPort")
            new_server_port = newDev.pluginProps.get("serverPort")

            if old_access_mode != new_access_mode:
                self.logger.info(
                    f"Access mode changed from {old_access_mode} to {new_access_mode}, restarting server"
                )
                self._restart_mcp_server_from_device(newDev)
            elif old_server_port != new_server_port:
                self.logger.info(
                    f"Server port changed from {old_server_port} to {new_server_port}, restarting server"
                )
                self._restart_mcp_server_from_device(newDev)

            # Update device name if it changed
            if origDev.name != newDev.name:
                newDev.updateStateOnServer(key="serverName", value=newDev.name)

    def validateDeviceConfigUi(
        self, valuesDict: indigo.Dict, typeId: str, devId: int
    ) -> tuple:
        """
        Validate device configuration.
        """
        errors_dict = indigo.Dict()

        if typeId == "mcpServer":
            # Enforce single MCP Server device
            if self._count_mcp_server_devices(exclude_id=devId) > 0:
                errors_dict["serverName"] = (
                    "Only one MCP Server device is allowed per plugin"
                )

            # Validate server name
            server_name = valuesDict.get("serverName", "").strip()
            if not server_name:
                errors_dict["serverName"] = "Server name is required"

            # Validate server port
            server_port = valuesDict.get("serverPort", "").strip()
            if not server_port:
                errors_dict["serverPort"] = "Server port is required"
            else:
                try:
                    port = int(server_port)
                    if port < 1024 or port > 65535:
                        errors_dict["serverPort"] = "Port must be between 1024 and 65535"
                except (ValueError, TypeError):
                    errors_dict["serverPort"] = "Port must be a valid number"

        return (len(errors_dict) == 0, valuesDict, errors_dict)

    def _count_mcp_server_devices(self, exclude_id: int = None) -> int:
        """
        Count the number of MCP Server devices, optionally excluding one by ID.
        """
        count = 0
        for device in indigo.devices.iter(filter="self"):
            if device.deviceTypeId == "mcpServer" and device.id != exclude_id:
                count += 1
        return count

    def _get_mcp_server_device(self) -> indigo.Device:
        """
        Get the single MCP Server device, if it exists.
        """
        for device in indigo.devices.iter(filter="self"):
            if device.deviceTypeId == "mcpServer":
                return device
        return None

    def _start_mcp_server_from_device(self, device: indigo.Device) -> None:
        """
        Start MCP server using device configuration.
        """
        try:
            # Store reference to device
            self.mcp_server_device = device

            # Get server port from device properties (with fallback to plugin prefs for compatibility)
            device_server_port = device.pluginProps.get("serverPort")
            if device_server_port:
                server_port = int(device_server_port)
            else:
                # Fallback to plugin preferences for existing installations
                server_port = self.server_port
                self.logger.debug(f"Using plugin-level server port {server_port} for device {device.name}")

            # Get access mode from device properties
            device_access_mode = device.pluginProps.get(
                "server_access_mode", "local_only"
            )

            # Convert access mode string to enum
            access_mode = (
                AccessMode.REMOTE_ACCESS
                if device_access_mode == "remote_access"
                else AccessMode.LOCAL_ONLY
            )

            # Update device states
            device.updateStateOnServer(key="serverStatus", value="Starting")
            device.updateStateOnServer(key="serverPort", value=server_port)
            device.updateStateOnServer(
                key="accessMode", value=device_access_mode.replace("_", " ").title()
            )
            device.updateStateOnServer(key="clientCount", value=0)

            # Initialize data provider if needed
            if not self.data_provider:
                self.data_provider = IndigoDataProvider(logger=self.logger)

            # Initialize and start MCP server
            if self.mcp_server_core:
                self.mcp_server_core.stop()

            self.mcp_server_core = MCPServerCore(
                data_provider=self.data_provider,
                server_name="indigo-mcp-server",
                port=server_port,
                access_mode=access_mode,
                bearer_token=self.bearer_token,
                logger=self.logger,
            )

            # Update device status to Vector DB Initializing
            device.updateStateOnServer(key="serverStatus", value="Vector DB Initializing", uiValue="Vector DB Initializing")
            
            # Start the MCP server synchronously - this will handle the initialization progress internally
            self.mcp_server_core.start()
            
            # Update device states to Running after completion
            device.updateStateOnServer(key="serverStatus", value="Running", uiValue="Running")
            device.updateStateOnServer(key="lastActivity", value="Server started")

            self.logger.info(f"{device.name} started.")
            
            # Log registered MCP components
            self._log_mcp_components()

        except Exception as e:
            device.updateStateOnServer(key="serverStatus", value="Error")
            self.logger.error(f"Failed to start MCP server from device: {e}")

    def _stop_mcp_server_from_device(self, device: indigo.Device) -> None:
        """
        Stop MCP server for a specific device.
        """
        try:
            device.updateStateOnServer(key="serverStatus", value="Stopping")

            if self.mcp_server_core:
                self.mcp_server_core.stop()
                self.mcp_server_core = None

            device.updateStateOnServer(key="serverStatus", value="Stopped")
            device.updateStateOnServer(key="clientCount", value=0)
            device.updateStateOnServer(key="lastActivity", value="Server stopped")

            self.logger.info(f"MCP server stopped for device {device.name}")

        except Exception as e:
            device.updateStateOnServer(key="serverStatus", value="Error")
            self.logger.error(f"Failed to stop MCP server for device: {e}")

    def _log_mcp_components(self) -> None:
        """
        Log registered MCP components (tools, resources, prompts).
        Simple, synchronous method that queries the FastMCP server directly.
        """
        if not self.mcp_server_core or not self.mcp_server_core.mcp_server:
            return
            
        try:
            # Get registered components from FastMCP
            import asyncio
            loop = asyncio.new_event_loop()
            
            try:
                # Get tools
                tools = loop.run_until_complete(self.mcp_server_core.mcp_server.get_tools())
                if tools:
                    tool_names = list(tools.keys())
                    self.logger.info(f"Published MCP Tools ({len(tool_names)}): {', '.join(tool_names)}")
                else:
                    self.logger.info("Published MCP Tools (0): None")
                    
                # Get resources
                resources = loop.run_until_complete(self.mcp_server_core.mcp_server.get_resources())
                if resources:
                    resource_names = list(resources.keys())
                    self.logger.info(f"Published MCP Resources ({len(resource_names)}): {', '.join(resource_names)}")
                else:
                    self.logger.info("Published MCP Resources (0): None")
                    
                # Get prompts
                prompts = loop.run_until_complete(self.mcp_server_core.mcp_server.get_prompts())
                if prompts:
                    prompt_names = list(prompts.keys())
                    self.logger.info(f"Published MCP Prompts ({len(prompt_names)}): {', '.join(prompt_names)}")
                else:
                    self.logger.info("Published MCP Prompts (0): None")
                    
            finally:
                loop.close()
                
        except Exception as e:
            self.logger.debug(f"Could not log MCP components: {e}")

    def _restart_mcp_server_from_device(self, device: indigo.Device) -> None:
        """
        Restart MCP server for a specific device.
        """
        self._stop_mcp_server_from_device(device)
        self._start_mcp_server_from_device(device)
    

    def closedPrefsConfigUi(
        self, values_dict: indigo.Dict, user_cancelled: bool
    ) -> None:
        """
        Called when the plugin configuration dialog is closed.

        :param values_dict: the values dictionary
        :param user_cancelled: True if the user cancelled the dialog
        """
        if not user_cancelled:
            self.logger.info("Applying configuration changes...")

            # Update ALL configuration values from the dialog
            self.log_level = int(values_dict.get("log_level", 20))
            self.indigo_log_handler.setLevel(self.log_level)
            self.plugin_file_handler.setLevel(self.log_level)
            logging.getLogger("Plugin").setLevel(self.log_level)

            # Core configuration
            self.openai_api_key = values_dict.get("openai_api_key", "")
            self.large_model = values_dict.get("large_model", "gpt-5")
            self.small_model = values_dict.get("small_model", "gpt-5-mini")
            self.server_port = int(values_dict.get("server_port", 8080))

            # Security configuration
            self.access_mode = values_dict.get("access_mode", "local_only")
            self.bearer_token = values_dict.get("bearer_token", "")

            # LangSmith configuration
            self.enable_langsmith = values_dict.get("enable_langsmith", False)
            self.langsmith_endpoint = values_dict.get(
                "langsmith_endpoint", "https://api.smith.langchain.com"
            )
            self.langsmith_api_key = values_dict.get("langsmith_api_key", "")
            self.langsmith_project = values_dict.get("langsmith_project", "")

            # InfluxDB configuration
            self.enable_influxdb = values_dict.get("enable_influxdb", False)
            self.influx_url = values_dict.get("influx_url", "http://localhost")
            self.influx_port = values_dict.get("influx_port", "8086")
            self.influx_login = values_dict.get("influx_login", "")
            self.influx_password = values_dict.get("influx_password", "")
            self.influx_database = values_dict.get("influx_database", "indigo")

            # Generate bearer token if not set (same as startup)
            if not self.bearer_token:
                self.bearer_token = self.auth_manager.generate_bearer_token()
                # Save to plugin preferences
                plugin_prefs = self.pluginPrefs
                plugin_prefs["bearer_token"] = self.bearer_token
                self.logger.info(
                    "Generated new bearer token for MCP server authentication"
                )

            # Set ALL environment variables (same as startup)
            os.environ["OPENAI_API_KEY"] = self.openai_api_key
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

            # Set InfluxDB environment variables
            if self.enable_influxdb:
                os.environ["INFLUXDB_HOST"] = self.influx_url.replace(
                    "http://", ""
                ).replace("https://", "")
                os.environ["INFLUXDB_PORT"] = str(self.influx_port)
                os.environ["INFLUXDB_USERNAME"] = self.influx_login
                os.environ["INFLUXDB_PASSWORD"] = self.influx_password
                os.environ["INFLUXDB_DATABASE"] = self.influx_database
                os.environ["INFLUXDB_ENABLED"] = "true"
            else:
                os.environ["INFLUXDB_ENABLED"] = "false"

            # Set DB_FILE environment variable for vector store (same as startup)
            db_path = os.path.join(
                indigo.server.getInstallFolderPath(),
                "Preferences/Plugins/com.vtmikel.mcp_server/vector_db",
            )
            os.environ["DB_FILE"] = db_path

            # Reinitialize LangSmith configuration
            self.langsmith_config = get_langsmith_config()

            # Test connections with new configuration
            self.logger.info("Testing connections with new configuration...")
            connections_ok = self.test_connections()

            if not connections_ok:
                self.logger.error(
                    "⚠️ Some required connections failed. Configuration saved."
                )
                self.logger.error(
                    "Please check your configuration and restart the plugin manually."
                )
                return

            self.logger.info(
                "✅ Configuration updated successfully. Restarting MCP server with new settings..."
            )
            
            # Restart MCP server automatically with new configuration
            try:
                mcp_device = self._get_mcp_server_device()
                if mcp_device:
                    self._restart_mcp_server_from_device(mcp_device)
                    self.logger.info("✅ MCP server restarted successfully with new configuration.")
                else:
                    self.logger.info("No MCP Server Indigo Device Found. Create a MCP Server via the New Device Button.")
            except Exception as e:
                self.logger.error(f"Failed to restart MCP server automatically: {e}")
                self.logger.info("Please restart the MCP server device manually.")
