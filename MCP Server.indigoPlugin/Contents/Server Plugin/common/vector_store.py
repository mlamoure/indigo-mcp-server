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
from openai import OpenAI

from adapters.vector_store_interface import VectorStoreInterface


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
        self.logger = logger or logging.getLogger(__name__)
        self.dimension = 1536  # text-embedding-3-small dimension
        self.db = None
        self.openai_client = None
        
        # Initialize database
        self._init_database()
        
        # Initialize OpenAI client
        self._init_openai_client()
    
    def _init_openai_client(self) -> None:
        """Initialize OpenAI client for embeddings."""
        try:
            self.openai_client = OpenAI()
            self.logger.debug("OpenAI client initialized")
        except Exception as e:
            self.logger.error(f"Failed to initialize OpenAI client: {e}")
            raise
    
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
    
    def _create_embedding_text(self, entity: Dict[str, Any], entity_type: str) -> str:
        """
        Create text representation for embedding generation.
        
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
        """Generate embedding for text using OpenAI."""
        try:
            response = self.openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=text
            )
            return response.data[0].embedding
            
        except Exception as e:
            self.logger.error(f"Failed to generate embedding: {e}")
            raise
    
    def _hash_entity(self, entity: Dict[str, Any]) -> str:
        """Generate hash for entity to detect changes."""
        # Create deterministic string representation using custom encoder
        entity_str = json.dumps(entity, sort_keys=True, cls=DateTimeJSONEncoder)
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
        entities: List[Dict[str, Any]]
    ) -> None:
        """Update embeddings for a specific entity type."""
        try:
            table = self.db.open_table(table_name)
            
            # Get existing entities
            existing = {}
            try:
                for row in table.search().to_list():
                    existing[row["id"]] = row["hash"]
            except Exception:
                # Table might be empty
                pass
            
            # Process entities
            records_to_add = []
            updated_count = 0
            
            for entity in entities:
                entity_id = entity.get("id")
                if entity_id is None:
                    continue
                
                # Generate hash
                entity_hash = self._hash_entity(entity)
                
                # Check if update needed
                if entity_id in existing and existing[entity_id] == entity_hash:
                    continue  # No change
                
                # Generate embedding text
                text = self._create_embedding_text(entity, table_name)
                
                # Generate embedding
                try:
                    embedding = self._generate_embedding(text)
                except Exception as e:
                    self.logger.error(f"Failed to generate embedding for {table_name} {entity_id}: {e}")
                    continue
                
                # Create record
                record = {
                    "id": entity_id,
                    "name": entity.get("name", ""),
                    "text": text,
                    "data": json.dumps(entity, cls=DateTimeJSONEncoder),
                    "hash": entity_hash,
                    "embedding": embedding
                }
                
                records_to_add.append(record)
                updated_count += 1
            
            # Delete outdated records
            if existing:
                current_ids = {e.get("id") for e in entities if e.get("id") is not None}
                for old_id in existing:
                    if old_id not in current_ids:
                        table.delete(f"id = {old_id}")
            
            # Add new/updated records
            if records_to_add:
                table.add(records_to_add)
                
            self.logger.info(f"Updated {updated_count} embeddings in {table_name}")
            
        except Exception as e:
            self.logger.error(f"Failed to update {table_name} embeddings: {e}")
    
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
            
            # Generate embedding
            text = self._create_embedding_text(entity_data, table_name)
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