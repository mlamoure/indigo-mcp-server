"""
Tests for mcp_server.common.influxdb.client — SSL handling and the
db-scoped health check (InfluxDB 1.x and v3 v1-compat support).
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

PLUGIN_SRC = Path(__file__).parent.parent / "MCP Server.indigoPlugin/Contents/Server Plugin"


def _load_module_from_file(name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


client_mod = _load_module_from_file(
    "mcp_server.common.influxdb.client",
    PLUGIN_SRC / "mcp_server" / "common" / "influxdb" / "client.py",
)


def _set_env(monkeypatch, ssl="false"):
    monkeypatch.setenv("INFLUXDB_ENABLED", "true")
    monkeypatch.setenv("INFLUXDB_HOST", "influx.example.com")
    monkeypatch.setenv("INFLUXDB_PORT", "8086")
    monkeypatch.setenv("INFLUXDB_USERNAME", "user")
    monkeypatch.setenv("INFLUXDB_PASSWORD", "secret")
    monkeypatch.setenv("INFLUXDB_DATABASE", "indigo")
    monkeypatch.setenv("INFLUXDB_SSL", ssl)


class TestConnectionInfo:
    def test_ssl_defaults_to_false(self, monkeypatch):
        _set_env(monkeypatch)
        monkeypatch.delenv("INFLUXDB_SSL")
        info = client_mod.InfluxDBClient().get_connection_info()
        assert info["ssl"] is False

    def test_ssl_false_when_env_false(self, monkeypatch):
        _set_env(monkeypatch, ssl="false")
        info = client_mod.InfluxDBClient().get_connection_info()
        assert info["ssl"] is False

    def test_ssl_true_when_env_true(self, monkeypatch):
        _set_env(monkeypatch, ssl="true")
        info = client_mod.InfluxDBClient().get_connection_info()
        assert info["ssl"] is True


class TestGetClient:
    def test_passes_ssl_flags_when_enabled(self, monkeypatch):
        _set_env(monkeypatch, ssl="true")
        mock_client_cls = MagicMock()
        mock_client_cls.return_value.ping.return_value = "3.10.3"
        monkeypatch.setattr(client_mod, "InfluxClient", mock_client_cls)

        with client_mod.InfluxDBClient().get_client():
            pass

        kwargs = mock_client_cls.call_args.kwargs
        assert kwargs["ssl"] is True
        assert kwargs["verify_ssl"] is True

    def test_no_ssl_for_http(self, monkeypatch):
        _set_env(monkeypatch, ssl="false")
        mock_client_cls = MagicMock()
        mock_client_cls.return_value.ping.return_value = "1.8.10"
        monkeypatch.setattr(client_mod, "InfluxClient", mock_client_cls)

        with client_mod.InfluxDBClient().get_client():
            pass

        kwargs = mock_client_cls.call_args.kwargs
        assert kwargs["ssl"] is False
        assert kwargs["verify_ssl"] is False


class TestTestConnection:
    def test_uses_db_scoped_query_not_show_databases(self, monkeypatch):
        # SHOW DATABASES requires admin rights, which scoped InfluxDB 3
        # tokens don't have — the health check must stay db-scoped.
        _set_env(monkeypatch, ssl="true")
        mock_client_cls = MagicMock()
        instance = mock_client_cls.return_value
        instance.ping.return_value = "3.10.3"
        monkeypatch.setattr(client_mod, "InfluxClient", mock_client_cls)

        assert client_mod.InfluxDBClient().test_connection() is True
        instance.query.assert_called_once_with("SHOW MEASUREMENTS LIMIT 1")
        instance.get_list_database.assert_not_called()

    def test_returns_false_on_query_failure(self, monkeypatch):
        _set_env(monkeypatch, ssl="true")
        mock_client_cls = MagicMock()
        instance = mock_client_cls.return_value
        instance.ping.return_value = "3.10.3"
        instance.query.side_effect = RuntimeError("unauthorized access")
        monkeypatch.setattr(client_mod, "InfluxClient", mock_client_cls)

        assert client_mod.InfluxDBClient().test_connection() is False

    def test_returns_false_when_disabled(self, monkeypatch):
        monkeypatch.setenv("INFLUXDB_ENABLED", "false")
        assert client_mod.InfluxDBClient().test_connection() is False
