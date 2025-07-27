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

from adapters.vector_store_interface import VectorStoreInterface
from ..openai_client.main import emb_text
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
    
    
    def _init_database(self) -> None:
        """Initialize LanceDB database and create tables if needed."""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            
            # Connect to LanceDB
            self.db = lancedb.connect(self.db_path)
            self.logger.info(f"Vector database connected at: {self.db_path}")
            
            # Initialize tables for each entity type
            for table_name in ["devices", "variables", "actions"]:
                if table_name not in self.db.table_names():
                    self._create_table(table_name)
                    
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
        batch_size: int = 20
    ) -> None:
        """Update embeddings for a specific entity type with enhanced processing."""
        if not entities:
            self.logger.debug(f"No {table_name} entities to process")
            return
            
        try:
            table = self.db.open_table(table_name)
            
            # Get existing entities with improved error handling
            existing = {}
            try:
                existing_rows = table.search().to_list()
                existing = {row["id"]: row["hash"] for row in existing_rows}
                self.logger.debug(f"Found {len(existing)} existing {table_name} records")
            except Exception as e:
                self.logger.debug(f"Table {table_name} appears empty or new: {e}")
            
            # Analyze what needs updating using static field hashing
            valid_entities = [e for e in entities if e.get("id") is not None]
            current_ids = {e["id"] for e in valid_entities}
            existing_ids = set(existing.keys())
            
            missing_entities = [e for e in valid_entities if e["id"] not in existing_ids]
            existing_entities = [e for e in valid_entities if e["id"] in existing_ids]
            
            # Check which existing entities need updates
            outdated_entities = []
            for entity in existing_entities:
                entity_id = entity["id"]
                new_hash = self._hash_static_fields(entity, table_name)
                if existing.get(entity_id) != new_hash:
                    outdated_entities.append(entity)
            
            entities_to_process = missing_entities + outdated_entities
            total_updates = len(entities_to_process)
            
            if total_updates == 0:
                self.logger.debug(f"All {table_name} embeddings are up to date")
                return
            
            # Show update summary
            if total_updates > 10:
                self.logger.info(f"📊 {table_name.title()} embedding updates required:")
                self.logger.info(f"   New: {len(missing_entities)}")
                self.logger.info(f"   Updates: {len(outdated_entities)}")
                self.logger.info(f"   Total: {total_updates}")
            
            # Initialize progress tracking
            progress = create_progress_tracker(
                f"{table_name.title()} Embeddings", 
                total_updates,
                threshold=10
            )
            
            # Generate semantic keywords in batch
            self.logger.debug(f"Generating semantic keywords for {total_updates} {table_name}")
            all_keywords = generate_batch_device_keywords(
                entities_to_process, 
                batch_size=min(15, batch_size),
                collection_name=table_name
            )
            
            # Delete outdated records first
            if outdated_entities:
                outdated_ids = [str(e["id"]) for e in outdated_entities]
                try:
                    if len(outdated_ids) == 1:
                        delete_condition = f"id = {outdated_ids[0]}"
                    else:
                        id_list = ", ".join(outdated_ids)
                        delete_condition = f"id IN ({id_list})"
                    table.delete(delete_condition)
                    self.logger.debug(f"Deleted {len(outdated_ids)} outdated {table_name} records")
                except Exception as e:
                    self.logger.error(f"Error deleting outdated {table_name} records: {e}")
            
            # Process embeddings in batches
            records_to_add = []
            failed_count = 0
            
            for i, entity in enumerate(entities_to_process):
                try:
                    entity_id = entity["id"]
                    
                    # Get semantic keywords for this entity
                    semantic_keywords = all_keywords.get(str(entity_id), [])
                    
                    # Generate enhanced embedding text
                    text = self._create_embedding_text(entity, table_name, semantic_keywords)
                    
                    # Generate embedding
                    try:
                        embedding = self._generate_embedding(text)
                    except Exception as e:
                        self.logger.error(f"Failed to generate embedding for {table_name} {entity_id}: {e}")
                        failed_count += 1
                        continue
                    
                    # Create record with static field hash
                    record = {
                        "id": entity_id,
                        "name": entity.get("name", ""),
                        "text": text,
                        "data": json.dumps(entity, cls=DateTimeJSONEncoder),
                        "hash": self._hash_static_fields(entity, table_name),
                        "embedding": embedding
                    }
                    
                    records_to_add.append(record)
                    
                    # Update progress
                    progress.update(i + 1, f"processed {entity.get('name', f'ID {entity_id}')}")
                    
                except Exception as e:
                    self.logger.error(f"Error processing {table_name} entity {entity.get('id', 'unknown')}: {e}")
                    failed_count += 1
                    continue
            
            # Bulk add all new records
            if records_to_add:
                try:
                    table.add(records_to_add)
                    success_count = len(records_to_add)
                    progress.complete(f"added {success_count} records")
                except Exception as e:
                    self.logger.error(f"Failed to bulk add {table_name} records: {e}")
                    progress.error(f"failed to add {len(records_to_add)} records")
                    return
            else:
                progress.complete("no records to add")
            
            # Handle removed entities
            removed_ids = existing_ids - current_ids
            if removed_ids:
                try:
                    removed_list = list(removed_ids)
                    if len(removed_list) == 1:
                        delete_condition = f"id = {removed_list[0]}"
                    else:
                        id_list = ", ".join(map(str, removed_list))
                        delete_condition = f"id IN ({id_list})"
                    table.delete(delete_condition)
                    self.logger.info(f"Removed {len(removed_ids)} deleted {table_name} from vector store")
                except Exception as e:
                    self.logger.error(f"Error removing deleted {table_name}: {e}")
            
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
    ) -> List[Dict[str, Any]]:
        """
        Search for entities using semantic similarity.
        
        Args:
            query: Natural language search query
            entity_types: Optional list of entity types to filter ('devices', 'variables', 'actions')
            top_k: Maximum number of results to return
            similarity_threshold: Minimum similarity score threshold
            
        Returns:
            List of search results with similarity scores
        """
        if entity_types is None:
            entity_types = ["devices", "variables", "actions"]
        
        # Generate query embedding
        try:
            query_embedding = self._generate_embedding(query)
        except Exception as e:
            self.logger.error(f"Failed to generate query embedding: {e}")
            return []
        
        all_results = []
        
        for entity_type in entity_types:
            if entity_type not in ["devices", "variables", "actions"]:
                continue
                
            try:
                table = self.db.open_table(entity_type)
                
                # Perform vector search
                search_results = (
                    table.search(query_embedding)
                    .metric("cosine")
                    .limit(top_k)
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
        
        # Sort by similarity score
        all_results.sort(key=lambda x: x.get("_similarity_score", 0), reverse=True)
        
        # Limit total results
        return all_results[:top_k]
    
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