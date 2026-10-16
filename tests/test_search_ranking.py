"""
Tests for search ranking and index hygiene (indigo-mcp-server#72).

Pure helpers (name normalization, index text, score blend) run everywhere.
The VectorStore tests need the real lancedb native library and skip in CI,
where .gitea/ci_stubs shadows it; they use deterministic fake embeddings, so
they make no network calls.
"""

import hashlib
import json
import logging
import math
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

plugin_path = Path(__file__).parent.parent / "MCP Advanced Tools.indigoPlugin/Contents/Server Plugin"
sys.path.insert(0, str(plugin_path))

import lancedb  # noqa: E402

from mcp_server.common.vector_store import main as vs_main  # noqa: E402
from mcp_server.common.vector_store.main import (  # noqa: E402
    build_document_text,
    build_name_text,
    combine_scores,
    device_class_for,
    query_coverage,
    normalize_name,
    readable_model,
)
from mcp_server.common.vector_store.semantic_keywords import (  # noqa: E402
    _generate_device_keywords,
    _generate_variable_keywords,
)

HAS_LANCEDB = hasattr(lancedb, "__version__")
needs_lancedb = pytest.mark.skipif(
    not HAS_LANCEDB, reason="real lancedb unavailable (CI stub)"
)


# ----------------------------------------------------------------------
# Name normalization and overlap


@pytest.mark.parametrize(
    "a,b",
    [
        ("Living Room Lamp", "living room lamp"),
        ("  Living   Room Lamp ", "living room lamp"),
        ("alarm_enabled", "alarm enabled"),
        ("isNightTime", "is night time"),
        ("Espresso Machine - On", "espresso machine on"),
        ("Garage Door (radgo via HA)", "garage door radgo via ha"),
    ],
)
def test_normalize_name_equal(a, b):
    assert normalize_name(a) == normalize_name(b)


def test_normalize_name_distinguishes_suffix():
    assert normalize_name("Living Room Lamp 2") != normalize_name("living room lamp")


def test_query_coverage_plural_and_stopwords():
    assert query_coverage("kitchen lights", "Kitchen Light") == 1.0
    assert query_coverage("light over the kitchen island", "Kitchen Island Lights") == 1.0
    assert query_coverage("porch light", "Front Door Outside Lights") == 0.5
    assert query_coverage("the", "anything") == 0.0


def test_query_coverage_counts_keyword_aliases():
    tv_light = build_document_text(
        {"name": "Basement TV Area Ceiling Light", "class": "indigo.DimmerDevice"},
        "devices",
        _generate_device_keywords({"name": "Basement TV Area Ceiling Light"}),
    )
    assert query_coverage("media room lights", tv_light) == 1.0


def test_combine_scores_prefers_name_match_on_ties():
    doc, name = 0.80, 0.80
    assert combine_scores(doc, name, 1.0) > combine_scores(doc, name, 0.5)
    # a much better name vector outweighs a slightly better document vector
    assert combine_scores(0.80, 0.95, 0.0) > combine_scores(0.82, 0.80, 0.0)


# ----------------------------------------------------------------------
# Index text


LAMP = {
    "id": 1183208037,
    "name": "Living Room Lamp",
    "class": "indigo.RelayDevice",
    "deviceTypeId": "zwRelayType",
    "model": "Smart Switch 6 (ZW096)",
    "address": "5",
    "protocol": "indigo.kProtocol.ZWave",
    "description": "",
    "enabled": True,
    "batteryLevel": None,
}


def test_device_text_keeps_hardware_noise_out():
    text = build_document_text(LAMP, "devices", ["lamp", "living room"])
    assert text.startswith("Living Room Lamp. ")
    assert "on/off switch" in text and "Smart Switch 6" in text
    for noise in ("ZW096", "kProtocol", "zwave", '"address"', "{"):
        assert noise.lower() not in text.lower()
    assert text.endswith("Keywords: lamp, living room.")


def test_variable_texts_are_humanized():
    variable = {"id": 7, "name": "alarm_enabled", "description": ""}
    assert build_name_text(variable, "variables") == "alarm enabled"
    assert build_document_text(variable, "variables").startswith("alarm enabled. variable")


def test_readable_model_drops_part_numbers():
    assert readable_model("Smart Switch 6 (ZW096)") == "Smart Switch 6"
    assert readable_model("PD5WS-DH Dimmer") == "Dimmer"
    assert readable_model("Nest Thermostat") == "Nest Thermostat"


def test_device_class_for():
    assert device_class_for(LAMP, "devices") == "relay"
    assert device_class_for({"class": "indigo.DimmerDevice"}, "devices") == "dimmer"
    assert device_class_for({"name": "x"}, "variables") == ""


def test_rule_keywords_exclude_state_and_hardware():
    keywords = _generate_device_keywords(dict(LAMP, batteryLevel=10))
    assert {"living room", "family room", "lamp", "light"} <= keywords
    for noise in ("enabled", "low_battery", "smart switch 6 (zw096)", "indigo.kprotocol.zwave"):
        assert noise not in keywords


def test_rule_keywords_never_cross_rooms():
    keywords = _generate_device_keywords({"name": "Front Guest Bedroom Lamp"})
    assert "front door" not in keywords
    keywords = _generate_device_keywords({"name": "Living Room Ceiling Lights"})
    assert "lamp" not in keywords  # a ceiling light is not a lamp
    # other names for the same place are added
    assert "front porch" in _generate_device_keywords({"name": "Front Door Outside Lights"})
    assert "media room" in _generate_device_keywords({"name": "Basement TV Area Ceiling Light"})


def test_variable_keywords_ignore_value():
    keywords = _generate_variable_keywords({"name": "porch_light_state", "value": "true"})
    assert "true" not in keywords and "boolean_string" not in keywords


# ----------------------------------------------------------------------
# VectorStore with real lancedb and fake embeddings


def _fake_vector(text: str) -> list:
    """Deterministic unit vector per text (1536 dims), bag-of-words based."""
    vec = [0.0] * 1536
    for word in normalize_name(text).split():
        digest = hashlib.sha256(word.encode()).digest()
        for i in range(0, 12, 2):
            vec[int.from_bytes(digest[i:i + 2], "big") % 1536] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _fake_batch(texts, entity_names=None, progress_callback=None):
    return [_fake_vector(t) for t in texts]


def _device(entity_id, name, cls="indigo.RelayDevice", **extra):
    return dict({"id": entity_id, "name": name, "class": cls, "deviceTypeId": "x",
                 "model": "", "description": ""}, **extra)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")
    with patch.object(vs_main, "emb_texts_batch", side_effect=_fake_batch), \
         patch.object(vs_main, "generate_batch_device_keywords", return_value={}):
        yield vs_main.VectorStore(str(tmp_path / "db"), logger=logging.getLogger("test"))


DEVICES = [
    _device(1, "Living Room Ceiling Lights", "indigo.DimmerDevice"),
    _device(2, "Living Room Lamp"),
    _device(3, "Living Room Lamp 2"),
    _device(4, "Basement TV Area Ceiling Light", "indigo.DimmerDevice"),
    _device(5, "Kitchen Lights", "indigo.DimmerDevice"),
]


def _sync(store, devices=DEVICES, variables=(), actions=()):
    with patch.object(vs_main, "emb_texts_batch", side_effect=_fake_batch), \
         patch.object(vs_main, "generate_batch_device_keywords", return_value={}):
        store.update_embeddings(list(devices), list(variables), list(actions), [], [])


def _search(store, query, **kwargs):
    with patch.object(vs_main, "emb_texts_batch", side_effect=_fake_batch):
        return store.search(query, similarity_threshold=0.0, **kwargs)


@needs_lancedb
def test_exact_name_is_pinned_first(store):
    _sync(store)
    # Make the ceiling lights the best vector match for the query words
    with patch.object(vs_main, "emb_texts_batch",
                      side_effect=lambda texts, *a, **k: [_fake_vector("Living Room Ceiling Lights")] * len(texts)):
        results, _ = store.search("living room lamp", similarity_threshold=0.0)
    assert results[0]["name"] == "Living Room Lamp"
    assert results[0]["_similarity_score"] == 1.0
    assert all(r["_similarity_score"] < 1.0 for r in results[1:])


@needs_lancedb
def test_exact_name_matches_across_entity_types(store):
    _sync(store, variables=[{"id": 9, "name": "alarm_enabled", "description": ""}],
          actions=[{"id": 8, "name": "Espresso Machine - On", "description": ""}])
    results, _ = _search(store, "espresso machine on")
    assert (results[0]["name"], results[0]["_entity_type"]) == ("Espresso Machine - On", "action")
    results, _ = _search(store, "alarm enabled")
    assert (results[0]["name"], results[0]["_entity_type"]) == ("alarm_enabled", "variable")


@needs_lancedb
def test_device_class_prefilter_and_counts(store):
    _sync(store)
    results, meta = _search(store, "lights", entity_types=["devices"], device_classes=["relay"], top_k=1)
    assert [r["name"] for r in results][0] in {"Living Room Lamp", "Living Room Lamp 2"}
    assert meta["total_found"] == 2 and meta["truncated"] is True
    results, _ = _search(store, "lights", entity_types=["devices"], device_classes=["relay"], top_k=40)
    assert {r["name"] for r in results} == {"Living Room Lamp", "Living Room Lamp 2"}


@needs_lancedb
def test_expanded_query_keeps_better_score(store):
    _sync(store)
    plain, _ = _search(store, "entryway", entity_types=["devices"])
    expanded, _ = _search(store, "entryway", entity_types=["devices"], expanded_query="kitchen lights")
    assert expanded[0]["name"] == "Kitchen Lights"
    assert expanded[0]["_similarity_score"] > next(
        r["_similarity_score"] for r in plain if r["name"] == "Kitchen Lights"
    )


@needs_lancedb
def test_resync_never_duplicates_and_repairs_duplicates(store):
    _sync(store)
    renamed = [dict(d, name=d["name"] + " X") if d["id"] == 2 else d for d in DEVICES]
    _sync(store, renamed)
    table = store.db.open_table("devices")
    assert table.count_rows() == len(DEVICES)

    # An old index with several copies of one id is repaired on the next sync
    row = table.search().where("id = 3").limit(1).to_list()[0]
    row = {k: v for k, v in row.items() if not k.startswith("_")}
    table.add([row, row])
    assert table.count_rows() == len(DEVICES) + 2
    _sync(store, renamed)
    # A lancedb table handle does not see later writes from other handles
    table = store.db.open_table("devices")
    ids = [r["id"] for r in table.search().select(["id"]).limit(100).to_list()]
    assert len(ids) == len(set(ids)) == len(DEVICES)


@needs_lancedb
def test_orphans_removed(store):
    _sync(store)
    _sync(store, DEVICES[:3])
    assert store.db.open_table("devices").count_rows() == 3


@needs_lancedb
def test_format_change_rebuilds_index(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")
    path = str(tmp_path / "db")
    store = vs_main.VectorStore(path, logger=logging.getLogger("test"))
    _sync(store)
    assert store.db.open_table("devices").count_rows() == len(DEVICES)

    # Same format: kept
    store = vs_main.VectorStore(path, logger=logging.getLogger("test"))
    assert store.db.open_table("devices").count_rows() == len(DEVICES)

    # Embedding model change: rebuilt empty, then repopulated by the next sync
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    store = vs_main.VectorStore(path, logger=logging.getLogger("test"))
    assert store.db.open_table("devices").count_rows() == 0

    # Index format bump: rebuilt
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")
    store = vs_main.VectorStore(path, logger=logging.getLogger("test"))
    _sync(store)
    monkeypatch.setattr(vs_main, "INDEX_FORMAT_VERSION", "999")
    store = vs_main.VectorStore(path, logger=logging.getLogger("test"))
    assert store.db.open_table("devices").count_rows() == 0

    # Keyword rules edited (no version bump): rebuilt
    _sync(store)
    monkeypatch.setattr(vs_main, "keyword_rules_fingerprint", lambda: "edited-rules")
    store = vs_main.VectorStore(path, logger=logging.getLogger("test"))
    assert store.db.open_table("devices").count_rows() == 0


@needs_lancedb
def test_legacy_schema_without_metadata_is_rebuilt(tmp_path, monkeypatch):
    import pyarrow as pa
    path = str(tmp_path / "db")
    db = lancedb.connect(path)
    legacy = pa.schema([pa.field("id", pa.int64()), pa.field("name", pa.string()),
                        pa.field("embedding", pa.list_(pa.float32(), 1536))])
    for name in vs_main.ENTITY_TABLES:
        db.create_table(name, schema=legacy)
    store = vs_main.VectorStore(path, logger=logging.getLogger("test"))
    assert "name_embedding" in store.db.open_table("devices").schema.names


@needs_lancedb
def test_stored_text_and_columns(store):
    _sync(store, [dict(_device(2, "Living Room Lamp"), model="Smart Switch 6 (ZW096)", address="5")])
    row = store.db.open_table("devices").search().limit(1).to_list()[0]
    assert row["device_class"] == "relay"
    assert "ZW096" not in row["text"] and row["text"].startswith("Living Room Lamp.")
    assert json.loads(row["data"])["address"] == "5"  # still in the stored data
    assert len(row["name_embedding"]) == 1536


# ----------------------------------------------------------------------
# Search handler: window, pre-filter, pagination


def _handler(results, total_found=None):
    from mcp_server.tools.search_entities.main import SearchEntitiesHandler

    store = Mock()
    store.search.return_value = (
        [dict(r) for r in results],
        {"total_found": total_found or len(results), "total_returned": len(results),
         "truncated": (total_found or 0) > len(results)},
    )
    provider = Mock()
    for lookup in ("get_device", "get_variable", "get_action", "get_trigger", "get_schedule"):
        getattr(provider, lookup).return_value = None
    handler = SearchEntitiesHandler(data_provider=provider, vector_store=store, logger=Mock())
    handler.query_parser.expand_query = Mock(return_value="expanded words")
    return handler, store


def _hit(i, kind, name, score):
    return {"id": i, "name": name, "_entity_type": kind, "_similarity_score": score}


def test_limit_and_offset_drive_window_and_prefilter():
    relays = [dict(_hit(i, "device", f"Relay {i}", 0.9), **{"class": "indigo.RelayDevice"}) for i in range(40)]
    handler, store = _handler(relays, total_found=141)
    result = handler.search("Living Room Lamp", device_types=["relay"], limit=40)
    kwargs = store.search.call_args.kwargs
    assert kwargs["top_k"] == 40
    assert kwargs["device_classes"] == ["relay"]
    assert kwargs["query"] == "Living Room Lamp" and kwargs["expanded_query"] == "expanded words"
    assert result["pagination"]["returned_count"] == 40
    assert result["pagination"]["total_count"] == 141
    assert result["pagination"]["has_more"] is True

    handler, store = _handler([])
    handler.search("x", limit=5, offset=30)
    assert store.search.call_args.kwargs["top_k"] == 35
    handler.search("x")
    assert store.search.call_args.kwargs["top_k"] == 10  # default window unchanged


def test_pagination_follows_global_rank():
    hits = [_hit(100, "action", "Turn off Basement AVR", 1.0)] + [
        _hit(i, "device", f"Basement AVR {i}", 0.9 - i / 100) for i in range(9)
    ]
    handler, _ = _handler(hits, total_found=50)
    result = handler.search("Turn off Basement AVR", limit=3)
    assert [a["name"] for a in result["results"]["actions"]] == ["Turn off Basement AVR"]
    assert len(result["results"]["devices"]) == 2


def test_large_windows_use_minimal_device_fields():
    hits = [dict(_hit(i, "device", f"Light {i}", 0.8), pluginProps={"big": "x" * 50}) for i in range(30)]
    handler, _ = _handler(hits)
    result = handler.search("lights", limit=30)
    assert "pluginProps" not in result["results"]["devices"][0]
    handler, _ = _handler(hits[:5])
    result = handler.search("lights", limit=5)
    assert "pluginProps" in result["results"]["devices"][0]
