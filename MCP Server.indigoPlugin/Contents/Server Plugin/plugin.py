####################
# MCP Server Plugin for Indigo Domotics
# Provides Model Context Protocol (MCP) support for AI assistants to interact with Indigo
####################

try:
    import indigo
except ImportError:
    pass

import json
import logging
import os
import platform
import socket
import subprocess

import openai

# Import our modules
from mcp_server.adapters.indigo_data_provider import IndigoDataProvider
from mcp_server.common.openai_client.langsmith_config import get_langsmith_config
from mcp_server.mcp_handler import MCPHandler
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

        # Component instances
        self.data_provider = None
        self.mcp_handler = None
        self.auth_manager = AuthManager(logger=self.logger)

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
        try:
            # Validate API key format
            if (
                not self.openai_api_key
                or self.openai_api_key == "xxxxx-xxxxx-xxxxx-xxxxx"
            ):
                self.logger.error("\t❌ OpenAI API key not configured")
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
                        self.logger.info("\t✅ OpenAI API connected")
                    else:
                        self.logger.error("\t❌ OpenAI API returned invalid response")
                        all_required_connections_ok = False
                except Exception as api_error:
                    self.logger.error(f"\t❌ OpenAI API failed: {api_error}")
                    all_required_connections_ok = False

        except ImportError:
            self.logger.error("\t❌ OpenAI library not available")
            all_required_connections_ok = False
        except Exception as e:
            self.logger.error(f"\t❌ OpenAI connection failed: {e}")
            all_required_connections_ok = False

        # Test InfluxDB connection (optional, only if enabled)
        if self.enable_influxdb:
            try:
                from influxdb import InfluxDBClient

                # Validate InfluxDB configuration
                if not self.influx_url or not self.influx_port:
                    self.logger.warning("\t⚠️ InfluxDB enabled but not configured")
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
                            self.logger.info("\t✅ InfluxDB connected (historical data available)")
                        else:
                            self.logger.warning("\t⚠️ InfluxDB ping failed")

                        client.close()

                    except ValueError as ve:
                        self.logger.warning(f"\t⚠️ InfluxDB port error: {ve}")
                    except Exception as influx_error:
                        self.logger.warning(f"\t⚠️ InfluxDB connection failed: {influx_error}")

            except ImportError:
                self.logger.warning("\t⚠️ InfluxDB library not available")
            except Exception as e:
                self.logger.warning(f"\t⚠️ InfluxDB connection failed: {e}")

        return all_required_connections_ok

    def check_cpu_compatibility(self) -> bool:
        """
        Check if the CPU supports AVX2 instructions required by LanceDB.

        LanceDB requires Intel Haswell (2013+) or Apple Silicon processors.

        Returns:
            True if CPU is compatible, False otherwise
        """
        machine = platform.machine()

        # Apple Silicon Macs are always compatible
        if machine == 'arm64':
            self.logger.debug("✅ Apple Silicon detected - CPU compatible")
            return True

        # Check x86_64 Macs for AVX2 support
        if machine == 'x86_64':
            try:
                result = subprocess.run(
                    ['sysctl', '-n', 'machdep.cpu.leaf7_features'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )

                if result.returncode == 0 and 'AVX2' in result.stdout:
                    self.logger.debug("✅ AVX2 support detected - CPU compatible")
                    return True
                else:
                    self.logger.error("❌ CPU Compatibility Error: AVX2 instruction set not supported")
                    self.logger.error("")
                    self.logger.error("   This plugin requires a CPU with AVX2 support (Intel Haswell or newer, 2013+)")
                    self.logger.error("")
                    self.logger.error("   Incompatible Systems:")
                    self.logger.error("   • 2012-2013 Intel Macs (Ivy Bridge or older)")
                    self.logger.error("   • 2013 Mac Pro (MacPro6,1 'trash can')")
                    self.logger.error("")
                    self.logger.error("   Compatible Systems:")
                    self.logger.error("   • Mid-2013 MacBook Air/Pro and later (Haswell+)")
                    self.logger.error("   • Late-2013 iMac and later")
                    self.logger.error("   • 2019 Mac Pro and later")
                    self.logger.error("   • All Apple Silicon Macs (M1/M2/M3/M4)")
                    self.logger.error("")
                    self.logger.error("   For more information, see: https://github.com/mlamoure/indigo-mcp-server#system-requirements")
                    return False

            except subprocess.TimeoutExpired:
                self.logger.warning("⚠️ CPU compatibility check timed out - assuming compatible")
                return True
            except Exception as e:
                self.logger.warning(f"⚠️ Could not check CPU compatibility: {e}")
                self.logger.warning("   Assuming CPU is compatible. If plugin fails, check system requirements.")
                return True

        # Unknown architecture - assume compatible with warning
        self.logger.warning(f"⚠️ Unknown CPU architecture: {machine}")
        self.logger.warning("   Assuming CPU is compatible. If plugin fails, check system requirements.")
        return True

    def _get_mcp_client_urls(self) -> list:
        """
        Detect and return all available URLs for MCP client connections.

        Returns a list of dicts with 'label', 'url', and 'config' keys for each access method:
        - localhost URL (always available)
        - hostname-based URL (if detectable)
        - IP address-based URLs (all non-localhost IPs)
        - Indigo Reflector URL (if configured)

        :return: List of URL dicts [{"label": "...", "url": "...", "config": {...}}, ...]
        """
        urls = []
        indigo_port = 8176  # Default Indigo web server port
        path = "/message/com.vtmikel.mcp_server/mcp/"

        # Helper function to generate Claude Desktop config for a given URL
        def make_config(url):
            return {
                "mcpServers": {
                    "indigo": {
                        "command": "npx",
                        "args": [
                            "mcp-remote",
                            url
                        ]
                    }
                }
            }

        # Always add localhost URL
        localhost_url = f"http://localhost:{indigo_port}{path}"
        urls.append({
            "label": "Local",
            "url": localhost_url,
            "config": make_config(localhost_url)
        })

        try:
            # Get hostname and add hostname-based URL
            hostname = socket.gethostname()
            if hostname and hostname != "localhost":
                hostname_url = f"http://{hostname}:{indigo_port}{path}"
                urls.append({
                    "label": "Network (hostname)",
                    "url": hostname_url,
                    "config": make_config(hostname_url)
                })

            # Get all non-localhost IP addresses
            try:
                addr_info = socket.getaddrinfo(hostname, None, socket.AF_INET)
                seen_ips = set()
                for info in addr_info:
                    ip = info[4][0]
                    # Skip localhost IPs and duplicates
                    if not ip.startswith('127.') and ip not in seen_ips:
                        seen_ips.add(ip)
                        ip_url = f"http://{ip}:{indigo_port}{path}"
                        urls.append({
                            "label": "Network (IP)",
                            "url": ip_url,
                            "config": make_config(ip_url)
                        })
            except Exception as e:
                self.logger.debug(f"Could not detect network IPs: {e}")

        except Exception as e:
            self.logger.debug(f"Could not detect hostname: {e}")

        # Try to get Indigo Reflector URL if configured
        try:
            reflector_url = indigo.server.getReflectorURL()
            if reflector_url:
                # Remove trailing slash if present
                reflector_base = reflector_url.rstrip('/')
                reflector_full_url = f"{reflector_base}{path}"
                urls.append({
                    "label": "Remote (Reflector)",
                    "url": reflector_full_url,
                    "config": make_config(reflector_full_url)
                })
        except Exception as e:
            self.logger.debug(f"Could not detect Indigo Reflector URL: {e}")

        return urls

    ########################################
    def startup(self) -> None:
        """
        Called after __init__ when the plugin is starting up.
        """
        self.logger.info("Starting plugin...")

        # Test connections before proceeding
        if not self.test_connections():
            self.logger.error("\t❌ Required service connections failed - startup aborted")
            return

        # Check CPU compatibility before loading LanceDB
        if not self.check_cpu_compatibility():
            self.logger.error("\t❌ CPU compatibility check failed - startup aborted")
            self.logger.error("\t   Plugin cannot initialize without AVX2 CPU support")
            return

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
            self.logger.error(f"\t❌ Data provider initialization failed: {e}")
            return

        # Initialize MCP handler (includes vector store initialization)
        try:
            self.mcp_handler = MCPHandler(
                data_provider=self.data_provider,
                logger=self.logger
            )

            # Log MCP client connection information
            self.logger.info("🌐 MCP Client Connection Information:")
            urls = self._get_mcp_client_urls()
            for url_info in urls:
                self.logger.info(f"   {url_info['label']}: {url_info['url']}")

        except Exception as e:
            self.logger.error(f"\t❌ MCP handler initialization failed: {e}")
            self.mcp_handler = None
            self.logger.error("\t❌ MCP server unavailable - plugin restart required")
            return

    def shutdown(self) -> None:
        """
        Called when the plugin is being shut down.
        """
        self.logger.info("Stopping plugin...")

        # Clean up MCP handler
        if self.mcp_handler:
            try:
                self.mcp_handler.stop()
                self.logger.info("\t✅ MCP handler stopped")
            except Exception as e:
                self.logger.error(f"\t❌ Error stopping MCP handler: {e}")
            finally:
                self.mcp_handler = None

    ########################################
    # MCP Endpoint Handler for IWS
    ########################################
    
    def handle_mcp_endpoint(self, action, dev=None, callerWaitingForResult=True):
        """
        Handle MCP requests through Indigo IWS.
        This method is called when the /message/<plugin_id>/mcp/ endpoint is accessed.

        Args:
            action: Indigo action containing request details
            dev: Optional device reference
            callerWaitingForResult: Whether caller is waiting for result

        Returns:
            Dict with status, headers, and content for IWS response
        """
        # Extract request details
        method = (action.props.get("incoming_request_method") or "").upper()
        headers = dict(action.props.get("headers", {}))
        body = action.props.get("request_body") or ""

        # Validate MCP handler is available
        if not self.mcp_handler:
            self.logger.error("❌ MCP handler not initialized")
            return {
                "status": 503,  # Service Unavailable
                "headers": {"Content-Type": "application/json"},
                "content": json.dumps({
                    "error": "MCP server unavailable - plugin initialization failed"
                })
            }

        # Delegate to MCP handler (it will handle logging)
        try:
            response = self.mcp_handler.handle_request(method, headers, body)
            return response

        except Exception as e:
            self.logger.error(f"❌ MCP endpoint error: {e}")
            return {
                "status": 500,
                "content": json.dumps({"error": str(e)})
            }

    ########################################
    # Menu Actions
    ########################################

    def show_mcp_client_info_menu(self) -> None:
        """Menu action to show Claude Desktop MCP client connection information."""
        # Get all available connection URLs
        urls = self._get_mcp_client_urls()

        config_lines = [
            "🌐 Claude Desktop MCP Client Connection Information:",
            "",
            "⚠️  AUTHENTICATION REQUIRED: All configurations require a Bearer token with an Indigo API key.",
            "",
            "📚 How to obtain API keys:",
            "  • Local/LAN access: Create a local secret at Indigo > Web Server Settings > Local Secrets",
            "    https://wiki.indigodomo.com/doku.php?id=indigo_2024.2_documentation:indigo_web_server#local_secrets",
            "  • Remote access: Use your Indigo Reflector API key",
            "",
            "=" * 80,
            "",
            "🔧 SCENARIO 1: HTTP on Local/LAN (Recommended for local access)",
            "   • Protocol: http://",
            "   • Security: Safe on localhost/LAN (traffic never leaves local network)",
            "   • Requires: --allow-http flag + Bearer token with local secret",
            ""
        ]

        # Find localhost URL for Scenario 1
        localhost_url = next((u for u in urls if u['label'] == 'Local'), None)
        if localhost_url:
            scenario1_config = {
                "mcpServers": {
                    "indigo": {
                        "command": "npx",
                        "args": [
                            "-y",
                            "mcp-remote",
                            localhost_url['url'],
                            "--allow-http",
                            "--header",
                            "Authorization:Bearer YOUR_LOCAL_SECRET_KEY"
                        ]
                    }
                }
            }
            config_lines.append(json.dumps(scenario1_config, indent=2))
            config_lines.extend(["", ""])

        config_lines.extend([
            "=" * 80,
            "",
            "🔧 SCENARIO 2: HTTPS via Reflector (Remote access)",
            "   • Protocol: https://",
            "   • Security: Encrypted remote access with valid SSL certificate",
            "   • Requires: Bearer token with Reflector API key",
            ""
        ])

        # Find reflector URL for Scenario 2
        reflector_url = next((u for u in urls if u['label'] == 'Remote (Reflector)'), None)
        if reflector_url:
            scenario2_config = {
                "mcpServers": {
                    "indigo": {
                        "command": "npx",
                        "args": [
                            "-y",
                            "mcp-remote",
                            reflector_url['url'],
                            "--header",
                            "Authorization:Bearer YOUR_REFLECTOR_API_KEY"
                        ]
                    }
                }
            }
            config_lines.append(json.dumps(scenario2_config, indent=2))
        else:
            config_lines.extend([
                "⚠️  Reflector not configured. Configure at Indigo > Web Server Settings > Reflector",
                "   Example URL: https://your-reflector-url.indigodomo.net/message/com.vtmikel.mcp_server/mcp/"
            ])
        config_lines.extend(["", ""])

        config_lines.extend([
            "=" * 80,
            "",
            "🔧 SCENARIO 3: HTTPS on LAN with Self-Signed Certificate (Advanced)",
            "   • Protocol: https://",
            "   • Security: Requires disabling certificate validation (NODE_TLS_REJECT_UNAUTHORIZED=0)",
            "   • Requires: Bearer token with local secret",
            "   • Use case: When HTTPS is required on local network (less common)",
            ""
        ])

        # Find IP or hostname URL for Scenario 3
        network_url = next((u for u in urls if u['label'] in ['Network (IP)', 'Network (hostname)']), None)
        if network_url:
            # Convert HTTP URL to HTTPS for this scenario
            https_url = network_url['url'].replace('http://', 'https://')
            scenario3_config = {
                "mcpServers": {
                    "indigo": {
                        "command": "npx",
                        "args": [
                            "-y",
                            "mcp-remote",
                            https_url,
                            "--header",
                            "Authorization:Bearer YOUR_LOCAL_SECRET_KEY"
                        ],
                        "env": {
                            "NODE_TLS_REJECT_UNAUTHORIZED": "0"
                        }
                    }
                }
            }
            config_lines.append(json.dumps(scenario3_config, indent=2))
        config_lines.extend(["", ""])

        config_lines.extend([
            "=" * 80,
            "",
            "💡 Quick Start Guide:",
            "   1. Choose a scenario that matches your use case",
            "   2. Generate an API key (local secret or Reflector key)",
            "   3. Replace YOUR_LOCAL_SECRET_KEY or YOUR_REFLECTOR_API_KEY with your actual key",
            "   4. Save to: ~/Library/Application Support/Claude/claude_desktop_config.json",
            "   5. Restart Claude Desktop",
            "",
            "📖 For more information, see the plugin README.md file",
            ""
        ])

        self.logger.info("\n".join(config_lines))

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
            self.logger.info(f"MCP Server device started: {device.name}")
            # Store reference to device
            self.mcp_server_device = device

            # Update device states to show server is available via IWS
            device.updateStateOnServer(key="serverStatus", value="Running")
            device.updateStateOnServer(key="accessMode", value="IWS")
            device.updateStateOnServer(key="lastActivity", value=str(indigo.server.getTime()))

    def deviceStopComm(self, device: indigo.Device) -> None:
        """
        Called when a device should stop communication.
        """
        if device.deviceTypeId == "mcpServer":
            self.logger.info(f"MCP Server device stopped: {device.name}")
            # Update device state
            device.updateStateOnServer(key="serverStatus", value="Stopped")

            # Clear device reference
            if self.mcp_server_device and self.mcp_server_device.id == device.id:
                self.mcp_server_device = None

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

            if old_access_mode != new_access_mode:
                self.logger.info(
                    f"Access mode changed from {old_access_mode} to {new_access_mode}, restarting server"
                )
                self._restart_mcp_server_from_device(newDev)

            # Device name changes are handled automatically by Indigo

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

    # Server management methods removed - MCP is always available via IWS
    

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
