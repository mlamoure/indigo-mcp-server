"""
Tests for IndiDbStructureStore (mtime caching, degradation) and the
reverse-reference index built over the fixture database.
"""

import os
import shutil
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

plugin_path = Path(__file__).parent.parent / "MCP Server.indigoPlugin/Contents/Server Plugin"
sys.path.insert(0, str(plugin_path))

from mcp_server.adapters.indidb.store import IndiDbStructureStore  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "sample_indidb.xml"


def make_store(path, throttle=0.0):
    return IndiDbStructureStore(
        db_path_supplier=lambda: str(path), logger=Mock(), stat_throttle_seconds=throttle
    )


@pytest.fixture
def store():
    return make_store(FIXTURE)


class TestCaching:
    def test_same_mtime_returns_same_parse(self, tmp_path):
        db = tmp_path / "db.indiDb"
        shutil.copy(FIXTURE, db)
        store = make_store(db)
        first = store._ensure_fresh()
        second = store._ensure_fresh()
        assert first is second

    def test_mtime_change_triggers_reparse(self, tmp_path):
        db = tmp_path / "db.indiDb"
        shutil.copy(FIXTURE, db)
        store = make_store(db)
        first = store._ensure_fresh()
        os.utime(db, (1, 1))
        second = store._ensure_fresh()
        assert first is not second

    def test_corrupt_rewrite_retains_last_good_parse(self, tmp_path):
        db = tmp_path / "db.indiDb"
        shutil.copy(FIXTURE, db)
        store = make_store(db)
        good = store._ensure_fresh()
        assert good is not None
        db.write_text("<?xml version='1.0'?><Database type='dict'><Trigg")
        os.utime(db, (2, 2))
        assert store._ensure_fresh() is good

    def test_missing_file_returns_none(self, tmp_path):
        store = make_store(tmp_path / "nope.indiDb")
        assert store._ensure_fresh() is None
        assert store.get_structure("trigger", 1) is None
        assert store.find_references("device", 1) == []
        assert store.freshness() == {"available": False}

    def test_path_supplier_exception_degrades(self):
        def boom():
            raise RuntimeError("no server")

        store = IndiDbStructureStore(db_path_supplier=boom, logger=Mock())
        assert store._ensure_fresh() is None


class TestAccessors:
    def test_get_structure(self, store):
        trigger = store.get_structure("trigger", 4000001)
        assert trigger["Name"] == "Front door opens at night"
        assert store.get_structure("schedule", 5000001)["Name"] == "Run Goodnight at Sunset"
        assert store.get_structure("action_group", 3000001)["Name"] == "Evening Scene"
        assert store.get_structure("trigger", 12345) is None
        assert store.get_structure("bogus_kind", 4000001) is None

    def test_lookup_name(self, store):
        assert store.lookup_name("device", 1000111) == "Porch Light"
        assert store.lookup_name("variable", 2000888) == "isDaytime"
        assert store.lookup_name("action_group", 3000002) == "Goodnight"
        assert store.lookup_name("trigger", 4000002) == "Camera sees a person"
        assert store.lookup_name("schedule", 5000001) == "Run Goodnight at Sunset"
        assert store.lookup_name("device", 42) is None

    def test_freshness(self, store):
        fresh = store.freshness()
        assert fresh["available"] is True
        assert fresh["counts"] == {"triggers": 3, "schedules": 1, "action_groups": 2}
        assert "file_modified" in fresh


class TestReverseIndex:
    def _refs_by_key(self, refs):
        return {(r["entity_type"], r["id"], r["role"]) for r in refs}

    def test_trigger_watches_device(self, store):
        refs = store.find_references("device", 1000222)
        assert ("trigger", 4000001, "watches") in self._refs_by_key(refs)

    def test_device_acted_on_directly_and_via_chain(self, store):
        refs = store.find_references("device", 1000111)
        keys = self._refs_by_key(refs)
        # Direct action steps
        assert ("action_group", 3000001, "acts_on") in keys
        assert ("trigger", 4000001, "acts_on") in keys
        # Condition read (trigger 4000001 checks Porch Light state)
        assert ("trigger", 4000001, "condition_reads") in keys
        # Transitive: Goodnight executes Evening Scene which acts on the light
        chained = [r for r in refs if r.get("via_action_groups")]
        chain_keys = {(r["entity_type"], r["id"]) for r in chained}
        assert ("action_group", 3000002) in chain_keys
        assert ("trigger", 4000001) in chain_keys
        assert ("schedule", 5000001) in chain_keys
        schedule_ref = next(r for r in chained if r["entity_type"] == "schedule")
        assert schedule_ref["via_action_groups"] == [3000002, 3000001]

    def test_variable_roles(self, store):
        set_refs = self._refs_by_key(store.find_references("variable", 2000999))
        assert ("trigger", 4000001, "sets") in set_refs

        read_refs = self._refs_by_key(store.find_references("variable", 2000888))
        assert ("trigger", 4000001, "condition_reads") in read_refs
        assert ("schedule", 5000001, "condition_reads") in read_refs

    def test_action_group_executes(self, store):
        refs = self._refs_by_key(store.find_references("action_group", 3000002))
        assert ("trigger", 4000001, "executes") in refs
        assert ("schedule", 5000001, "executes") in refs

    def test_plugin_config_heuristic(self, store):
        refs = store.find_references("device", 1000333)
        heuristic = [r for r in refs if r["role"] == "plugin_config_reference"]
        keys = {(r["entity_type"], r["id"]) for r in heuristic}
        # AG step config and plugin-trigger MetaProps both name the Sonos id
        assert ("action_group", 3000001) in keys
        assert ("trigger", 4000002) in keys
        assert all(r["confidence"] == "heuristic" for r in heuristic)
