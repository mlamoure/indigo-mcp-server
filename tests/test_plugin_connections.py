"""
Tests for plugin connection testing functionality.
"""

import pytest
import os
from unittest.mock import Mock, patch, MagicMock

try:
    import indigo
    HAS_INDIGO = True
except ImportError:
    HAS_INDIGO = False
    indigo = None


class MockPlugin:
    """Mock plugin class for testing."""
    
    def __init__(self):
        self.logger = Mock()
        self.openai_api_key = "test-api-key"
        self.enable_influxdb = False
        self.influx_url = "http://localhost"
        self.influx_port = "8086"
        self.influx_login = "testuser"
        self.influx_password = "testpass"
        self.influx_database = "indigo"
    
    def test_connections(self) -> bool:
        """
        Test connections to required and optional services.
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
                        
                        result = client.ping()
                        if result:
                            self.logger.info("✅ InfluxDB connection successful")
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
                        
            except ImportError:
                self.logger.warning("⚠️ InfluxDB library not available - historical data analysis will be unavailable")
            except Exception as e:
                self.logger.warning(f"⚠️ InfluxDB connection test failed: {e}")
        else:
            self.logger.info("InfluxDB disabled - historical data analysis will not be available")
        
        return all_required_connections_ok


@pytest.mark.skipif(not HAS_INDIGO, reason="indigo module not available in test environment")
class TestPluginConnections:
    """Test cases for plugin connection testing."""
    
    def test_openai_connection_success(self):
        """Test successful OpenAI connection."""
        plugin = MockPlugin()
        plugin.openai_api_key = "sk-test123456789"
        
        # Mock successful OpenAI response
        mock_response = Mock()
        mock_response.data = [Mock()]
        
        with patch('openai.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_client.embeddings.create.return_value = mock_response
            mock_openai.return_value = mock_client
            
            result = plugin.test_connections()
            
            assert result is True
            plugin.logger.info.assert_any_call("✅ OpenAI API connection successful")
    
    def test_openai_connection_invalid_key(self):
        """Test OpenAI connection with invalid key."""
        plugin = MockPlugin()
        plugin.openai_api_key = "xxxxx-xxxxx-xxxxx-xxxxx"  # Placeholder key
        
        result = plugin.test_connections()
        
        assert result is False
        plugin.logger.error.assert_any_call("OpenAI API key is not configured or is placeholder")
    
    def test_openai_connection_empty_key(self):
        """Test OpenAI connection with empty key."""
        plugin = MockPlugin()
        plugin.openai_api_key = ""
        
        result = plugin.test_connections()
        
        assert result is False
        plugin.logger.error.assert_any_call("OpenAI API key is not configured or is placeholder")
    
    def test_openai_connection_api_error(self):
        """Test OpenAI connection with API error."""
        plugin = MockPlugin()
        plugin.openai_api_key = "sk-test123456789"
        
        with patch('openai.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_client.embeddings.create.side_effect = Exception("API Error")
            mock_openai.return_value = mock_client
            
            result = plugin.test_connections()
            
            assert result is False
            plugin.logger.error.assert_any_call("❌ OpenAI API connection failed: API Error")
    
    def test_openai_connection_invalid_response(self):
        """Test OpenAI connection with invalid response."""
        plugin = MockPlugin()
        plugin.openai_api_key = "sk-test123456789"
        
        with patch('openai.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_client.embeddings.create.return_value = None  # Invalid response
            mock_openai.return_value = mock_client
            
            result = plugin.test_connections()
            
            assert result is False
            plugin.logger.error.assert_any_call("❌ OpenAI API returned invalid response")
    
    def test_openai_import_error(self):
        """Test OpenAI connection when library is not available."""
        plugin = MockPlugin()
        
        with patch('builtins.__import__', side_effect=ImportError("No module named 'openai'")):
            result = plugin.test_connections()
            
            assert result is False
            plugin.logger.error.assert_any_call("❌ OpenAI library not available")
    
    def test_influxdb_disabled(self):
        """Test when InfluxDB is disabled."""
        plugin = MockPlugin()
        plugin.enable_influxdb = False
        plugin.openai_api_key = "sk-test123456789"
        
        # Mock successful OpenAI response
        mock_response = Mock()
        mock_response.data = [Mock()]
        
        with patch('openai.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_client.embeddings.create.return_value = mock_response
            mock_openai.return_value = mock_client
            
            result = plugin.test_connections()
            
            assert result is True
            plugin.logger.info.assert_any_call("InfluxDB disabled - historical data analysis will not be available")
    
    def test_influxdb_connection_success(self):
        """Test successful InfluxDB connection."""
        plugin = MockPlugin()
        plugin.enable_influxdb = True
        plugin.openai_api_key = "sk-test123456789"
        
        # Mock successful OpenAI response
        mock_openai_response = Mock()
        mock_openai_response.data = [Mock()]
        
        # Mock successful InfluxDB connection
        mock_influx_client = Mock()
        mock_influx_client.ping.return_value = True
        mock_influx_client.get_list_database.return_value = [{"name": "indigo"}]
        
        with patch('openai.OpenAI') as mock_openai:
            mock_openai_client = Mock()
            mock_openai_client.embeddings.create.return_value = mock_openai_response
            mock_openai.return_value = mock_openai_client
            
            with patch('influxdb.InfluxDBClient') as mock_influx:
                mock_influx.return_value = mock_influx_client
                
                result = plugin.test_connections()
                
                assert result is True
                plugin.logger.info.assert_any_call("✅ InfluxDB connection successful")
                plugin.logger.info.assert_any_call("✅ InfluxDB database access successful")
    
    def test_influxdb_connection_ping_failure(self):
        """Test InfluxDB connection with ping failure."""
        plugin = MockPlugin()
        plugin.enable_influxdb = True
        plugin.openai_api_key = "sk-test123456789"
        
        # Mock successful OpenAI response
        mock_openai_response = Mock()
        mock_openai_response.data = [Mock()]
        
        # Mock InfluxDB ping failure
        mock_influx_client = Mock()
        mock_influx_client.ping.return_value = False
        
        with patch('openai.OpenAI') as mock_openai:
            mock_openai_client = Mock()
            mock_openai_client.embeddings.create.return_value = mock_openai_response
            mock_openai.return_value = mock_openai_client
            
            with patch('influxdb.InfluxDBClient') as mock_influx:
                mock_influx.return_value = mock_influx_client
                
                result = plugin.test_connections()
                
                assert result is True  # InfluxDB is optional, so overall should still succeed
                plugin.logger.warning.assert_any_call("⚠️ InfluxDB ping failed - historical data analysis will be unavailable")
    
    def test_influxdb_missing_config(self):
        """Test InfluxDB with missing configuration."""
        plugin = MockPlugin()
        plugin.enable_influxdb = True
        plugin.influx_url = ""  # Missing URL
        plugin.openai_api_key = "sk-test123456789"
        
        # Mock successful OpenAI response
        mock_openai_response = Mock()
        mock_openai_response.data = [Mock()]
        
        with patch('openai.OpenAI') as mock_openai:
            mock_openai_client = Mock()
            mock_openai_client.embeddings.create.return_value = mock_openai_response
            mock_openai.return_value = mock_openai_client
            
            with patch('influxdb.InfluxDBClient'):
                result = plugin.test_connections()
                
                assert result is True  # InfluxDB is optional
                plugin.logger.warning.assert_any_call("⚠️ InfluxDB enabled but URL or port not configured")
    
    def test_influxdb_invalid_port(self):
        """Test InfluxDB with invalid port configuration."""
        plugin = MockPlugin()
        plugin.enable_influxdb = True
        plugin.influx_port = "invalid"  # Invalid port
        plugin.openai_api_key = "sk-test123456789"
        
        # Mock successful OpenAI response
        mock_openai_response = Mock()
        mock_openai_response.data = [Mock()]
        
        with patch('openai.OpenAI') as mock_openai:
            mock_openai_client = Mock()
            mock_openai_client.embeddings.create.return_value = mock_openai_response
            mock_openai.return_value = mock_openai_client
            
            with patch('influxdb.InfluxDBClient'):
                result = plugin.test_connections()
                
                assert result is True  # InfluxDB is optional
                plugin.logger.warning.assert_any_call("⚠️ InfluxDB port configuration error: invalid literal for int() with base 10: 'invalid'")
    
    def test_influxdb_import_error(self):
        """Test InfluxDB when library is not available."""
        plugin = MockPlugin()
        plugin.enable_influxdb = True
        plugin.openai_api_key = "sk-test123456789"
        
        # Mock successful OpenAI response
        mock_openai_response = Mock()
        mock_openai_response.data = [Mock()]
        
        with patch('openai.OpenAI') as mock_openai:
            mock_openai_client = Mock()
            mock_openai_client.embeddings.create.return_value = mock_openai_response
            mock_openai.return_value = mock_openai_client
            
            with patch('builtins.__import__', side_effect=ImportError("No module named 'influxdb'")):
                result = plugin.test_connections()
                
                assert result is True  # InfluxDB is optional
                plugin.logger.warning.assert_any_call("⚠️ InfluxDB library not available - historical data analysis will be unavailable")