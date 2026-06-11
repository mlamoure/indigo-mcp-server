"""
Tests for IndigoDataProvider with a fake `indigo` module.

The provider's read paths intentionally degrade (log at DEBUG, return
empty/None) and its control paths return {"error": ...} dicts — these
tests pin that contract.
"""

import pytest
from unittest.mock import Mock, patch
import sys
from pathlib import Path

# Add plugin to path
plugin_path = Path(__file__).parent.parent / "MCP Server.indigoPlugin/Contents/Server Plugin"
sys.path.insert(0, str(plugin_path))

import mcp_server.adapters.indigo_data_provider as idp_module
from mcp_server.adapters.indigo_data_provider import IndigoDataProvider


class FakeDevice(dict):
    """Mapping (so dict(dev) works) with attribute access like indigo.Device."""

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError:
            raise AttributeError(item)


class FakeDevices:
    """Container mimicking indigo.devices: `in`, [id], iteration over ids."""

    def __init__(self, devices):
        self._devices = devices

    def __contains__(self, device_id):
        return device_id in self._devices

    def __getitem__(self, device_id):
        return self._devices[device_id]

    def __iter__(self):
        return iter(self._devices)


def make_fake_indigo(devices=None):
    fake = Mock()
    fake.devices = FakeDevices(devices or {})
    return fake


@pytest.fixture
def provider():
    return IndigoDataProvider(logger=Mock())


def with_indigo(fake):
    """Patch the module-global `indigo` name (import is try/except'd in tests env)."""
    return patch.object(idp_module, "indigo", fake, create=True)


class TestGetDevice:
    def test_found_returns_dict(self, provider):
        dev = FakeDevice(id=42, name="Kitchen Lights", onState=False)
        with with_indigo(make_fake_indigo({42: dev})):
            result = provider.get_device(42)

        assert result == {"id": 42, "name": "Kitchen Lights", "onState": False}

    def test_missing_returns_none(self, provider):
        with with_indigo(make_fake_indigo({})):
            assert provider.get_device(99) is None

    def test_exception_returns_none(self, provider):
        fake = Mock()
        fake.devices = Mock(__contains__=Mock(side_effect=RuntimeError("down")))
        with with_indigo(fake):
            assert provider.get_device(1) is None


class TestGetAllDevices:
    def test_exception_returns_empty_list(self, provider):
        fake = Mock()
        fake.devices = Mock(__iter__=Mock(side_effect=RuntimeError("down")))
        with with_indigo(fake):
            assert provider.get_all_devices() == []


class TestTurnOnDevice:
    def test_not_found_returns_error(self, provider):
        with with_indigo(make_fake_indigo({})):
            result = provider.turn_on_device(99)

        assert result == {"error": "Device 99 not found"}

    def test_state_change_detected(self, provider):
        dev = FakeDevice(id=42, name="Kitchen Lights", onState=False)
        fake = make_fake_indigo({42: dev})

        def turn_on(device_id):
            dev["onState"] = True

        fake.device.turnOn.side_effect = turn_on

        with with_indigo(fake), patch.object(idp_module.time, "sleep"):
            result = provider.turn_on_device(42)

        assert result["changed"] is True
        assert result["previous"] is False
        assert result["current"] is True
        assert result["device_name"] == "Kitchen Lights"

    def test_no_change_when_already_on(self, provider):
        dev = FakeDevice(id=42, name="Kitchen Lights", onState=True)
        fake = make_fake_indigo({42: dev})

        with with_indigo(fake), patch.object(idp_module.time, "sleep"):
            result = provider.turn_on_device(42)

        assert result["changed"] is False

    def test_indigo_exception_becomes_error_dict(self, provider):
        dev = FakeDevice(id=42, name="Kitchen Lights", onState=False)
        fake = make_fake_indigo({42: dev})
        fake.device.turnOn.side_effect = RuntimeError("bridge offline")

        with with_indigo(fake), patch.object(idp_module.time, "sleep"):
            result = provider.turn_on_device(42)

        assert result == {"error": "bridge offline"}


class TestTurnOffDevice:
    def test_not_found_returns_error(self, provider):
        with with_indigo(make_fake_indigo({})):
            result = provider.turn_off_device(99)

        assert result == {"error": "Device 99 not found"}
