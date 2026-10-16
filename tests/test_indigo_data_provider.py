"""
Tests for IndigoDataProvider with a fake `indigo` module.

The provider's read paths intentionally degrade (log at DEBUG, return
empty/None) — these tests pin that contract. (Automation commands are
covered in test_automation_control.py.)
"""

import pytest
from unittest.mock import Mock, patch
import sys
from pathlib import Path

# Add plugin to path
plugin_path = Path(__file__).parent.parent / "MCP Advanced Tools.indigoPlugin/Contents/Server Plugin"
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
