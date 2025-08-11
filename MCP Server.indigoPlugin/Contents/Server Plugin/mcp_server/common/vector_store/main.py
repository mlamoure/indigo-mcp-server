"""
Simplified LanceDB vector store for semantic search of Indigo entities.
Only handles embeddings for devices, variables, and actions.
"""

import datetime
import hashlib
import json
import logging
import os
from typing import List, Dict, Any, Optional

import lancedb
import pyarrow as pa

from ...adapters.vector_store_interface import VectorStoreInterface
from ..openai_client.main import emb_text, emb_texts_batch
from .progress_tracker import create_progress_tracker
from .semantic_keywords import generate_batch_device_keywords


# Field classification constants - define which fields are static vs dynamic
STATIC_FIELDS = {
    "devices": {"id", "name", "description", "model", "deviceTypeId", "pluginId", "address", "protocol"},
    "variables": {"id", "name", "description", "folderId"},
    "actions": {"id", "name", "description", "folderId"},
}

# Fields for embedding text generation (subset of static fields)
EMBEDDING_FIELDS = {
    "devices": {"name", "description", "model", "deviceTypeId", "address"},
    "variables": {"name", "description"},
    "actions": {"name", "description"},
}


class DateTimeJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime objects."""
    
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        elif isinstance(obj, datetime.date):
            return obj.isoformat()
        elif isinstance(obj, datetime.time):
            return obj.isoformat()
        return super().default(obj)


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
        self.dimension = 1536  # text-embedding-3-small dimension
        self.db = None
        
        # Initialize database
        self._init_database()
        
        # Check and manage embedding model metadata
        self._manage_embedding_metadata()
    
    
    def _init_database(self) -> None:
        """Initialize LanceDB database and create tables if needed."""
        try:
            # Ensure directory exists (only if db_path has a directory part)
            db_dir = os.path.dirname(self.db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
            
            # Connect to LanceDB
            self.db = lancedb.connect(self.db_path)
            self.logger.info(f"Vector database connected at: {self.db_path}")
            
            # Check database path and permissions
            self.logger.debug(f"📂 Database path: {self.db_path}")
            self.logger.debug(f"📂 Database directory exists: {os.path.exists(os.path.dirname(self.db_path))}")
            if os.path.exists(self.db_path):
                self.logger.debug(f"📂 Database file exists: True")
                self.logger.debug(f"📂 Database file size: {os.path.getsize(self.db_path)} bytes")
            else:
                self.logger.debug(f"📂 Database file exists: False")
                
            # Check existing tables
            existing_tables = self.db.table_names()
            self.logger.debug(f"📊 Existing vector store tables: {existing_tables}")
            
            # Initialize tables for each entity type
            for table_name in ["devices", "variables", "actions"]:
                if table_name not in existing_tables:
                    self.logger.debug(f"🆕 Creating new table: {table_name}")
                    self._create_table(table_name)
                else:
                    self.logger.debug(f"✅ Table exists: {table_name}")
                    # For existing tables, try to get basic info
                    try:
                        table = self.db.open_table(table_name)
                        row_count = len(table.search().to_list())
                        self.logger.debug(f"📊 Table {table_name} currently has {row_count} rows")
                    except Exception as table_error:
                        self.logger.debug(f"⚠️ Could not check row count for {table_name}: {table_error}")
                    
        except Exception as e:
            self.logger.error(f"Database initialization failed: {e}")
            raise
    
    def _create_table(self, table_name: str) -> None:
        """Create a table for storing entity embeddings."""
        schema = pa.schema([
            pa.field("id", pa.int64()),
            pa.field("name", pa.string()),
            pa.field("text", pa.string()),  # Text used for search
            pa.field("data", pa.string()),  # JSON representation of full entity
            pa.field("hash", pa.string()),  # Hash for change detection
            pa.field("embedding", pa.list_(pa.float32(), self.dimension))
        ])
        
        # Create empty table
        empty_data = pa.Table.from_arrays(
            [
                pa.array([], type=pa.int64()),      # id
                pa.array([], type=pa.string()),     # name
                pa.array([], type=pa.string()),     # text
                pa.array([], type=pa.string()),     # data
                pa.array([], type=pa.string()),     # hash
                pa.array([], type=pa.list_(pa.float32(), self.dimension))  # embedding
            ],
            schema=schema
        )
        
        self.db.create_table(table_name, empty_data)
        self.logger.debug(f"Created table: {table_name}")
    
    def _manage_embedding_metadata(self) -> None:
        """Check and manage embedding model metadata."""
        import os
        current_model = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        
        # Check if metadata table exists
        existing_tables = self.db.table_names()
        if "metadata" not in existing_tables:
            # Create metadata table and store current embedding model
            self._create_metadata_table()
            self._store_embedding_model(current_model)
            self.logger.info(f"📊 Created metadata table with embedding model: {current_model}")
        else:
            # Check stored embedding model
            stored_model = self._get_stored_embedding_model()
            if stored_model is None:
                # No stored model (legacy database), assume current model
                self._store_embedding_model(current_model)
                self.logger.info(f"📊 Legacy database detected, assumed embedding model: {current_model}")
            elif stored_model != current_model:
                # Model has changed, need to rebuild vector store
                self.logger.warning(f"🔄 Embedding model changed from '{stored_model}' to '{current_model}' - vector store rebuild required")
                self._rebuild_vector_store_for_new_model(current_model)
            else:
                self.logger.debug(f"✅ Embedding model verified: {current_model}")
    
    def _create_metadata_table(self) -> None:
        """Create metadata table for storing embedding model information."""
        schema = pa.schema([
            pa.field("key", pa.string()),
            pa.field("value", pa.string()),
            pa.field("updated_at", pa.timestamp('us'))
        ])
        
        # Create empty metadata table
        empty_data = pa.Table.from_arrays(
            [
                pa.array([], type=pa.string()),  # key
                pa.array([], type=pa.string()),  # value  
                pa.array([], type=pa.timestamp('us'))  # updated_at
            ],
            schema=schema
        )
        
        self.db.create_table("metadata", empty_data)
        self.logger.debug("Created metadata table")
    
    def _store_embedding_model(self, model: str) -> None:
        """Store the current embedding model in metadata."""
        import datetime
        
        metadata_table = self.db.open_table("metadata")
        
        # Check if embedding_model key already exists
        try:
            existing_records = metadata_table.search().where(f"key = 'embedding_model'").to_list()
            if existing_records:
                # Update existing record
                metadata_table.delete(f"key = 'embedding_model'")
        except Exception:
            # Table might be empty, continue with insert
            pass
        
        # Insert new/updated record
        new_record = pa.Table.from_arrays([
            pa.array(["embedding_model"]),
            pa.array([model]),
            pa.array([datetime.datetime.now()])
        ], names=["key", "value", "updated_at"])
        
        metadata_table.add(new_record)
        self.logger.debug(f"Stored embedding model: {model}")
    
    def _get_stored_embedding_model(self) -> Optional[str]:
        """Get the stored embedding model from metadata."""
        try:
            metadata_table = self.db.open_table("metadata")
            records = metadata_table.search().where(f"key = 'embedding_model'").to_list()
            if records:
                return records[0]['value']
        except Exception as e:
            self.logger.debug(f"Could not retrieve embedding model metadata: {e}")
        return None
    
    def _rebuild_vector_store_for_new_model(self, new_model: str) -> None:
        """Rebuild the entire vector store when embedding model changes."""
        self.logger.warning("🔄 Rebuilding vector store for new embedding model...")
        
        # Drop all entity tables
        for table_name in ["devices", "variables", "actions"]:
            try:
                self.db.drop_table(table_name)
                self.logger.info(f"Dropped table: {table_name}")
            except Exception as e:
                self.logger.debug(f"Could not drop table {table_name}: {e}")
        
        # Recreate tables
        for table_name in ["devices", "variables", "actions"]:
            self._create_table(table_name)
        
        # Update metadata with new model
        self._store_embedding_model(new_model)
        
        self.logger.info(f"✅ Vector store rebuilt for embedding model: {new_model}")
        self.logger.info("🔄 Note: Vector store is now empty and needs to be repopulated with embeddings")
    
    def _create_embedding_text(self, entity: Dict[str, Any], entity_type: str, semantic_keywords: List[str] = None) -> str:
        """
        Create enhanced text representation for embedding generation with semantic keywords.
        
        Args:
            entity: Entity dictionary
            entity_type: Type of entity (devices, variables, actions)
            semantic_keywords: Optional list of semantic keywords to include
            
        Returns:
            Enhanced text string for embedding
        """
        # Extract only embedding-relevant fields
        embedding_fields = EMBEDDING_FIELDS.get(entity_type, set())
        base_data = {k: v for k, v in entity.items() if k in embedding_fields}
        
        # Create base text from embedding fields
        base_text = json.dumps(base_data, sort_keys=True, cls=DateTimeJSONEncoder)
        
        # Add semantic keywords if provided
        if semantic_keywords:
            keywords_text = " ".join(semantic_keywords)
            enhanced_text = f"{base_text} {keywords_text}"
        else:
            enhanced_text = base_text
        
        return enhanced_text
    
    def _create_embedding_text_legacy(self, entity: Dict[str, Any], entity_type: str) -> str:
        """
        Legacy method for creating simple text representation (kept for compatibility).
        
        Args:
            entity: Entity dictionary
            entity_type: Type of entity (devices, variables, actions)
            
        Returns:
            Text string for embedding
        """
        parts = []
        
        # Add entity type
        parts.append(f"Type: {entity_type[:-1]}")  # Remove 's' from plural
        
        # Add name
        if "name" in entity:
            parts.append(f"Name: {entity['name']}")
        
        # Add type-specific fields
        if entity_type == "devices":
            if "model" in entity and entity["model"]:
                parts.append(f"Model: {entity['model']}")
            if "type" in entity and entity["type"]:
                parts.append(f"Device Type: {entity['type']}")
            if "address" in entity and entity["address"]:
                parts.append(f"Address: {entity['address']}")
                
        elif entity_type == "variables":
            if "value" in entity:
                parts.append(f"Value: {entity['value']}")
                
        # Add description if available
        if "description" in entity and entity["description"]:
            parts.append(f"Description: {entity['description']}")
        
        return " | ".join(parts)
    
    def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text using common OpenAI client."""
        try:
            return emb_text(text)
            
        except Exception as e:
            self.logger.error(f"Failed to generate embedding: {e}")
            raise
    
    def _generate_embeddings_batch(self, texts: List[str], entity_names: List[str] = None, progress_callback: Optional[callable] = None) -> List[List[float]]:
        """Generate embeddings for multiple texts using batch OpenAI API calls with progress tracking."""
        try:
            # Add progress tracking to embedding generation
            if progress_callback:
                self.logger.debug(f"🚀 Starting embedding generation for {len(texts)} texts with progress tracking")
            
            return emb_texts_batch(texts, entity_names, progress_callback)
            
        except Exception as e:
            self.logger.error(f"Failed to generate batch embeddings: {e}")
            # Return empty embeddings for all texts on failure
            return [[] for _ in texts]
    
    def _hash_entity(self, entity: Dict[str, Any]) -> str:
        """Generate hash for entity to detect changes (legacy method)."""
        # Create deterministic string representation using custom encoder
        entity_str = json.dumps(entity, sort_keys=True, cls=DateTimeJSONEncoder)
        return hashlib.sha256(entity_str.encode()).hexdigest()
    
    def _get_static_fields_only(self, entity: Dict[str, Any], entity_type: str) -> Dict[str, Any]:
        """
        Extract only static fields from an entity for hash comparison.
        
        Args:
            entity: The full entity dictionary
            entity_type: Type of entity (devices, variables, actions)
            
        Returns:
            Dictionary with only static fields
        """
        static_fields = STATIC_FIELDS.get(entity_type, set())
        return {k: v for k, v in entity.items() if k in static_fields}
    
    def _hash_static_fields(self, entity: Dict[str, Any], entity_type: str) -> str:
        """
        Generate a hash using only static fields for change detection.
        
        Args:
            entity: The full entity dictionary
            entity_type: Type of entity (devices, variables, actions)
            
        Returns:
            SHA256 hash of static fields only
        """
        static_entity = self._get_static_fields_only(entity, entity_type)
        entity_str = json.dumps(static_entity, sort_keys=True, cls=DateTimeJSONEncoder)
        return hashlib.sha256(entity_str.encode()).hexdigest()
    
    def update_embeddings(
        self,
        devices: List[Dict[str, Any]],
        variables: List[Dict[str, Any]],
        actions: List[Dict[str, Any]]
    ) -> None:
        """
        Update embeddings for all entity types.
        
        Args:
            devices: List of device dictionaries
            variables: List of variable dictionaries
            actions: List of action dictionaries
        """
        # Update each entity type
        self._update_entity_embeddings("devices", devices)
        self._update_entity_embeddings("variables", variables)
        self._update_entity_embeddings("actions", actions)
    
    def _update_entity_embeddings(
        self,
        table_name: str,
        entities: List[Dict[str, Any]],
        batch_size: int = None  # Auto-calculate optimal batch size for keyword generation
    ) -> None:
        """Update embeddings for a specific entity type with enhanced processing."""
        if not entities:
            self.logger.debug(f"No {table_name} entities to process")
            return
            
        try:
            table = self.db.open_table(table_name)
            
            # Filter valid entities (entities with IDs)
            valid_entities = [e for e in entities if e.get("id") is not None]
            
            # Load comprehensive validation data
            from .validation import load_validation_data, perform_comprehensive_validation, prioritize_updates, log_validation_summary
            
            validation_data = load_validation_data(table, self.logger)
            
            if not validation_data:
                self.logger.debug(f"🔍 No existing data found for {table_name}, will create all records")
                # All entities need to be created
                entities_to_process = valid_entities
            else:
                # Perform comprehensive validation
                validation_result = perform_comprehensive_validation(
                    valid_entities, 
                    validation_data, 
                    table_name, 
                    self._hash_static_fields
                )
                
                # Log validation summary
                log_validation_summary(validation_result, table_name, self.logger)
                
                if not validation_result.has_issues():
                    # All entities are valid, no updates needed
                    entities_to_process = []
                else:
                    # Get prioritized update list
                    priority_updates = prioritize_updates(validation_result)
                    
                    # Combine all entities that need updates
                    entities_needing_update = set()
                    entities_needing_update.update(priority_updates.get("critical", []))
                    entities_needing_update.update(priority_updates.get("high", []))
                    entities_needing_update.update(priority_updates.get("medium", []))
                    
                    # Filter entities to only those needing updates
                    entities_to_process = [e for e in valid_entities if e["id"] in entities_needing_update]
                    
                    # Log what's being refreshed
                    total_to_refresh = len(entities_needing_update)
                    if total_to_refresh < 20:
                        # List specific entity names when small number
                        entity_names = []
                        for e in entities_to_process[:20]:
                            entity_names.append(e.get("name", f"ID:{e.get('id')}"))
                        self.logger.info(f"Refreshing embeddings for {total_to_refresh} {table_name}: {', '.join(entity_names)}")
                    else:
                        # Just show count for larger updates
                        self.logger.info(f"Refreshing embeddings for {total_to_refresh} {table_name}")
            
            total_updates = len(entities_to_process)
            
            if total_updates == 0:
                self.logger.debug(f"All {table_name} embeddings are up to date")
                return
            
            # Show update summary at debug level unless significant
            if total_updates > 50:
                self.logger.info(f"📊 Processing {total_updates} {table_name} entities")
            else:
                self.logger.debug(f"📊 Processing {total_updates} {table_name} entities")
            
            # Initialize progress tracking
            progress = create_progress_tracker(
                f"{table_name.title()} Embeddings", 
                total_updates,
                threshold=10
            )
            
            # Generate semantic keywords in batch with progress tracking
            self.logger.debug(f"Generating semantic keywords for {total_updates} {table_name}")
            all_keywords = generate_batch_device_keywords(
                entities_to_process, 
                batch_size=batch_size,  # Auto-calculate optimal batch size if None
                collection_name=table_name,
                progress_callback=lambda current, message: progress.update(current, message)
            )
            
            # Delete existing records that need updates (they will be recreated with fresh data)
            if validation_data and entities_to_process:
                # Get IDs of entities being updated that already exist in the store
                updating_entity_ids = [e["id"] for e in entities_to_process if e["id"] in validation_data]
                
                if updating_entity_ids:
                    try:
                        updating_ids_str = [str(id_val) for id_val in updating_entity_ids]
                        if len(updating_ids_str) == 1:
                            delete_condition = f"id = {updating_ids_str[0]}"
                        else:
                            id_list = ", ".join(updating_ids_str)
                            delete_condition = f"id IN ({id_list})"
                        table.delete(delete_condition)
                        self.logger.debug(f"Deleted {len(updating_entity_ids)} existing {table_name} records for update")
                    except Exception as e:
                        self.logger.error(f"Error deleting existing {table_name} records for update: {e}")
            
            # Prepare texts for batch embedding processing
            texts_for_embedding = []
            entity_names_for_embedding = []
            entities_data = []
            
            for entity in entities_to_process:
                try:
                    entity_id = entity["id"]
                    
                    # Get semantic keywords for this entity
                    semantic_keywords = all_keywords.get(str(entity_id), [])
                    
                    # Generate enhanced embedding text
                    text = self._create_embedding_text(entity, table_name, semantic_keywords)
                    
                    # Store text, entity name, and entity data for batch processing
                    texts_for_embedding.append(text)
                    entity_names_for_embedding.append(entity.get("name", f"ID:{entity_id}"))
                    entities_data.append({
                        "entity": entity,
                        "text": text,
                        "semantic_keywords": semantic_keywords
                    })
                    
                except Exception as e:
                    self.logger.error(f"Error preparing {table_name} entity {entity.get('id', 'unknown')} for embedding: {e}")
                    continue
            
            if not texts_for_embedding:
                progress.complete("no texts to embed")
                return
                
            # Generate embeddings in batches - this is the major performance improvement
            self.logger.info(f"🚀 Generating embeddings for {len(texts_for_embedding)} {table_name} in batches...")
            
            # Create embedding progress callback that reports to the overall progress tracker
            def embedding_progress_callback(current_batch, total_batches, batch_size):
                # Calculate overall progress (embeddings happen after keyword generation)
                embedding_progress = int((current_batch / total_batches) * 100)
                progress.update(total_updates, f"Embedding generation - batch {current_batch}/{total_batches}")
                
                # Log embedding progress every 10% or every batch if few batches
                if current_batch % max(1, total_batches // 10) == 0 or current_batch == total_batches:
                    self.logger.info(f"📊 Embedding Generation progress: {embedding_progress}% complete (batch {current_batch}/{total_batches}, {current_batch * batch_size}/{len(texts_for_embedding)} texts)")
            
            batch_embeddings = self._generate_embeddings_batch(texts_for_embedding, entity_names_for_embedding, embedding_progress_callback)
            
            # Create records with batch embeddings
            records_to_add = []
            failed_count = 0
            
            for i, (embedding, entity_data) in enumerate(zip(batch_embeddings, entities_data)):
                try:
                    if not embedding:  # Empty embedding indicates failure
                        failed_count += 1
                        continue
                        
                    entity = entity_data["entity"]
                    entity_id = entity["id"]
                    
                    # Create record with static field hash
                    record = {
                        "id": entity_id,
                        "name": entity.get("name", ""),
                        "text": entity_data["text"],
                        "data": json.dumps(entity, cls=DateTimeJSONEncoder),
                        "hash": self._hash_static_fields(entity, table_name),
                        "embedding": embedding
                    }
                    
                    records_to_add.append(record)
                    
                except Exception as e:
                    self.logger.error(f"Error creating record for {table_name} entity: {e}")
                    failed_count += 1
                    continue
            
            # Bulk add all new records
            if records_to_add:
                try:
                    table.add(records_to_add)
                    success_count = len(records_to_add)
                    progress.complete(f"added {success_count} records")
                    
                    # Verify records were actually added and persisted
                    try:
                        # Force a sync/flush if available
                        if hasattr(table, 'flush'):
                            table.flush()
                            self.logger.debug("🔄 Flushed table to ensure data persistence")
                        
                        # Wait a moment for write to complete
                        import time
                        time.sleep(0.1)
                        
                        verification_rows = table.search().to_list()
                        current_count = len(verification_rows)
                        self.logger.debug(f"✅ Verification: {table_name} table now contains {current_count} total records")
                        
                        if current_count < success_count:
                            self.logger.warning(f"⚠️ Expected at least {success_count} new records but table shows {current_count} total")
                            
                        if current_count > 0:
                            # Show sample of what was written
                            sample_record = verification_rows[0]
                            self.logger.debug(f"Sample record keys: {list(sample_record.keys())}")
                            if 'id' in sample_record:
                                self.logger.debug(f"Sample record ID: {sample_record['id']}")
                                
                    except Exception as verify_error:
                        self.logger.warning(f"Could not verify record count after addition: {verify_error}")
                        
                except Exception as e:
                    self.logger.error(f"Failed to bulk add {table_name} records: {e}")
                    progress.error(f"failed to add {len(records_to_add)} records")
                    return
            else:
                progress.complete("no records to add")
            
            # Handle orphaned records (entities no longer exist in Indigo)
            if validation_data:
                current_ids = {e["id"] for e in valid_entities}
                existing_ids = set(validation_data.keys())
                orphaned_ids = existing_ids - current_ids
                
                if orphaned_ids:
                    try:
                        orphaned_list = list(orphaned_ids)
                        if len(orphaned_list) == 1:
                            delete_condition = f"id = {orphaned_list[0]}"
                        else:
                            id_list = ", ".join(map(str, orphaned_list))
                            delete_condition = f"id IN ({id_list})"
                        table.delete(delete_condition)
                        self.logger.info(f"🗑️ Removed {len(orphaned_ids)} orphaned {table_name} records from vector store")
                    except Exception as e:
                        self.logger.error(f"Error removing orphaned {table_name} records: {e}")
            
            # Final summary
            success_count = len(records_to_add)
            if failed_count > 0:
                self.logger.warning(f"⚠️ {table_name.title()} update completed with {failed_count} failures")
            
            if success_count > 0 or failed_count > 0:
                self.logger.info(f"✅ {table_name.title()} embeddings updated: {success_count} successful, {failed_count} failed")
            
        except Exception as e:
            self.logger.error(f"Failed to update {table_name} embeddings: {e}")
            raise
    
    def search(
        self,
        query: str,
        entity_types: Optional[List[str]] = None,
        top_k: int = 10,
        similarity_threshold: float = 0.7
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Search for entities using semantic similarity.
        
        Args:
            query: Natural language search query
            entity_types: Optional list of entity types to filter ('devices', 'variables', 'actions')
            top_k: Maximum number of results to return
            similarity_threshold: Minimum similarity score threshold
            
        Returns:
            Tuple of (search results with similarity scores, metadata dict)
            Metadata includes: total_found, total_returned, truncated
        """
        if entity_types is None:
            entity_types = ["devices", "variables", "actions"]
        
        # Generate query embedding
        try:
            query_embedding = self._generate_embedding(query)
        except Exception as e:
            self.logger.error(f"Failed to generate query embedding: {e}")
            return [], {"total_found": 0, "total_returned": 0, "truncated": False}
        
        all_results = []
        
        for entity_type in entity_types:
            if entity_type not in ["devices", "variables", "actions"]:
                continue
                
            try:
                table = self.db.open_table(entity_type)
                
                # Perform vector search with large limit to get all potential matches
                # We'll filter by similarity threshold after getting results
                search_results = (
                    table.search(query_embedding)
                    .metric("cosine")
                    .limit(1000)  # Large limit to capture all potential matches
                    .to_list()
                )
                
                # Process results
                for result in search_results:
                    # Calculate similarity score
                    cosine_distance = result.get("_distance", 0)
                    similarity_score = 1 - (cosine_distance / 2)
                    
                    if similarity_score >= similarity_threshold:
                        # Parse entity data
                        entity_data = json.loads(result["data"])
                        entity_data["_similarity_score"] = similarity_score
                        entity_data["_entity_type"] = entity_type[:-1]  # Remove 's' from plural
                        all_results.append(entity_data)
                
            except Exception as e:
                self.logger.error(f"Search failed for {entity_type}: {e}")
        
        # Sort by similarity score (highest first)
        all_results.sort(key=lambda x: x.get("_similarity_score", 0), reverse=True)
        
        # Calculate metadata
        total_found = len(all_results)
        limited_results = all_results[:top_k]
        total_returned = len(limited_results)
        truncated = total_found > top_k
        
        metadata = {
            "total_found": total_found,
            "total_returned": total_returned,
            "truncated": truncated
        }
        
        # Return limited results with metadata
        return limited_results, metadata
    
    def add_entity(self, entity_type: str, entity_data: Dict[str, Any]) -> None:
        """
        Add a single entity to the vector store.
        
        Args:
            entity_type: Type of entity ('device', 'variable', 'action')
            entity_data: Entity data dictionary
        """
        # Convert singular to plural for table name
        table_name = entity_type + "s" if not entity_type.endswith("s") else entity_type
        
        if table_name not in ["devices", "variables", "actions"]:
            self.logger.error(f"Invalid entity type: {entity_type}")
            return
        
        try:
            table = self.db.open_table(table_name)
            
            # Generate embedding using legacy method for single additions
            text = self._create_embedding_text_legacy(entity_data, table_name)
            embedding = self._generate_embedding(text)
            
            # Create record
            record = {
                "id": entity_data.get("id"),
                "name": entity_data.get("name", ""),
                "text": text,
                "data": json.dumps(entity_data, cls=DateTimeJSONEncoder),
                "hash": self._hash_entity(entity_data),
                "embedding": embedding
            }
            
            # Add to table
            table.add([record])
            self.logger.debug(f"Added {entity_type} {entity_data.get('id')} to vector store")
            
        except Exception as e:
            self.logger.error(f"Failed to add {entity_type} to vector store: {e}")
    
    def remove_entity(self, entity_type: str, entity_id: int) -> None:
        """
        Remove an entity from the vector store.
        
        Args:
            entity_type: Type of entity ('device', 'variable', 'action')
            entity_id: Entity ID to remove
        """
        # Convert singular to plural for table name
        table_name = entity_type + "s" if not entity_type.endswith("s") else entity_type
        
        if table_name not in ["devices", "variables", "actions"]:
            self.logger.error(f"Invalid entity type: {entity_type}")
            return
        
        try:
            table = self.db.open_table(table_name)
            
            # Delete by ID
            table.delete(f"id = {entity_id}")
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
        
        for table_name in ["devices", "variables", "actions"]:
            try:
                table = self.db.open_table(table_name)
                count = len(table.search().to_list())
                stats["tables"][table_name] = count
            except Exception:
                stats["tables"][table_name] = 0
        
        return stats
    
    def close(self) -> None:
        """Close the database connection."""
        if self.db:
            self.db = None
            self.logger.debug("Database connection closed")