####################
# MCP Advanced Tools Plugin for Indigo Domotics
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

import openai

# Import our modules
from mcp_server.adapters.indigo_data_provider import IndigoDataProvider
from mcp_server.common import log_style
from mcp_server.common.openai_client.langsmith_config import get_langsmith_config
from mcp_server.common.openai_client.main import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_SMALL_MODEL,
    embedding_request_params,
)
from mcp_server.external_tools.discovery import SELF_PLUGIN_ID, discover_manifests
from mcp_server.external_tools.manager import ExternalToolManager
from mcp_server.external_tools.policy import (
    PREF_ALLOWLIST,
    PREF_BLOCKLIST,
    ProviderPolicy,
    build_plugin_list_options,
    describe_policy_result,
    normalize_plugin_ids,
    provider_subscription_ids,
)
from mcp_server.mcp_handler import MCPHandler
from mcp_server.tools.tags.tag_rules import is_valid_tag_name


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
        Initialize the MCP Advanced Tools plugin.

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
        self.small_model = self._resolve_small_model(plugin_prefs.get("small_model"))

        # LangSmith configuration
        self.enable_langsmith = plugin_prefs.get("enable_langsmith", False)
        self.langsmith_endpoint = plugin_prefs.get(
            "langsmith_endpoint", "https://api.smith.langchain.com"
        )
        self.langsmith_api_key = plugin_prefs.get("langsmith_api_key", "")
        self.langsmith_project = plugin_prefs.get("langsmith_project", "")

        # Webhook configuration
        self.enable_webhooks = plugin_prefs.get("enable_webhooks", False)

        # Automation delete gate (checked at call time — no restart needed).
        # Editing (names/descriptions/trigger event settings) is not gated.
        self.enable_automation_delete = plugin_prefs.get("enable_automation_delete", False)

        # Tags (checked at call time). Deleting a tag is gated like deleting an
        # automation; elements carrying the confirmation tag need confirm=true.
        self.enable_tag_delete = plugin_prefs.get("enable_tag_delete", False)
        self.confirm_tag = plugin_prefs.get("confirm_tag", "ask-first")

        # Plugin-provided (external) tool write gate (checked at call time).
        # Default TRUE: provider writes are the point of the feature, and
        # providers auto-backup their own config changes.
        self.enable_external_tool_writes = plugin_prefs.get(
            "enable_external_tool_writes", True
        )

        # Which plugins may provide MCP tools (read on every rescan). Missing
        # prefs (an upgrade) mean "all plugins", the previous behavior. The
        # saved allowlist is kept even in the other modes: its ids are
        # subscribed to so an allowlisted provider is picked up on install.
        self.external_tool_policy = ProviderPolicy.from_prefs(
            plugin_prefs, logger=self.logger
        )
        self.external_tool_allowlist_ids = normalize_plugin_ids(
            plugin_prefs.get(PREF_ALLOWLIST)
        )
        # Plugin ids already subscribed to for 'mcp_tools_updated' (Indigo has
        # no unsubscribe call, and repeat subscriptions should not pile up)
        self._subscribed_provider_ids = set()

        # Component instances
        self.data_provider = None
        self.mcp_handler = None

        # Event subscription components
        self.subscription_manager = None
        self.webhook_dispatcher = None

        # Device management
        self.mcp_server_device = None

        # Set up logging properly
        self.log_level = int(plugin_prefs.get("log_level", logging.INFO))
        self.indigo_log_handler.setLevel(self.log_level)
        self.plugin_file_handler.setLevel(self.log_level)
        logging.getLogger("Plugin").setLevel(self.log_level)
        log_style.set_verbose_activity(plugin_prefs.get("log_mcp_activity", False))

    # Small-model values the config menu once offered but no longer does.
    # gpt-5-mini was the only option before 2026.10.1 (and was never actually
    # used: the model was read at import time, before prefs were applied), so
    # a saved gpt-5-mini is moved to the current default.
    LEGACY_SMALL_MODELS = ("gpt-5-mini",)

    def _resolve_small_model(self, saved) -> str:
        if not saved:
            return DEFAULT_SMALL_MODEL
        if saved in self.LEGACY_SMALL_MODELS:
            self.logger.info(
                f"Small model {saved} is no longer offered — using {DEFAULT_SMALL_MODEL} "
                f"(change it in Plugins → MCP Advanced Tools → Configure)"
            )
            try:
                self.pluginPrefs["small_model"] = DEFAULT_SMALL_MODEL
                # Saved now, not at shutdown, so the notice is logged once
                indigo.server.savePluginPrefs()
            except Exception as e:
                self.logger.debug(f"Could not save the migrated small model: {e}")
            return DEFAULT_SMALL_MODEL
        return saved

    # Preferences of features that left this plugin. They are deleted from the
    # saved prefs so a stored credential doesn't outlive its use: InfluxDB
    # history (and its password/token) moved to the Grafana Home Dashboard
    # plugin's influxlog_query_history tool in 2026.11.0.
    RETIRED_PREFS = (
        "enable_influxdb",
        "influx_url",
        "influx_port",
        "influx_login",
        "influx_password",
        "influx_database",
    )

    def _drop_retired_prefs(self) -> None:
        stale = [key for key in self.RETIRED_PREFS if key in self.pluginPrefs]
        if not stale:
            return
        for key in stale:
            del self.pluginPrefs[key]
        try:
            indigo.server.savePluginPrefs()
        except Exception as e:
            self.logger.debug(f"Could not save the pruned preferences: {e}")
        self.logger.info(
            "Removed the InfluxDB settings from this plugin's preferences: history "
            "now comes from the Grafana Home Dashboard plugin (tool influxlog_query_history)"
        )

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
                self.logger.error("❌ OpenAI API key is missing — open Plugins → MCP Advanced Tools → Configure and enter your key")
                all_required_connections_ok = False
            else:
                # Set API key temporarily for testing
                test_client = openai.OpenAI(api_key=self.openai_api_key)

                # Make a minimal API call to test connectivity
                try:
                    # Use a very small embedding request to test the connection
                    response = test_client.embeddings.create(
                        **embedding_request_params(), input="test", timeout=10.0
                    )
                    if response and response.data:
                        self.logger.info("✅ OpenAI connected")
                    else:
                        self.logger.error("❌ OpenAI returned an invalid response — try again or check status.openai.com")
                        all_required_connections_ok = False
                except Exception as api_error:
                    self.logger.error(f"❌ OpenAI connection failed: {api_error}")
                    all_required_connections_ok = False

        except ImportError:
            self.logger.error("❌ OpenAI library not available — reinstall the plugin")
            all_required_connections_ok = False
        except Exception as e:
            self.logger.error(f"❌ OpenAI connection failed: {e}")
            all_required_connections_ok = False

        return all_required_connections_ok

    def check_cpu_compatibility(self) -> bool:
        """
        Check and log CPU architecture information.

        Note: LanceDB requires Intel Haswell (2013+) or Apple Silicon processors with AVX2 support.
        However, this check is informational only - the plugin will attempt to start regardless.

        Returns:
            Always returns True to allow plugin to start
        """
        machine = platform.machine()

        # Apple Silicon Macs are always compatible
        if machine == 'arm64':
            self.logger.debug("Apple Silicon detected (M1/M2/M3/M4)")
            return True

        # Log info for Intel Macs
        if machine == 'x86_64':
            self.logger.info("Intel Mac detected - LanceDB requires AVX2 CPU support (Intel Haswell 2013+ or newer)")
            self.logger.info("If the plugin fails to start, your CPU may not support AVX2 instructions")
            return True

        # Unknown architecture - log warning but continue
        self.logger.warning(f"⚠️ Unknown CPU architecture: {machine}")
        self.logger.warning("⚠️ Plugin will attempt to start; if it fails, check system requirements.")
        return True

    def _get_mcp_client_urls(self, path: str = "/message/com.vtmikel.mcp_server/mcp/") -> list:
        """
        Detect and return all available URLs for a given IWS message endpoint.

        Returns a list of dicts with 'label', 'url', and 'config' keys for each access method:
        - localhost URL (always available)
        - hostname-based URL (if detectable)
        - IP address-based URLs (all non-localhost IPs)
        - Indigo Reflector URL (if configured)

        :param path: IWS message path to build URLs for (defaults to the MCP endpoint).
        :return: List of URL dicts [{"label": "...", "url": "...", "config": {...}}, ...]
        """
        urls = []
        indigo_port = 8176  # Default Indigo web server port

        # Helper function to generate Claude Desktop config for a given URL
        def make_config(url):
            return {
                "mcpServers": {
                    "indigo-advanced-tools": {
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
    def _automation_gate(self, pref_name: str) -> bool:
        """
        Whether the automation delete gate is open.

        Primary control is the plugin preference checkbox. A JSON override
        file inside the plugin's support folder can also open the gate for
        headless administration — writing it requires filesystem access to
        the server, the same trust level as the config UI:

            <install>/Preferences/Plugins/com.vtmikel.mcp_server/automation_gates.json
            {"enable_automation_delete": true}
        """
        if getattr(self, pref_name, False):
            return True
        try:
            override_path = os.path.join(
                indigo.server.getInstallFolderPath(),
                "Preferences/Plugins/com.vtmikel.mcp_server/automation_gates.json",
            )
            with open(override_path) as override_file:
                overrides = json.load(override_file)
            return bool(overrides.get(pref_name, False))
        except FileNotFoundError:
            return False
        except Exception as e:
            self.logger.debug(f"automation_gates.json unreadable: {e}")
            return False

    ########################################
    # Plugin-provided (external) MCP tools

    def _installed_plugins(self) -> list:
        """
        Every installed plugin, enabled or disabled, as
        (plugin_id, display_name, enabled) tuples; None if Indigo can't say.
        """
        try:
            plugin_list = indigo.server.getPluginList(includeDisabled=True)
        except Exception as e:
            self.logger.warning(f"⚠️ Could not enumerate installed plugins: {e}")
            return None
        plugins = []
        for plugin in plugin_list:
            try:
                plugins.append(
                    (plugin.pluginId, plugin.pluginDisplayName, bool(plugin.isEnabled()))
                )
            except Exception as e:
                self.logger.debug(f"Skipping an unreadable plugin entry: {e}")
        return plugins

    def _subscribe_to_provider_broadcasts(self) -> set:
        """
        Subscribe to the 'mcp_tools_updated' broadcast from every installed
        plugin plus every allowlisted id (subscriptions are registered
        server-side by (pluginId, key) and survive the broadcaster not being
        installed yet). Providers broadcast it from their startup() and
        whenever their tool set changes, so a provider upgrade that adds a
        manifest registers live. Only ids not subscribed yet are subscribed.

        Returns:
            The plugin ids newly subscribed by this call.
        """
        installed = self._installed_plugins()
        installed_ids = [p[0] for p in installed] if installed is not None else []
        if self.mcp_handler and self.mcp_handler.external_tool_manager:
            # Known providers, in case the plugin list was unavailable
            manager = self.mcp_handler.external_tool_manager
            installed_ids += manager.provider_ids() + manager.blocked_provider_ids()

        wanted = provider_subscription_ids(
            installed_ids, self.external_tool_allowlist_ids, SELF_PLUGIN_ID
        )
        newly_subscribed = set()
        for plugin_id in sorted(wanted - self._subscribed_provider_ids):
            try:
                indigo.server.subscribeToBroadcast(
                    plugin_id, "mcp_tools_updated", "external_tools_updated_broadcast"
                )
                self._subscribed_provider_ids.add(plugin_id)
                newly_subscribed.add(plugin_id)
                self.logger.debug(f"Subscribed to mcp_tools_updated from {plugin_id}")
            except Exception as e:
                self.logger.warning(
                    f"⚠️ Could not subscribe to mcp_tools_updated from {plugin_id}: {e}"
                )
        return newly_subscribed

    def _check_for_new_provider_plugins(self) -> bool:
        """
        Called by the MCP handler from tools/list (throttled there to once a
        minute): a plugin installed for the first time after startup has not
        been subscribed to, so its startup broadcast was lost. Subscribe to
        it now and report True so the handler rescans before answering.
        """
        return bool(self._subscribe_to_provider_broadcasts())

    def external_tools_updated_broadcast(self, arg=None) -> None:
        """
        Broadcast callback: a provider announced that its MCP tool manifest
        changed (or the provider just started). Runs on the plugin's single
        callback thread, so the registry rebuild needs no locking.
        """
        if self.mcp_handler:
            self.logger.debug("mcp_tools_updated broadcast received — rescanning")
            self.mcp_handler.refresh_external_tools()

    def rescan_external_tools_menu(self) -> None:
        """Menu item: manually re-discover plugin-provided MCP tools."""
        if not self.mcp_handler:
            self.logger.error("❌ MCP Advanced Tools is not running — nothing to rescan")
            return
        self._subscribe_to_provider_broadcasts()
        self.mcp_handler.refresh_external_tools(announce=True)

    def external_tool_plugin_list(
        self, filter="", valuesDict=None, typeId="", targetId=0
    ) -> list:
        """
        Dynamic list for the allowlist/blocklist config fields: every
        installed plugin (enabled or disabled) except this one, labelled with
        its MCP tool count and enabled state, plus saved ids whose plugin is
        no longer installed (so a save does not silently drop them). Tool
        counts come from a fresh discovery each time the dialog opens.
        """
        installed = self._installed_plugins() or []
        try:
            tool_counts = {
                m.plugin_id: len(m.tools) for m in discover_manifests(self.logger)
            }
        except Exception as e:
            self.logger.debug(f"MCP tool manifest discovery failed: {e}")
            tool_counts = {}
        saved_ids = []
        if valuesDict is not None:
            for key in (PREF_ALLOWLIST, PREF_BLOCKLIST):
                try:
                    saved_ids += normalize_plugin_ids(valuesDict.get(key))
                except Exception as e:
                    self.logger.debug(f"Could not read saved {key}: {e}")
        return build_plugin_list_options(installed, tool_counts, saved_ids, SELF_PLUGIN_ID)

    def _apply_external_tool_policy(self) -> None:
        """
        Apply a changed provider policy right away: subscribe to newly
        allowlisted ids, swap the registry in place (the same path broadcasts
        and the Rescan menu item use), and log one line describing the result.
        """
        if not self.mcp_handler or not self.mcp_handler.external_tool_manager:
            self.logger.info(
                describe_policy_result(self.external_tool_policy, [], [])
                + " (applies when the MCP Advanced Tools starts)"
            )
            return
        try:
            self._subscribe_to_provider_broadcasts()
            self.mcp_handler.refresh_external_tools(announce=False)
            self.logger.info(self.mcp_handler.external_tool_manager.policy_summary())
        except Exception as e:
            self.logger.error(
                f"❌ Could not apply the plugin-provided tools setting: {e} — use "
                f"Plugins → MCP Advanced Tools → Rescan Plugin-Provided MCP Tools"
            )

    ########################################
    def _apply_environment(self) -> None:
        """
        Push the current plugin configuration into environment variables for
        the mcp_server modules, and refresh the LangSmith config.

        Called from startup() and closedPrefsConfigUi(); must run before the
        MCPHandler is (re)initialized so DB_FILE and API keys are in place.
        """
        os.environ["OPENAI_API_KEY"] = self.openai_api_key

        # Model selection (read at call time by the openai_client helpers).
        # The embedding model is fixed: changing it rebuilds the whole index.
        os.environ["SMALL_MODEL"] = self.small_model
        os.environ["OPENAI_EMBEDDING_MODEL"] = DEFAULT_EMBEDDING_MODEL

        # LangSmith tracing
        if self.enable_langsmith:
            os.environ["LANGSMITH_TRACING"] = "true"
            os.environ["LANGSMITH_ENDPOINT"] = self.langsmith_endpoint
            os.environ["LANGSMITH_API_KEY"] = self.langsmith_api_key
            os.environ["LANGSMITH_PROJECT"] = self.langsmith_project
        else:
            os.environ["LANGSMITH_TRACING"] = "false"

        self.langsmith_config = get_langsmith_config()

        # Vector store location
        db_path = os.path.join(
            indigo.server.getInstallFolderPath(),
            "Preferences/Plugins/com.vtmikel.mcp_server/vector_db",
        )
        os.environ["DB_FILE"] = db_path

    ########################################
    def startup(self) -> None:
        """
        Called after __init__ when the plugin is starting up.
        """
        self.logger.info("Starting MCP Advanced Tools...")

        self._drop_retired_prefs()

        # Test connections before proceeding
        if not self.test_connections():
            self.logger.error("❌ MCP Advanced Tools can't start until the connection problems above are fixed")
            return

        # Log CPU architecture information
        self.check_cpu_compatibility()

        # Apply configuration to environment for the modules to use
        self._apply_environment()

        # Initialize data provider
        try:
            self.data_provider = IndigoDataProvider(logger=self.logger)
        except Exception as e:
            self.logger.error(f"❌ MCP Advanced Tools failed to start (Indigo data access): {e}")
            return

        # Subscribe to all device and variable changes for event webhooks
        indigo.devices.subscribeToChanges()
        indigo.variables.subscribeToChanges()

        # Initialize event subscription system (if webhooks enabled)
        subscription_handler = None
        if self.enable_webhooks:
            try:
                from mcp_server.events import (
                    SubscriptionManager, WebhookDispatcher, SubscriptionHandler,
                    SubscriptionStore
                )
                # Persist subscriptions next to the vector DB so they survive
                # plugin/Indigo restarts.
                subscriptions_path = os.path.join(
                    indigo.server.getInstallFolderPath(),
                    "Preferences/Plugins/com.vtmikel.mcp_server/subscriptions.json",
                )
                subscription_store = SubscriptionStore(
                    subscriptions_path, logger=self.logger
                )
                self.subscription_manager = SubscriptionManager(
                    logger=self.logger, store=subscription_store
                )
                self.webhook_dispatcher = WebhookDispatcher(logger=self.logger)
                self.webhook_dispatcher.start()
                # Wire dwell timer callback to dispatcher
                self.subscription_manager.set_dispatch_callback(
                    self.webhook_dispatcher.dispatch
                )
                # Wire auto-expiry callback for max_fires
                self.webhook_dispatcher.set_on_expired(
                    lambda sub: self.subscription_manager.delete(sub.subscription_id)
                )
                # Restore subscriptions persisted from a previous run
                restored = self.subscription_manager.load_from_store()
                if restored:
                    self.logger.info(f"🔔 Restored {restored} event subscription(s)")
                subscription_handler = SubscriptionHandler(
                    subscription_manager=self.subscription_manager,
                    webhook_dispatcher=self.webhook_dispatcher,
                    logger=self.logger,
                )
                self.logger.info("✅ Event webhooks ready")
            except Exception as e:
                self.logger.error(f"❌ Event webhooks failed to start: {e} — subscriptions won't fire until the plugin is reloaded")
                self.subscription_manager = None
                self.webhook_dispatcher = None

        # Initialize MCP handler (includes vector store initialization)
        try:
            external_tool_manager = ExternalToolManager(
                logger=self.logger,
                write_gate_supplier=lambda: self._automation_gate(
                    "enable_external_tool_writes"
                ),
                policy_supplier=lambda: self.external_tool_policy,
            )
            self.mcp_handler = MCPHandler(
                data_provider=self.data_provider,
                logger=self.logger,
                subscription_handler=subscription_handler,
                server_version=self.pluginVersion,
                automation_delete_supplier=lambda: self._automation_gate("enable_automation_delete"),
                tag_delete_supplier=lambda: self._automation_gate("enable_tag_delete"),
                confirm_tag_supplier=lambda: self.confirm_tag,
                external_tool_manager=external_tool_manager,
                provider_scan_supplier=self._check_for_new_provider_plugins,
            )
            self._subscribe_to_provider_broadcasts()

            # Log MCP client connection information (full list in the menu action)
            urls = self._get_mcp_client_urls()
            if urls:
                self.logger.info(
                    f"🌐 MCP endpoint: {urls[0]['url']} "
                    f"(Plugins → MCP Advanced Tools → Print MCP Client Connection Information for all options)"
                )
            for url_info in urls:
                self.logger.debug(f"MCP endpoint ({url_info['label']}): {url_info['url']}")

        except Exception as e:
            self.mcp_handler = None
            self.logger.error(f"❌ MCP Advanced Tools failed to start: {e} — fix the problem and reload the plugin")
            self.logger.debug("MCP handler initialization failed", exc_info=True)
            return

    def shutdown(self) -> None:
        """
        Called when the plugin is being shut down.
        """
        self.logger.info("Stopping MCP Advanced Tools...")

        # Clean up webhook dispatcher
        if self.webhook_dispatcher:
            try:
                self.webhook_dispatcher.stop()
                self.logger.debug("Webhook dispatcher stopped")
            except Exception as e:
                self.logger.warning(f"⚠️ Webhook dispatcher didn't stop cleanly: {e}")
            finally:
                self.webhook_dispatcher = None

        # Clean up subscription manager (cancels dwell timers)
        if self.subscription_manager:
            try:
                # Flush latest stats to disk before stopping
                self.subscription_manager.save()
                self.subscription_manager.shutdown()
                self.logger.debug("Subscription manager stopped")
            except Exception as e:
                self.logger.warning(f"⚠️ Subscription manager didn't stop cleanly: {e}")
            finally:
                self.subscription_manager = None

        # Clean up MCP handler
        if self.mcp_handler:
            try:
                self.mcp_handler.stop()
                self.logger.debug("MCP handler stopped")
            except Exception as e:
                self.logger.warning(f"⚠️ MCP handler didn't stop cleanly: {e}")
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
            self.logger.error("❌ MCP request received but the server isn't running — reload the plugin")
            return {
                "status": 503,  # Service Unavailable
                "headers": {"Content-Type": "application/json"},
                "content": json.dumps({
                    "error": "MCP Advanced Tools unavailable - plugin initialization failed"
                })
            }

        # Delegate to MCP handler (it will handle logging)
        try:
            response = self.mcp_handler.handle_request(method, headers, body)
            return response

        except Exception as e:
            self.logger.error(f"❌ MCP request failed unexpectedly: {e}")
            return {
                "status": 500,
                "headers": {"Content-Type": "application/json"},
                "content": json.dumps({"error": str(e)})
            }

    def handle_events_ui_endpoint(self, action, dev=None, callerWaitingForResult=True):
        """
        Serve the event-subscriptions web UI through Indigo IWS.

        Routed from /message/com.vtmikel.mcp_server/events_ui/. Authentication is
        enforced by IWS before this callback runs.

        GET  -> render the subscription list (HTML).
        POST -> delete one subscription (form field 'subscription_id'), then re-render.

        The handler is intentionally method-agnostic: any non-POST request renders
        the list, so the page works whether or not IWS forwards GET requests.
        """
        from mcp_server.events import web_ui

        method = (action.props.get("incoming_request_method") or "").upper()
        body = action.props.get("request_body") or ""

        # Event webhooks disabled (or failed to initialize) — friendly notice.
        if not self.enable_webhooks or self.subscription_manager is None:
            return {
                "status": 200,
                "headers": {"Content-Type": "text/html; charset=utf-8"},
                "content": web_ui.render_disabled_page(),
            }

        try:
            if method == "POST":
                sub_id = web_ui.parse_delete_subscription_id(body)
                if sub_id:
                    # delete() is idempotent and thread-safe.
                    self.subscription_manager.delete(sub_id)

            subscriptions = [
                s.to_dict(include_token=False)
                for s in self.subscription_manager.list_all()
            ]
            dispatcher_stats = (
                self.webhook_dispatcher.get_stats() if self.webhook_dispatcher else None
            )
            return {
                "status": 200,
                "headers": {"Content-Type": "text/html; charset=utf-8"},
                "content": web_ui.render_subscriptions_page(subscriptions, dispatcher_stats),
            }
        except Exception as e:
            self.logger.error(f"❌ Event subscriptions web page failed to render: {e}")
            return {
                "status": 500,
                "headers": {"Content-Type": "text/html; charset=utf-8"},
                "content": "<html><body><h1>Internal error</h1></body></html>",
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
            "This plugin is a companion to Indigo's built-in MCP Control server (Indigo 2026.1+). Connect both:",
            "  • MCP Control at /v3/api/mcp: device control, variables, running action groups, triggers and schedules",
            "  • this plugin at /message/com.vtmikel.mcp_server/mcp/: search, automation and event-log tools",
            "",
            "⚠️  AUTHENTICATION REQUIRED: All configurations require a Bearer token with an Indigo API key.",
            "",
            "📚 In all cases, you will need an API Key. For this, you have two choices:",
            "  • Indigo Reflector API Key: Obtained from your Reflector settings",
            "  • Local Secret: Created in secrets.json file",
            "    Location: /Library/Application Support/Perceptive Automation/Indigo [VERSION]/Preferences/secrets.json",
            "    Details: https://wiki.indigodomo.com/doku.php?id=indigo_2024.2_documentation:indigo_web_server#local_secrets",
            "    Note: Restart Indigo Web Server after creating/modifying this file",
            "",
            "=" * 80,
            "",
            "🔧 SCENARIO 1: HTTPS via Reflector (Most Common, Enables remote access outside your home)",
            "   • Use when: Accessing Indigo from outside your local network",
            "   • Security: Encrypted connection with valid SSL certificate",
            ""
        ]

        # Find reflector URL for Scenario 1
        reflector_url = next((u for u in urls if u['label'] == 'Remote (Reflector)'), None)
        if reflector_url:
            scenario1_config = {
                "mcpServers": {
                    "indigo-advanced-tools": {
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
            config_lines.append(json.dumps(scenario1_config, indent=2))
            config_lines.extend(["", "Setup:", "  1. Configure Indigo Reflector in Web Server Settings", "  2. Use your Reflector API key", "  3. Replace YOUR_REFLECTOR_API_KEY with your Reflector API key", ""])
        else:
            config_lines.extend([
                "⚠️  Reflector not configured. Configure at Indigo > Web Server Settings > Reflector",
                "   Example URL: https://your-reflector-url.indigodomo.net/message/com.vtmikel.mcp_server/mcp/"
            ])
        config_lines.extend(["", ""])

        config_lines.extend([
            "=" * 80,
            "",
            "🔧 SCENARIO 2: HTTPS on LAN with Self-Signed Certificate",
            ""
        ])

        # Find IP or hostname URL for Scenario 2
        network_url = next((u for u in urls if u['label'] in ['Network (IP)', 'Network (hostname)']), None)
        if network_url:
            # Convert HTTP URL to HTTPS for this scenario
            https_url = network_url['url'].replace('http://', 'https://')
            scenario2_config = {
                "mcpServers": {
                    "indigo-advanced-tools": {
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
            config_lines.append(json.dumps(scenario2_config, indent=2))
            config_lines.extend(["", "Setup:", "  1. Create a local secret (see documentation link above)", "  2. Replace your-local-hostname-or-ip with your Indigo server IP/hostname", "  3. Replace YOUR_LOCAL_SECRET_KEY with your generated local secret", "  4. NODE_TLS_REJECT_UNAUTHORIZED=0 disables certificate validation (required)", "  5. Replace port 8176 if you are not using the default Indigo Web Server port", ""])
        config_lines.extend(["", ""])

        config_lines.extend([
            "=" * 80,
            "",
            "🔧 SCENARIO 3: HTTP on Local/LAN",
            "   • Use when: HTTPS is disabled on your Indigo Web Server",
            ""
        ])

        # Find IP or hostname URL for Scenario 3 (use same network_url as Scenario 2)
        if network_url:
            scenario3_config = {
                "mcpServers": {
                    "indigo-advanced-tools": {
                        "command": "npx",
                        "args": [
                            "-y",
                            "mcp-remote",
                            network_url['url'],
                            "--allow-http",
                            "--header",
                            "Authorization:Bearer YOUR_LOCAL_SECRET_KEY"
                        ]
                    }
                }
            }
            config_lines.append(json.dumps(scenario3_config, indent=2))
            config_lines.extend(["", "Setup:", "  1. Create a local secret (see documentation link above)", "  2. Replace YOUR_LOCAL_SECRET_KEY with your generated local secret", "  3. Replace your-local-hostname-or-ip with your server IP/hostname for LAN access", "  4. Replace port 8176 if you are not using the default Indigo Web Server port", ""])
        config_lines.extend(["", ""])

        self.logger.info("\n".join(config_lines))

    def show_events_ui_url_menu(self) -> None:
        """Menu action: print the Event Subscriptions web UI URL(s) to the log."""
        if not self.enable_webhooks:
            self.logger.info(
                "Event webhooks are disabled. Enable them in the plugin configuration "
                "to use the Event Subscriptions web UI."
            )
            return

        urls = self._get_mcp_client_urls(path="/message/com.vtmikel.mcp_server/events_ui/")
        lines = [
            "🗂️  Event Subscriptions Web UI:",
            "   Open one of these URLs in a browser logged into the Indigo Web Server",
            "   (lists active subscriptions and lets you remove them):",
            "",
        ]
        for u in urls:
            lines.append(f"   {u['label']}: {u['url']}")
        self.logger.info("\n".join(lines))

    def test_connections_button(self, values_dict: indigo.Dict) -> indigo.Dict:
        """Button action to test connections with current configuration values."""
        self.logger.info("Testing connections...")

        # Temporarily update instance variables with dialog values for testing
        old_api_key = self.openai_api_key

        try:
            # Apply values from dialog temporarily
            self.openai_api_key = values_dict.get("openai_api_key", "")

            # Test connections
            connections_ok = self.test_connections()

            if connections_ok:
                self.logger.info("✅ All required connections OK")
            else:
                self.logger.error(
                    "❌ Some required connections failed — see the messages above"
                )

        finally:
            # Restore original values
            self.openai_api_key = old_api_key

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


        # Confirmation tag: empty, or a valid Indigo tag name
        confirm_tag = (values_dict.get("confirm_tag", "") or "").strip()
        if confirm_tag and not is_valid_tag_name(confirm_tag):
            errors_dict["confirm_tag"] = (
                "Tag names are lowercase letters in words joined by single dashes "
                "(e.g. ask-first), or leave it empty"
            )

        # Validate log level
        try:
            log_level = int(values_dict.get("log_level", 20))
            if log_level not in [5, 10, 20, 30, 40, 50]:
                errors_dict["log_level"] = "Invalid log level"
        except (ValueError, TypeError):
            errors_dict["log_level"] = "Log level must be a valid number"

        return (len(errors_dict) == 0, values_dict, errors_dict)

    ########################################
    # Device Management
    ########################################

    def deviceStartComm(self, device: indigo.Device) -> None:
        """
        Called when a device should start communication.
        """
        if device.deviceTypeId == "mcpServer":
            self.logger.info(f"MCP Advanced Tools device started: {device.name}")
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
            self.logger.info(f"MCP Advanced Tools device stopped: {device.name}")
            # Update device state
            device.updateStateOnServer(key="serverStatus", value="Stopped")

            # Clear device reference
            if self.mcp_server_device and self.mcp_server_device.id == device.id:
                self.mcp_server_device = None

    def deviceUpdated(self, origDev: indigo.Device, newDev: indigo.Device) -> None:
        """
        Called when any device is updated (after subscribeToChanges).

        Handles MCP Advanced Tools device config changes AND evaluates event
        subscriptions for all other devices.
        """
        # MCP Advanced Tools device handling (existing logic)
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
                self.logger.debug(f"MCP Advanced Tools device '{newDev.name}' updated: {', '.join(changes)}")

            # Check if access mode changed (keep at INFO level - important configuration change)
            old_access_mode = origDev.pluginProps.get(
                "server_access_mode", "local_only"
            )
            new_access_mode = newDev.pluginProps.get("server_access_mode", "local_only")

            if old_access_mode != new_access_mode:
                self.logger.info(
                    f"Access mode changed from {old_access_mode} to {new_access_mode}"
                )
            return

        # Call base implementation (required for subscribeToChanges)
        indigo.PluginBase.deviceUpdated(self, origDev, newDev)

        # Evaluate event subscriptions for all non-plugin devices
        if self.subscription_manager and self.webhook_dispatcher:
            try:
                matches = self.subscription_manager.evaluate_device_change(
                    dict(origDev), dict(newDev)
                )
                for subscription, event in matches:
                    self.webhook_dispatcher.dispatch(subscription, event)
            except Exception as e:
                self.logger.warning(f"⚠️ Event subscription check failed for a device change: {e}")

    def variableUpdated(self, origVar: indigo.Variable, newVar: indigo.Variable) -> None:
        """
        Called when any variable is updated (after subscribeToChanges).

        Evaluates event subscriptions against the variable change.
        """
        indigo.PluginBase.variableUpdated(self, origVar, newVar)

        if self.subscription_manager and self.webhook_dispatcher:
            try:
                matches = self.subscription_manager.evaluate_variable_change(
                    dict(origVar), dict(newVar)
                )
                for subscription, event in matches:
                    self.webhook_dispatcher.dispatch(subscription, event)
            except Exception as e:
                self.logger.warning(f"⚠️ Event subscription check failed for a variable change: {e}")

    def validateDeviceConfigUi(
        self, valuesDict: indigo.Dict, typeId: str, devId: int
    ) -> tuple:
        """
        Validate device configuration.
        """
        errors_dict = indigo.Dict()

        if typeId == "mcpServer":
            # Enforce single MCP Advanced Tools device
            if self._count_mcp_server_devices(exclude_id=devId) > 0:
                errors_dict["serverName"] = (
                    "Only one MCP Advanced Tools device is allowed per plugin"
                )

            # Validate server name
            server_name = valuesDict.get("serverName", "").strip()
            if not server_name:
                errors_dict["serverName"] = "Server name is required"

        return (len(errors_dict) == 0, valuesDict, errors_dict)

    def _count_mcp_server_devices(self, exclude_id: int = None) -> int:
        """
        Count the number of MCP Advanced Tools devices, optionally excluding one by ID.
        """
        count = 0
        for device in indigo.devices.iter(filter="self"):
            if device.deviceTypeId == "mcpServer" and device.id != exclude_id:
                count += 1
        return count

    def _get_mcp_server_device(self) -> indigo.Device:
        """
        Get the single MCP Advanced Tools device, if it exists.
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
            log_style.set_verbose_activity(values_dict.get("log_mcp_activity", False))

            # Core configuration
            self.openai_api_key = values_dict.get("openai_api_key", "")
            self.small_model = values_dict.get("small_model") or DEFAULT_SMALL_MODEL

            # LangSmith configuration
            self.enable_langsmith = values_dict.get("enable_langsmith", False)
            self.langsmith_endpoint = values_dict.get(
                "langsmith_endpoint", "https://api.smith.langchain.com"
            )
            self.langsmith_api_key = values_dict.get("langsmith_api_key", "")
            self.langsmith_project = values_dict.get("langsmith_project", "")

            # Webhook configuration
            new_enable_webhooks = values_dict.get("enable_webhooks", False)
            if new_enable_webhooks != self.enable_webhooks:
                self.enable_webhooks = new_enable_webhooks
                self.logger.info(
                    f"Event webhooks {'enabled' if self.enable_webhooks else 'disabled'} "
                    f"- plugin restart required for MCP tool changes to take effect"
                )

            # Automation delete gate (takes effect immediately — checked per call)
            new_delete_gate = values_dict.get("enable_automation_delete", False)
            if new_delete_gate != self.enable_automation_delete:
                self.enable_automation_delete = new_delete_gate
                self.logger.info(
                    f"Automation delete via MCP {'enabled' if new_delete_gate else 'disabled'}"
                )

            # Tag delete gate and confirmation tag (take effect immediately)
            new_tag_delete = values_dict.get("enable_tag_delete", False)
            if new_tag_delete != self.enable_tag_delete:
                self.enable_tag_delete = new_tag_delete
                self.logger.info(f"Tag delete via MCP {'enabled' if new_tag_delete else 'disabled'}")
            new_confirm_tag = (values_dict.get("confirm_tag", "") or "").strip()
            if new_confirm_tag != self.confirm_tag:
                self.confirm_tag = new_confirm_tag
                self.logger.info(
                    f"Confirmation tag set to '{new_confirm_tag}'"
                    if new_confirm_tag else "Confirmation tag turned off"
                )

            # External tool write gate (takes effect immediately — checked per call)
            new_external_write_gate = values_dict.get("enable_external_tool_writes", True)
            if new_external_write_gate != self.enable_external_tool_writes:
                self.enable_external_tool_writes = new_external_write_gate
                self.logger.info(
                    f"Plugin-provided write tools "
                    f"{'enabled' if new_external_write_gate else 'disabled'}"
                )

            # Which plugins may provide MCP tools (takes effect immediately).
            # Both lists are kept as saved; only the active mode's list counts.
            self.external_tool_allowlist_ids = normalize_plugin_ids(
                values_dict.get(PREF_ALLOWLIST)
            )
            new_policy = ProviderPolicy.from_prefs(values_dict, logger=self.logger)
            if new_policy != self.external_tool_policy:
                self.external_tool_policy = new_policy
                self._apply_external_tool_policy()
            elif self.mcp_handler:
                # An edit to the inactive allowlist still gets subscribed to
                self._subscribe_to_provider_broadcasts()

            # Apply configuration to environment (same as startup)
            self._apply_environment()

            # Test connections with new configuration
            self.logger.debug("Testing connections with new configuration...")
            connections_ok = self.test_connections()

            if not connections_ok:
                self.logger.error(
                    "❌ Configuration saved, but a required connection failed — "
                    "the plugin can't work until this is fixed (see messages above)"
                )
                return

            self.logger.info("✅ Configuration saved")

            # No server restart needed - MCP runs via Indigo Web Server
            # Configuration changes (environment variables) are already applied above
            # and will be picked up by handlers on next request
