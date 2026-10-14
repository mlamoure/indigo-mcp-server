"""
LanceDB vector store for semantic search of Indigo entities.
Handles embeddings for devices, variables, actions, triggers, and schedules.

Ranking (indigo-mcp-server#72): every entity carries two vectors — a
document vector (a natural-language line: name, kind, description,
keywords) and a name-only vector. A query is scored as a blend of both plus
a small bonus for the share of its words found in the indexed text, for the user's own words and for the
LLM-expanded query, and each entity keeps its better score. An exact
(normalized) name match is always ranked first.
"""

import datetime
import hashlib
import json
import logging
import os
import re
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import lancedb
import pyarrow as pa

from ...adapters.vector_store_interface import VectorStoreInterface
from ..indigo_device_types import DeviceClassifier, IndigoDeviceType
from ..openai_client.main import (
    EMBEDDING_DIMENSIONS,
    emb_text,
    emb_texts_batch,
    get_embedding_model,
)
from .progress_tracker import create_progress_tracker
from .semantic_keywords import generate_batch_device_keywords, keyword_rules_fingerprint


# Entity tables managed by the vector store
ENTITY_TABLES = ["devices", "variables", "actions", "triggers", "schedules"]

# Bump whenever the indexed text or the table schema changes. A stored value
# that differs rebuilds every table, exactly like an embedding-model change.
# The stored format also carries keyword_rules_fingerprint(), so edits to the
# keyword rules rebuild without a bump.
#   1: JSON blob + keywords, one vector (through 2026.10.0)
#   2: natural-language text, name vector, device_class column
INDEX_FORMAT_VERSION = "2"

# Field classification constants - define which fields are static vs dynamic
STATIC_FIELDS = {
    "devices": {"id", "name", "description", "model", "deviceTypeId", "pluginId",
                "address", "protocol", "class"},
    "variables": {"id", "name", "description", "folderId"},
    "actions": {"id", "name", "description", "folderId"},
    "triggers": {"id", "name", "description", "folderId", "type", "deviceId",
                 "stateSelector", "stateValue", "variableId", "pluginId", "pluginTypeId"},
    "schedules": {"id", "name", "description", "folderId", "date_type", "time_type", "absolute_time"},
}

# Scoring knobs (see combine_scores()). Similarities are 1 - cosine_distance / 2,
# i.e. in [0, 1] with 0.5 for orthogonal vectors. Tuned on a 29-query golden
# set plus ~110 partial-name queries against a production index: a pure max of
# the two vectors let a name that merely sounds close (a porch illuminance
# sensor for "porch light") beat the device whose keywords say porch, and a
# word-overlap bonus on the name alone let "Auto Lights Zone - Downstairs
# Entryway" beat "Foyer Light" (keywords: entryway) for "entryway light".
DOC_WEIGHT = 0.6             # document vector (name, kind, description, keywords)
NAME_WEIGHT = 0.4            # name-only vector
COVERAGE_WEIGHT = 0.05       # bonus per fraction of query words found in the indexed text
EXACT_MATCH_SCORE = 1.0      # score reported for an exact (normalized) name match

# Run table.optimize() (compaction + old-version cleanup) at most this often
OPTIMIZE_INTERVAL_SECONDS = 6 * 3600
OPTIMIZE_KEEP_VERSIONS_FOR = datetime.timedelta(hours=1)

# Human-readable kind for each Indigo device class
_DEVICE_CLASS_KIND = {
    "indigo.DimmerDevice": "dimmer",
    "indigo.RelayDevice": "on/off switch",
    "indigo.SensorDevice": "sensor",
    "indigo.ThermostatDevice": "thermostat",
    "indigo.SpeedControlDevice": "speed control",
    "indigo.SprinklerDevice": "sprinkler controller",
    "indigo.MultiIODevice": "input/output module",
    "indigo.Device": "device",
}

_STOPWORDS = {"a", "an", "the", "of", "in", "on", "at", "to", "for", "over", "by", "and", "or", "my"}


class DateTimeJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime objects."""

    def default(self, obj):
        if isinstance(obj, (datetime.datetime, datetime.date, datetime.time)):
            return obj.isoformat()
        return super().default(obj)


# ----------------------------------------------------------------------
# Text helpers (pure; unit-tested)


def humanize_identifier(text: str) -> str:
    """'alarm_enabled' -> 'alarm enabled', 'isNightTime' -> 'is Night Time'."""
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text or "")
    text = re.sub(r"[_\-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_name(text: str) -> str:
    """
    Normalize a name or query for exact-match comparison: split identifiers,
    drop punctuation, casefold, collapse whitespace. 'Living  Room Lamp' ==
    'living room lamp'; 'alarm_enabled' == 'alarm enabled'.
    """
    text = humanize_identifier(text)
    text = re.sub(r"[^\w\s]", " ", text).replace("_", " ")
    return re.sub(r"\s+", " ", text).strip().casefold()


def _stem(word: str) -> str:
    # Plural-insensitive matching only ("lights" ~ "light"); deliberately crude
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def name_tokens(text: str) -> Set[str]:
    return {_stem(w) for w in normalize_name(text).split() if w not in _STOPWORDS}


def query_coverage(query: str, text: str) -> float:
    """Fraction of the query's words (stopwords dropped, plural-insensitive) found in the text."""
    q = name_tokens(query)
    if not q:
        return 0.0
    return len(q & name_tokens(text)) / len(q)


def readable_model(model: str) -> str:
    """Drop part-number noise from a model string: 'Smart Switch 6 (ZW096)' -> 'Smart Switch 6'."""
    text = re.sub(r"\([^)]*\)", " ", model or "")
    words = [
        w for w in text.split()
        # alphanumeric codes such as ZW096, PD5WS-DH, 3210-L
        if not (re.search(r"\d", w) and re.search(r"[A-Za-z]", w) and len(w) > 2)
    ]
    return " ".join(words).strip(" -,/")


def device_kind(entity: Dict[str, Any]) -> str:
    """'on/off switch, zw relay, Smart Switch 6' — what the device is, in words."""
    parts: List[str] = []
    kind = _DEVICE_CLASS_KIND.get(entity.get("class", ""), "")
    if kind:
        parts.append(kind)
    type_words = humanize_identifier(entity.get("deviceTypeId", "") or "").lower()
    type_words = re.sub(r"\s*\btype$", "", type_words).strip()
    if type_words and type_words not in parts:
        parts.append(type_words)
    model = readable_model(entity.get("model", "") or "")
    if model and model.lower() not in parts:
        parts.append(model)
    return ", ".join(parts)


def build_name_text(entity: Dict[str, Any], entity_type: str) -> str:
    """Text for the name vector: the entity's name, as words."""
    name = entity.get("name", "") or ""
    if entity_type == "variables":
        return humanize_identifier(name)
    return name.strip()


def build_document_text(
    entity: Dict[str, Any], entity_type: str, keywords: Optional[Iterable[str]] = None
) -> str:
    """
    Natural-language line for the document vector, e.g.
    'Living Room Lamp. on/off switch, zw relay, Smart Switch 6. Keywords: lamp, light, living room.'

    Addresses, protocols and model numbers stay in the stored data but out
    of the embedded text: they pulled vectors toward hardware rather than
    meaning (indigo-mcp-server#72).
    """
    parts = [build_name_text(entity, entity_type) or f"ID {entity.get('id')}"]

    if entity_type == "devices":
        kind = device_kind(entity)
    elif entity_type == "variables":
        kind = "variable"
    elif entity_type == "actions":
        kind = "action group"
    elif entity_type == "triggers":
        trigger_type = humanize_identifier(str(entity.get("type") or "")).lower()
        kind = f"trigger ({trigger_type})" if trigger_type else "trigger"
    else:
        kind = "schedule"
    if kind:
        parts.append(kind)

    description = (entity.get("description") or "").strip()
    if description:
        parts.append(description.rstrip("."))

    unique_keywords = sorted({k.strip() for k in (keywords or []) if k and k.strip()})
    if unique_keywords:
        parts.append("Keywords: " + ", ".join(unique_keywords))

    return ". ".join(parts) + "."


def device_class_for(entity: Dict[str, Any], entity_type: str) -> str:
    """Logical device type (dimmer, relay, ...) stored for pre-filtering; '' for non-devices."""
    if entity_type != "devices":
        return ""
    return DeviceClassifier.classify_device(entity)


def combine_scores(doc_sim: float, name_sim: float, coverage: float) -> float:
    """
    One relevance score from the two vector similarities and the query's
    word coverage of the indexed text. The name-only vector is far sharper
    for names; the document vector carries kind, aliases and keywords; the
    coverage breaks the near-ties that pure cosine scores leave, and counts
    keyword aliases ("media room" on a TV-area light), not just the name.
    """
    return DOC_WEIGHT * doc_sim + NAME_WEIGHT * name_sim + COVERAGE_WEIGHT * coverage


def _sql_in(values: Iterable[Any]) -> str:
    return ", ".join(str(int(v)) for v in values)


# ----------------------------------------------------------------------


class VectorStore(VectorStoreInterface):
    """Vector store for Indigo entities using LanceDB."""

    def __init__(self, db_path: str, logger: Optional[logging.Logger] = None):
        """
        Initialize the vector store.

        Args:
            db_path: Path to the LanceDB database directory
            logger: Optional logger instance
        """
        self.db_path = db_path
        self.logger = logger or logging.getLogger("Plugin")
        self.dimension = EMBEDDING_DIMENSIONS
        self.db = None
        self._last_optimize = 0.0

        # Initialize database
        self._init_database()

        # Check and manage embedding model / index format metadata
        self._manage_embedding_metadata()

    def _init_database(self) -> None:
        """Initialize LanceDB database and create tables if needed."""
        try:
            db_dir = os.path.dirname(self.db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)

            self.db = lancedb.connect(self.db_path)
            self.logger.debug(f"Vector database connected at: {self.db_path}")

            existing_tables = self.db.table_names()
            for table_name in ENTITY_TABLES:
                if table_name not in existing_tables:
                    self._create_table(table_name)
        except Exception as e:
            self.logger.error(f"❌ Search index database failed to open: {e}")
            raise

    def _table_schema(self) -> pa.Schema:
        return pa.schema([
            pa.field("id", pa.int64()),
            pa.field("name", pa.string()),
            pa.field("text", pa.string()),  # Document text that was embedded
            pa.field("data", pa.string()),  # JSON representation of full entity
            pa.field("hash", pa.string()),  # Hash of static fields for change detection
            pa.field("device_class", pa.string()),  # dimmer/relay/...; '' for non-devices
            pa.field("embedding", pa.list_(pa.float32(), self.dimension)),
            pa.field("name_embedding", pa.list_(pa.float32(), self.dimension)),
        ])

    def _create_table(self, table_name: str) -> None:
        """Create an empty table for storing entity embeddings."""
        self.db.create_table(table_name, schema=self._table_schema())
        self.logger.debug(f"Created table: {table_name}")

    # ------------------------------------------------------------------
    # Metadata: embedding model + index format

    def _index_signature(self) -> Dict[str, str]:
        return {
            "embedding_model": f"{get_embedding_model()}@{self.dimension}",
            "index_format": f"{INDEX_FORMAT_VERSION}.{keyword_rules_fingerprint()}",
        }

    def _manage_embedding_metadata(self) -> None:
        """Rebuild the index when the embedding model or the index format changed."""
        wanted = self._index_signature()

        if "metadata" not in self.db.table_names():
            self._create_metadata_table()
            if not self._tables_match_schema():
                self._rebuild_vector_store()
            self._store_metadata(wanted)
            self.logger.debug(f"Created metadata table: {wanted}")
            return

        stored = {key: self._get_metadata(key) for key in wanted}
        if stored == wanted and self._tables_match_schema():
            self.logger.debug(f"Search index format verified: {wanted}")
            return

        self.logger.info(
            "📊 Search index format changed — rebuilding the search index "
            "(one-time, may take several minutes)"
        )
        self.logger.debug(f"Index signature {stored} -> {wanted}")
        self._rebuild_vector_store()
        self._store_metadata(wanted)

    def _tables_match_schema(self) -> bool:
        """Every entity table has every column of the current schema."""
        wanted = set(self._table_schema().names)
        for table_name in ENTITY_TABLES:
            try:
                if not wanted.issubset(self.db.open_table(table_name).schema.names):
                    return False
            except Exception:
                return False
        return True

    def _create_metadata_table(self) -> None:
        schema = pa.schema([
            pa.field("key", pa.string()),
            pa.field("value", pa.string()),
            pa.field("updated_at", pa.timestamp('us'))
        ])
        self.db.create_table("metadata", schema=schema)
        self.logger.debug("Created metadata table")

    def _store_metadata(self, values: Dict[str, str]) -> None:
        metadata_table = self.db.open_table("metadata")
        for key, value in values.items():
            try:
                metadata_table.delete(f"key = '{key}'")
            except Exception:
                pass
            metadata_table.add([{
                "key": key,
                "value": value,
                "updated_at": datetime.datetime.now(),
            }])
        self.logger.debug(f"Stored index metadata: {values}")

    def _get_metadata(self, key: str) -> Optional[str]:
        try:
            metadata_table = self.db.open_table("metadata")
            records = metadata_table.search().where(f"key = '{key}'").limit(10).to_list()
            if records:
                return records[0]['value']
        except Exception as e:
            self.logger.debug(f"Could not read index metadata '{key}': {e}")
        return None

    def _rebuild_vector_store(self) -> None:
        """Drop and recreate every entity table; the next sync repopulates them."""
        for table_name in ENTITY_TABLES:
            try:
                self.db.drop_table(table_name)
                self.logger.debug(f"Dropped table: {table_name}")
            except Exception as e:
                self.logger.debug(f"Could not drop table {table_name}: {e}")
        for table_name in ENTITY_TABLES:
            self._create_table(table_name)
        self.logger.debug("Vector store is now empty and will be repopulated by the next sync")

    # ------------------------------------------------------------------
    # Hashing

    def _hash_entity(self, entity: Dict[str, Any]) -> str:
        """Generate hash for entity to detect changes (legacy method)."""
        entity_str = json.dumps(entity, sort_keys=True, cls=DateTimeJSONEncoder)
        return hashlib.sha256(entity_str.encode()).hexdigest()

    def _get_static_fields_only(self, entity: Dict[str, Any], entity_type: str) -> Dict[str, Any]:
        static_fields = STATIC_FIELDS.get(entity_type, set())
        return {k: v for k, v in entity.items() if k in static_fields}

    def _hash_static_fields(self, entity: Dict[str, Any], entity_type: str) -> str:
        """SHA256 of the static fields only (state changes do not re-embed)."""
        static_entity = self._get_static_fields_only(entity, entity_type)
        entity_str = json.dumps(static_entity, sort_keys=True, cls=DateTimeJSONEncoder)
        return hashlib.sha256(entity_str.encode()).hexdigest()

    # ------------------------------------------------------------------
    # Embedding

    def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text using common OpenAI client."""
        try:
            return emb_text(text)
        except Exception as e:
            self.logger.error(f"❌ Search index embedding request failed: {e}")
            raise

    def _generate_embeddings_batch(
        self,
        texts: List[str],
        entity_names: Optional[List[str]] = None,
        progress_callback: Optional[callable] = None,
    ) -> List[List[float]]:
        """Generate embeddings for multiple texts (empty list per failed text)."""
        try:
            return emb_texts_batch(texts, entity_names, progress_callback)
        except Exception as e:
            self.logger.error(f"❌ Search index embedding request failed: {e}")
            return [[] for _ in texts]

    def _build_records(
        self,
        entities: List[Dict[str, Any]],
        table_name: str,
        keywords_by_id: Dict[str, List[str]],
        progress_callback: Optional[callable] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Embed each entity's document text and name text (one batched pass)
        and return (records, failed_count).
        """
        doc_texts = [
            build_document_text(e, table_name, keywords_by_id.get(str(e["id"]), []))
            for e in entities
        ]
        name_texts = [build_name_text(e, table_name) or f"ID {e['id']}" for e in entities]
        names = [e.get("name", f"ID:{e['id']}") for e in entities]

        vectors = self._generate_embeddings_batch(
            doc_texts + name_texts, names + names, progress_callback
        )
        doc_vectors, name_vectors = vectors[:len(entities)], vectors[len(entities):]

        records = []
        failed = 0
        for entity, text, doc_vec, name_vec in zip(entities, doc_texts, doc_vectors, name_vectors):
            if not doc_vec or not name_vec:
                failed += 1
                continue
            records.append({
                "id": entity["id"],
                "name": entity.get("name", ""),
                "text": text,
                "data": json.dumps(entity, cls=DateTimeJSONEncoder),
                "hash": self._hash_static_fields(entity, table_name),
                "device_class": device_class_for(entity, table_name),
                "embedding": doc_vec,
                "name_embedding": name_vec,
            })
        return records, failed

    def _upsert(self, table, records: List[Dict[str, Any]]) -> None:
        """Insert or replace records by id (never appends a second copy)."""
        unique = list({r["id"]: r for r in records}.values())
        (
            table.merge_insert("id")
            .when_matched_update_all()
            .when_not_matched_insert_all()
            .execute(unique)
        )

    # ------------------------------------------------------------------
    # Sync

    def update_embeddings(
        self,
        devices: List[Dict[str, Any]],
        variables: List[Dict[str, Any]],
        actions: List[Dict[str, Any]],
        triggers: Optional[List[Dict[str, Any]]] = None,
        schedules: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        """Update embeddings for all entity types."""
        self._update_entity_embeddings("devices", devices)
        self._update_entity_embeddings("variables", variables)
        self._update_entity_embeddings("actions", actions)
        if triggers is not None:
            self._update_entity_embeddings("triggers", triggers)
        if schedules is not None:
            self._update_entity_embeddings("schedules", schedules)
        self._maybe_optimize()

    def _duplicate_ids(self, table) -> Set[int]:
        """Ids stored more than once (pre-2026.10.1 indexes accumulated copies)."""
        ids = [row["id"] for row in table.search().select(["id"]).limit(10_000_000).to_list()]
        seen: Set[int] = set()
        dupes: Set[int] = set()
        for entity_id in ids:
            if entity_id in seen:
                dupes.add(entity_id)
            seen.add(entity_id)
        return dupes

    def _update_entity_embeddings(
        self,
        table_name: str,
        entities: List[Dict[str, Any]],
        batch_size: int = None  # Auto-calculate optimal batch size for keyword generation
    ) -> None:
        """Bring one table in line with the current entities (changed, missing, orphaned, duplicated)."""
        if not entities:
            self.logger.debug(f"No {table_name} entities to process")
            return

        try:
            table = self.db.open_table(table_name)
            valid_entities = [e for e in entities if e.get("id") is not None]

            from .validation import (
                load_validation_data, perform_comprehensive_validation,
                prioritize_updates, log_validation_summary,
            )

            validation_data = load_validation_data(table, self.logger)

            if not validation_data:
                self.logger.debug(f"No existing data found for {table_name}, will create all records")
                entities_to_process = valid_entities
            else:
                validation_result = perform_comprehensive_validation(
                    valid_entities,
                    validation_data,
                    table_name,
                    self._hash_static_fields
                )
                log_validation_summary(validation_result, table_name, self.logger)

                if not validation_result.has_issues():
                    entities_to_process = []
                else:
                    priority_updates = prioritize_updates(validation_result)
                    entities_needing_update = set()
                    entities_needing_update.update(priority_updates.get("critical", []))
                    entities_needing_update.update(priority_updates.get("high", []))
                    entities_needing_update.update(priority_updates.get("medium", []))

                    # Flagged ids absent from the current entity list are
                    # orphans (removed below), not refreshable work
                    entities_to_process = [e for e in valid_entities if e["id"] in entities_needing_update]

                    total_to_refresh = len(entities_to_process)
                    if total_to_refresh:
                        self.logger.info(f"📊 Updating search index for {total_to_refresh} changed {table_name}")
                        if total_to_refresh < 20:
                            entity_names = [e.get("name", f"ID:{e.get('id')}") for e in entities_to_process]
                            self.logger.debug(f"Refreshing embeddings: {', '.join(entity_names)}")

            # Remove orphaned records (entities no longer in Indigo) BEFORE the
            # no-work early return — otherwise orphans survive forever and
            # re-flag on every sync cycle.
            if validation_data:
                current_ids = {e["id"] for e in valid_entities}
                orphaned_ids = set(validation_data.keys()) - current_ids
                if orphaned_ids:
                    try:
                        table.delete(f"id IN ({_sql_in(orphaned_ids)})")
                        self.logger.debug(f"Removed {len(orphaned_ids)} orphaned {table_name} record(s)")
                    except Exception as e:
                        self.logger.error(f"Error removing orphaned {table_name} records: {e}")

            # Duplicate rows (several copies of one id): delete every copy and
            # re-add the entity once. A merge would update all copies in place.
            if validation_data and table.count_rows() > len(validation_data):
                dupes = self._duplicate_ids(table)
                if dupes:
                    try:
                        table.delete(f"id IN ({_sql_in(dupes)})")
                        self.logger.debug(f"Removed duplicate rows for {len(dupes)} {table_name} id(s)")
                    except Exception as e:
                        self.logger.error(f"Error removing duplicate {table_name} records: {e}")
                    queued = {e["id"] for e in entities_to_process}
                    entities_to_process += [
                        e for e in valid_entities if e["id"] in dupes and e["id"] not in queued
                    ]

            total_updates = len(entities_to_process)
            if total_updates == 0:
                return

            progress = create_progress_tracker(
                f"indexing {table_name}",
                total_updates,
                threshold=10
            )

            # Generate semantic keywords (LLM for devices, rules for the rest)
            all_keywords = generate_batch_device_keywords(
                entities_to_process,
                batch_size=batch_size,
                collection_name=table_name,
                progress_callback=lambda current, message: progress.update(current, message)
            )

            if total_updates >= 20:
                self.logger.info(
                    f"📊 Updating search index for {total_updates} {table_name} — "
                    f"this can take a few minutes on first run"
                )

            def embedding_progress_callback(current_batch, total_batches, batch_size):
                progress.update(total_updates, f"Embedding generation - batch {current_batch}/{total_batches}")
                if current_batch % max(1, total_batches // 10) == 0 or current_batch == total_batches:
                    pct = int((current_batch / total_batches) * 100)
                    self.logger.debug(f"Embedding generation: {pct}% (batch {current_batch}/{total_batches})")

            records, failed_count = self._build_records(
                entities_to_process, table_name, all_keywords, embedding_progress_callback
            )

            if records:
                try:
                    self._upsert(table, records)
                    progress.complete(f"indexed {len(records)} records")
                except Exception as e:
                    self.logger.error(f"Failed to write {table_name} records: {e}")
                    progress.error(f"failed to write {len(records)} records")
                    return
            else:
                progress.complete("no records to write")

            success_count = len(records)
            if failed_count > 0:
                self.logger.warning(
                    f"⚠️ Search index updated with {failed_count} failures ({success_count} of "
                    f"{success_count + failed_count} {table_name} indexed) — affected items may "
                    f"not appear in AI searches"
                )
            self.logger.debug(
                f"{table_name.title()} embeddings updated: {success_count} successful, {failed_count} failed"
            )

        except Exception as e:
            self.logger.error(f"❌ Search index update for {table_name} failed: {e}")
            raise

    def _maybe_optimize(self, force: bool = False) -> None:
        """
        Compact each table and drop old versions. Every write creates a new
        table version; without cleanup the devices table reached 13k
        versions (374 MB) in production.
        """
        now = time.time()
        if not force and now - self._last_optimize < OPTIMIZE_INTERVAL_SECONDS:
            return
        self._last_optimize = now
        for table_name in ENTITY_TABLES:
            try:
                self.db.open_table(table_name).optimize(
                    cleanup_older_than=OPTIMIZE_KEEP_VERSIONS_FOR
                )
            except Exception as e:
                self.logger.debug(f"Search index optimize skipped for {table_name}: {e}")
        self.logger.debug("Search index tables optimized")

    # ------------------------------------------------------------------
    # Search

    def search(
        self,
        query: str,
        entity_types: Optional[List[str]] = None,
        top_k: int = 10,
        similarity_threshold: float = 0.7,
        expanded_query: Optional[str] = None,
        device_classes: Optional[Sequence[str]] = None,
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Search for entities.

        Args:
            query: The user's own search words
            entity_types: Optional list of tables to search (default: all)
            top_k: Maximum number of results to return
            similarity_threshold: Minimum relevance score
            expanded_query: Optional LLM-expanded query; scored alongside the
                original and each entity keeps its better score
            device_classes: Optional logical device types (dimmer, relay, ...)
                applied as a pre-filter inside the devices query

        Returns:
            Tuple of (results with _similarity_score/_entity_type, metadata).
            Metadata: total_found, total_returned, truncated.
        """
        empty_meta = {"total_found": 0, "total_returned": 0, "truncated": False}
        if entity_types is None:
            entity_types = list(ENTITY_TABLES)

        variants = [query]
        if expanded_query and expanded_query.strip() and expanded_query.strip() != query.strip():
            variants.append(expanded_query)
        try:
            vectors = self._generate_embeddings_batch(variants)
            if not vectors or not vectors[0]:
                raise RuntimeError("empty query embedding")
            vectors = [v for v in vectors if v]
        except Exception as e:
            self.logger.error(f"❌ Search failed (couldn't reach OpenAI for the query embedding): {e}")
            return [], empty_meta

        query_norm = normalize_name(query)
        scored: List[Dict[str, Any]] = []  # {table, id, name, score, exact}

        for entity_type in entity_types:
            if entity_type not in ENTITY_TABLES:
                continue
            try:
                scored.extend(self._score_table(entity_type, query, query_norm, vectors, device_classes))
            except Exception as e:
                self.logger.error(f"❌ Search failed for {entity_type}: {e}")

        candidates = [c for c in scored if c["exact"] or c["score"] >= similarity_threshold]
        candidates.sort(key=lambda c: (c["exact"], c["score"]), reverse=True)

        total_found = len(candidates)
        selected = candidates[:top_k]
        results = self._load_results(selected)

        metadata = {
            "total_found": total_found,
            "total_returned": len(results),
            "truncated": total_found > top_k,
        }
        return results, metadata

    def _device_class_filter(self, device_classes: Optional[Sequence[str]]) -> Optional[str]:
        if not device_classes:
            return None
        valid = [c for c in device_classes if IndigoDeviceType.is_valid_type(c)]
        if not valid:
            return "device_class = ''"  # nothing can match an unknown class
        return "device_class IN (" + ", ".join(f"'{c}'" for c in sorted(set(valid))) + ")"

    def _score_table(
        self,
        entity_type: str,
        query: str,
        query_norm: str,
        vectors: List[List[float]],
        device_classes: Optional[Sequence[str]],
    ) -> List[Dict[str, Any]]:
        """Score every row of one table against every query vector."""
        table = self.db.open_table(entity_type)
        where = self._device_class_filter(device_classes) if entity_type == "devices" else None

        row_count = table.count_rows(where) if where else table.count_rows()
        if row_count == 0:
            return []

        best: Dict[int, Dict[str, Any]] = {}
        coverage: Dict[int, float] = {}
        for vector in vectors:
            sims: Dict[str, Dict[int, float]] = {}
            names: Dict[int, str] = {}
            for column in ("embedding", "name_embedding"):
                search = (
                    table.search(vector, vector_column_name=column)
                    .metric("cosine")
                    .select(["id", "name", "text", "_distance"])
                    .limit(row_count)
                )
                if where:
                    search = search.where(where, prefilter=True)
                column_sims: Dict[int, float] = {}
                for row in search.to_list():
                    sim = 1 - (row.get("_distance", 2.0) / 2)
                    entity_id = row["id"]
                    # duplicate rows (old indexes) — keep the best copy
                    if sim > column_sims.get(entity_id, -1.0):
                        column_sims[entity_id] = sim
                    names[entity_id] = row.get("name") or ""
                    if entity_id not in coverage:
                        # the user's own words only: the expansion would
                        # credit every synonym it invented
                        coverage[entity_id] = query_coverage(query, row.get("text") or names[entity_id])
                sims[column] = column_sims

            for entity_id, name in names.items():
                doc_sim = sims["embedding"].get(entity_id, 0.0)
                name_sim = sims["name_embedding"].get(entity_id, 0.0)
                score = combine_scores(doc_sim, name_sim, coverage.get(entity_id, 0.0))
                current = best.get(entity_id)
                if current is None or score > current["score"]:
                    best[entity_id] = {
                        "table": entity_type,
                        "id": entity_id,
                        "name": name,
                        "score": score,
                        "exact": bool(query_norm) and normalize_name(name) == query_norm,
                    }
        return list(best.values())

    def _load_results(self, selected: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Fetch stored entity data for the selected hits, preserving rank order."""
        by_table: Dict[str, List[int]] = {}
        for c in selected:
            by_table.setdefault(c["table"], []).append(c["id"])

        data: Dict[Tuple[str, int], Dict[str, Any]] = {}
        for table_name, ids in by_table.items():
            try:
                rows = (
                    self.db.open_table(table_name)
                    .search()
                    .where(f"id IN ({_sql_in(ids)})")
                    .select(["id", "data"])
                    .limit(len(ids) * 20)  # room for duplicate rows in old indexes
                    .to_list()
                )
                for row in rows:
                    try:
                        data.setdefault((table_name, row["id"]), json.loads(row["data"]))
                    except (TypeError, ValueError):
                        continue
            except Exception as e:
                self.logger.error(f"❌ Loading search results from {table_name} failed: {e}")

        results = []
        for c in selected:
            entity = data.get((c["table"], c["id"]))
            if entity is None:
                continue
            entity = dict(entity)
            entity["_similarity_score"] = EXACT_MATCH_SCORE if c["exact"] else min(c["score"], 0.999)
            entity["_entity_type"] = c["table"][:-1]  # Remove 's' from plural
            results.append(entity)
        return results

    # ------------------------------------------------------------------
    # Single-entity maintenance

    def add_entity(self, entity_type: str, entity_data: Dict[str, Any]) -> None:
        """
        Add or replace a single entity (same text and vectors as a sync).

        Args:
            entity_type: Type of entity ('device', 'variable', 'action', ...)
            entity_data: Entity data dictionary
        """
        table_name = entity_type + "s" if not entity_type.endswith("s") else entity_type
        if table_name not in ENTITY_TABLES or entity_data.get("id") is None:
            self.logger.debug(f"Invalid entity for the search index: {entity_type}")
            return

        try:
            table = self.db.open_table(table_name)
            keywords = generate_batch_device_keywords([entity_data], collection_name=table_name)
            records, failed = self._build_records([entity_data], table_name, keywords)
            if records:
                self._upsert(table, records)
                self.logger.debug(f"Indexed {entity_type} {entity_data.get('id')}")
            else:
                self.logger.error(f"Failed to embed {entity_type} {entity_data.get('id')} for the search index")
        except Exception as e:
            self.logger.error(f"Failed to add {entity_type} to vector store: {e}")

    def remove_entity(self, entity_type: str, entity_id: int) -> None:
        """
        Remove an entity from the vector store.

        Args:
            entity_type: Type of entity ('device', 'variable', 'action')
            entity_id: Entity ID to remove
        """
        table_name = entity_type + "s" if not entity_type.endswith("s") else entity_type
        if table_name not in ENTITY_TABLES:
            self.logger.error(f"Invalid entity type: {entity_type}")
            return

        try:
            table = self.db.open_table(table_name)
            table.delete(f"id = {int(entity_id)}")
            self.logger.debug(f"Removed {entity_type} {entity_id} from vector store")
        except Exception as e:
            self.logger.error(f"Failed to remove {entity_type} {entity_id} from vector store: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the vector store."""
        stats = {
            "database_path": self.db_path,
            "dimension": self.dimension,
            "tables": {}
        }
        for table_name in ENTITY_TABLES:
            try:
                stats["tables"][table_name] = self.db.open_table(table_name).count_rows()
            except Exception:
                stats["tables"][table_name] = 0
        return stats

    def close(self) -> None:
        """Close the database connection."""
        if self.db:
            self.db = None
            self.logger.debug("Database connection closed")
