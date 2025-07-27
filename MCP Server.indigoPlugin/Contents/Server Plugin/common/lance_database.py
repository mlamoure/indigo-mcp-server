"""
Unified LanceDB database manager for Hello Indigo plugin.
Replaces SQLite (DatabaseManager) + Milvus (FeedbackVectorDB + IndigoVectorDB) with single LanceDB system.
Handles memory, API keys, chat history, and home automation item embeddings.
"""

import hashlib
import json
import logging
import os
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import List, Optional, Dict, Any

import lancedb
import pyarrow as pa

# Import moved to functions to avoid circular imports

logger = logging.getLogger("Plugin")


class ProgressTracker:
    """Handles progress tracking and reporting for vector operations."""

    def __init__(self, stage: str, total: int, threshold: int = 10):
        """
        Initialize progress tracker.

        Args:
            stage: Name of the processing stage
            total: Total number of items to process
            threshold: Minimum items before showing progress (default 10)
        """
        self.stage = stage
        self.total = total
        self.threshold = threshold
        self.current = 0
        self.start_time = time.time()
        self.last_reported_percent = 0
        self.should_report_progress = total >= threshold

        if self.should_report_progress:
            logger.info(f"🚀 Starting {stage}: processing {total} items...")

    def update(self, current: int, operation: str = ""):
        """
        Update progress and report if needed.

        Args:
            current: Current item count
            operation: Optional description of current operation
        """
        self.current = current

        if not self.should_report_progress:
            return

        # Calculate progress percentage
        percent = int((current / self.total) * 100)

        # Report every 10% increment
        if percent >= self.last_reported_percent + 10 and percent <= 100:
            elapsed = time.time() - self.start_time
            rate = current / elapsed if elapsed > 0 else 0
            eta = (self.total - current) / rate if rate > 0 else 0

            progress_msg = f"📊 {self.stage} progress: {percent}% complete ({current}/{self.total})"
            if operation:
                progress_msg += f" - {operation}"
            if eta > 0 and eta < 300:  # Show ETA if less than 5 minutes
                progress_msg += f" (ETA: {eta:.0f}s)"
            elif rate > 0:
                progress_msg += f" ({rate:.1f} items/sec)"

            logger.info(progress_msg)
            self.last_reported_percent = percent

    def complete(self, operation: str = ""):
        """
        Mark stage as complete and show final summary.

        Args:
            operation: Optional description of completion
        """
        elapsed = time.time() - self.start_time

        if self.should_report_progress:
            rate = self.total / elapsed if elapsed > 0 else 0
            final_msg = (
                f"✅ {self.stage} completed: {self.total} items in {elapsed:.2f}s"
            )
            if rate > 0:
                final_msg += f" ({rate:.1f} items/sec)"
            if operation:
                final_msg += f" - {operation}"
            logger.info(final_msg)
        elif self.total > 0:
            # Single info notification for small datasets
            logger.info(
                f"✅ {self.stage}: processed {self.total} items ({elapsed:.2f}s)"
            )

    def error(self, message: str):
        """Report an error during processing."""
        elapsed = time.time() - self.start_time
        logger.error(f"❌ {self.stage} failed after {elapsed:.2f}s: {message}")


def create_progress_tracker(
    stage: str, total: int, threshold: int = 10
) -> ProgressTracker:
    """
    Create a progress tracker for vector operations.

    Args:
        stage: Name of the processing stage
        total: Total number of items to process
        threshold: Minimum items before showing progress updates

    Returns:
        ProgressTracker instance
    """
    return ProgressTracker(stage, total, threshold)


# ==================== FIELD CLASSIFICATION CONSTANTS ====================
# Define which fields are static (for embeddings) vs dynamic (for live queries)

# Static fields: Used for embeddings and change detection - rarely change
STATIC_FIELDS = {
    "devices": {"id", "name", "description", "model", "class", "type"},
    "variables": {"id", "name", "description", "folderId"},
    "actions": {"id", "name", "description", "folderId"},
}

# Fields for embedding text generation (subset of static fields)
EMBEDDING_FIELDS = {
    "devices": {"name", "description", "model", "class", "type"},
    "variables": {"name", "description"},
    "actions": {"name", "description"},
}


class LanceDBManager:
    """Unified database manager using LanceDB for all Hello Indigo plugin operations."""

    # Singleton instance and lock
    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls, db_path: str):
        """
        Implement singleton pattern to ensure only one instance exists.

        Args:
            db_path: Path to the LanceDB database directory

        Returns:
            The singleton instance of LanceDBManager
        """
        if cls._instance is None:
            with cls._instance_lock:
                # Double-check locking pattern
                if cls._instance is None:
                    cls._instance = super(LanceDBManager, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_path: str):
        """
        Initialize the unified LanceDB manager.

        Args:
            db_path: Path to the LanceDB database directory
        """
        # Only initialize once
        if self._initialized:
            return

        self.db_path = db_path
        self.db = None
        self.dimension = 1536  # text-embedding-3-small dimension
        self._initialization_failed = False
        self._lock = threading.Lock()

        # Mark as initialized before calling _init_database to prevent recursion
        self._initialized = True

        # Initialize database and tables
        self._init_database()

    @classmethod
    def get_instance(cls, db_path: str) -> "LanceDBManager":
        """
        Get the singleton instance of LanceDBManager.

        Args:
            db_path: Path to the LanceDB database directory

        Returns:
            The singleton instance of LanceDBManager
        """
        return cls(db_path)

    def _init_database(self):
        """Initialize LanceDB database and create tables if needed."""
        try:
            # Ensure directory exists
            db_dir = os.path.dirname(self.db_path)
            if db_dir:  # Only create if there's actually a directory path
                os.makedirs(db_dir, exist_ok=True)

            # Connect to LanceDB
            self.db = lancedb.connect(self.db_path)
            logger.info(f"✅ Hello Indigo Database connected at: {self.db_path}")

            # Initialize all tables
            self._init_memory_table()
            self._init_api_keys_table()
            self._init_chat_history_table()
            self._init_home_automation_tables()

        except Exception as e:
            self._initialization_failed = True
            logger.error(f"❌ Database initialization failed: {str(e)}")
            logger.error("⚠️  Plugin will continue with limited functionality")
            raise

    def _reconnect(self) -> bool:
        """Attempt to reconnect to the database."""
        with self._lock:
            try:
                # Close existing connection if any
                if self.db is not None:
                    self.db = None

                # Reset initialization state
                self._initialization_failed = False

                # Reinitialize database
                self._init_database()

                logger.info("✅ Database reconnection successful")
                return True

            except Exception as e:
                self._initialization_failed = True
                self.db = None
                logger.error(f"❌ Database reconnection failed: {str(e)}")
                return False

    def _init_memory_table(self):
        """Initialize memory table with vector embeddings."""
        table_name = "memory"
        if table_name not in self.db.table_names():
            # Define schema for memory with embeddings
            schema = pa.schema(
                [
                    pa.field("memory_id", pa.string()),
                    pa.field("memory_timestamp", pa.string()),
                    pa.field("user_prompt", pa.string()),
                    pa.field("relevant_devices", pa.string()),  # JSON string
                    pa.field("system_response", pa.string()),
                    pa.field("rating", pa.int64()),
                    pa.field("comments", pa.string()),
                    pa.field("metadata", pa.string()),  # JSON string
                    pa.field("created_at", pa.string()),
                    pa.field("embedding", pa.list_(pa.float32(), self.dimension)),
                ]
            )

            # Create empty table with schema
            empty_data = pa.Table.from_arrays(
                [
                    pa.array([], type=pa.string()),  # memory_id
                    pa.array([], type=pa.string()),  # memory_timestamp
                    pa.array([], type=pa.string()),  # user_prompt
                    pa.array([], type=pa.string()),  # relevant_devices
                    pa.array([], type=pa.string()),  # system_response
                    pa.array([], type=pa.int64()),  # rating
                    pa.array([], type=pa.string()),  # comments
                    pa.array([], type=pa.string()),  # metadata
                    pa.array([], type=pa.string()),  # created_at
                    pa.array(
                        [], type=pa.list_(pa.float32(), self.dimension)
                    ),  # embedding
                ],
                schema=schema,
            )

            self.db.create_table(table_name, empty_data)
            pass  # Table created successfully

    def _init_api_keys_table(self):
        """Initialize API keys table."""
        table_name = "api_keys"
        if table_name not in self.db.table_names():
            schema = pa.schema(
                [
                    pa.field("api_key_id", pa.string()),
                    pa.field("api_key_hash", pa.string()),
                    pa.field("created_at", pa.string()),
                    pa.field("last_seen", pa.string()),
                    pa.field("description", pa.string()),
                ]
            )

            empty_data = pa.Table.from_arrays(
                [
                    pa.array([], type=pa.string()),  # api_key_id
                    pa.array([], type=pa.string()),  # api_key_hash
                    pa.array([], type=pa.string()),  # created_at
                    pa.array([], type=pa.string()),  # last_seen
                    pa.array([], type=pa.string()),  # description
                ],
                schema=schema,
            )

            self.db.create_table(table_name, empty_data)
            pass  # Table created successfully

    def _init_chat_history_table(self):
        """Initialize chat history table."""
        table_name = "chat_history"
        if table_name not in self.db.table_names():
            schema = pa.schema(
                [
                    pa.field("chat_id", pa.string()),
                    pa.field("session_id", pa.string()),
                    pa.field("messages_json", pa.string()),
                    pa.field("created_at", pa.string()),
                    pa.field("updated_at", pa.string()),
                    pa.field("title", pa.string()),
                    pa.field("chat_subject", pa.string()),
                ]
            )

            empty_data = pa.Table.from_arrays(
                [
                    pa.array([], type=pa.string()),  # chat_id
                    pa.array([], type=pa.string()),  # session_id
                    pa.array([], type=pa.string()),  # messages_json
                    pa.array([], type=pa.string()),  # created_at
                    pa.array([], type=pa.string()),  # updated_at
                    pa.array([], type=pa.string()),  # title
                    pa.array([], type=pa.string()),  # chat_subject
                ],
                schema=schema,
            )

            self.db.create_table(table_name, empty_data)
            pass  # Table created successfully

    def _init_home_automation_tables(self):
        """Initialize home automation tables (devices, variables, actions) with embeddings."""
        for table_name in ["devices", "variables", "actions"]:
            if table_name not in self.db.table_names():
                schema = pa.schema(
                    [
                        pa.field("id", pa.int64()),
                        pa.field("name", pa.string()),
                        pa.field("text", pa.string()),  # JSON representation for search
                        pa.field("hash", pa.string()),
                        pa.field("embedding", pa.list_(pa.float32(), self.dimension)),
                    ]
                )

                empty_data = pa.Table.from_arrays(
                    [
                        pa.array([], type=pa.int64()),  # id
                        pa.array([], type=pa.string()),  # name
                        pa.array([], type=pa.string()),  # text
                        pa.array([], type=pa.string()),  # hash
                        pa.array(
                            [], type=pa.list_(pa.float32(), self.dimension)
                        ),  # embedding
                    ],
                    schema=schema,
                )

                self.db.create_table(table_name, empty_data)
                pass  # Table created successfully

    def is_available(self) -> bool:
        """Check if database is available for use with connection validation and auto-reconnection."""
        # First check basic state
        if self._initialization_failed:
            return False

        # If no connection, try to reconnect
        if self.db is None:
            logger.info("🔄 Database connection is None, attempting reconnection...")
            return self._reconnect()

        # Validate existing connection by attempting a simple operation
        try:
            # Try to list tables as a lightweight connection test
            self.db.table_names()
            return True
        except Exception as e:
            logger.warning(f"🔄 Database connection validation failed: {str(e)}")
            logger.info("🔄 Attempting automatic reconnection...")
            return self._reconnect()

    @contextmanager
    def get_table(self, table_name: str):
        """Get a table with proper error handling and auto-reconnection."""
        if not self.is_available():
            raise RuntimeError("Database not available")

        try:
            table = self.db.open_table(table_name)
            yield table
        except Exception as e:
            logger.error(f"Error accessing table {table_name}: {str(e)}")
            # Try to reconnect on table access failure
            if "Connection" in str(e) or "connection" in str(e).lower():
                logger.info(
                    f"🔄 Table access failed, attempting reconnection for {table_name}"
                )
                if self._reconnect():
                    table = self.db.open_table(table_name)
                    yield table
                    return
            raise

    # ==================== MEMORY OPERATIONS ====================

    def create_memory(
        self,
        user_prompt: str,
        relevant_devices: List[Dict],
        system_response: str,
        rating: int,
        comments: str = "",
        metadata: Dict = None,
    ) -> str:
        """
        Create a new memory record with vector embedding.

        Returns:
            memory_id: The ID of the created memory record
        """
        if not self.is_available():
            raise RuntimeError("Database not available")

        memory_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat() + "Z"

        # Create embedding text for vector search
        embedding_text = self._create_memory_embedding_text(
            user_prompt, relevant_devices
        )
        from hello_indigo_api.agents.common.openai_client import emb_text

        embedding = emb_text(embedding_text)

        # Prepare record
        record = {
            "memory_id": memory_id,
            "memory_timestamp": timestamp,
            "user_prompt": user_prompt,
            "relevant_devices": json.dumps(relevant_devices),
            "system_response": system_response,
            "rating": rating,
            "comments": comments,
            "metadata": json.dumps(metadata or {}),
            "created_at": timestamp,
            "embedding": embedding,
        }

        with self.get_table("memory") as table:
            table.add([record])

        pass  # Memory record created
        return memory_id

    def get_memory(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """Get a memory record by ID."""
        if not self.is_available():
            return None

        try:
            with self.get_table("memory") as table:
                results = table.search().where(f"memory_id = '{memory_id}'").to_list()

                if results:
                    result = results[0]
                    return {
                        "memory_id": result["memory_id"],
                        "memory_timestamp": result["memory_timestamp"],
                        "user_prompt": result["user_prompt"],
                        "relevant_devices": json.loads(result["relevant_devices"]),
                        "system_response": result["system_response"],
                        "rating": result["rating"],
                        "comments": result["comments"],
                        "metadata": (
                            json.loads(result["metadata"]) if result["metadata"] else {}
                        ),
                    }
                return None
        except Exception as e:
            logger.error(f"Error getting memory {memory_id}: {str(e)}")
            return None

    def list_memory(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """List memory records with pagination."""
        if not self.is_available():
            return []

        try:
            with self.get_table("memory") as table:
                # LanceDB doesn't have direct LIMIT/OFFSET, so we'll get all and slice
                results = (
                    table.search()
                    .select(["memory_id", "memory_timestamp", "user_prompt", "rating"])
                    .to_list()
                )

                # Sort by timestamp descending and apply pagination
                sorted_results = sorted(
                    results, key=lambda x: x["memory_timestamp"], reverse=True
                )
                paginated_results = sorted_results[offset : offset + limit]

                return [
                    {
                        "memory_id": row["memory_id"],
                        "memory_timestamp": row["memory_timestamp"],
                        "user_prompt": row["user_prompt"],
                        "rating": row["rating"],
                    }
                    for row in paginated_results
                ]
        except Exception as e:
            logger.error(f"Error listing memory: {str(e)}")
            return []

    def update_memory(
        self,
        memory_id: str,
        rating: int = None,
        comments: str = None,
        relevant_devices: List[str] = None,
    ) -> bool:
        """Update a memory record."""
        if not self.is_available():
            return False

        if rating is None and comments is None and relevant_devices is None:
            return False

        try:
            with self.get_table("memory") as table:
                # Get existing record
                existing = table.search().where(f"memory_id = '{memory_id}'").to_list()
                if not existing:
                    return False

                record = existing[0]

                # Update fields
                if rating is not None:
                    record["rating"] = rating
                if comments is not None:
                    record["comments"] = comments
                if relevant_devices is not None:
                    record["relevant_devices"] = relevant_devices
                    # Regenerate embedding since relevant_devices affects it
                    embedding_text = f"{record['user_prompt']} {record['system_response']} {' '.join(relevant_devices)}"
                    record["embedding"] = self.openai_client.get_embedding(
                        embedding_text
                    )

                # Delete old record and add updated one
                table.delete(f"memory_id = '{memory_id}'")
                table.add([record])

                return True
        except Exception as e:
            logger.error(f"Error updating memory {memory_id}: {str(e)}")
            return False

    def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory record."""
        if not self.is_available():
            return False

        try:
            with self.get_table("memory") as table:
                table.delete(f"memory_id = '{memory_id}'")
                return True
        except Exception as e:
            logger.error(f"Error deleting memory {memory_id}: {str(e)}")
            return False

    def search_similar_memory(
        self,
        user_prompt: str,
        relevant_devices: List[Dict] = None,
        top_k: int = 3,
        similarity_threshold: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar memory records using vector similarity.

        Args:
            user_prompt: The user's current prompt
            relevant_devices: List of relevant device dictionaries (optional)
            top_k: Number of similar records to return
            similarity_threshold: Minimum similarity score (0-1)

        Returns:
            List of similar memory records with similarity scores
        """
        if not self.is_available():
            return []

        try:
            # Create embedding text for search
            embedding_text = self._create_memory_embedding_text(
                user_prompt, relevant_devices or []
            )

            # Generate query embedding
            from hello_indigo_api.agents.common.openai_client import emb_text

            query_embedding = emb_text(embedding_text)

            with self.get_table("memory") as table:
                # Perform vector search with cosine metric
                results = (
                    table.search(query_embedding)
                    .metric("cosine")
                    .limit(top_k)
                    .to_list()
                )

                # Format results and filter by similarity threshold
                similar_memory = []
                for result in results:
                    # For cosine metric, _distance is already cosine distance (0 to 2)
                    # Convert to similarity: cosine_similarity = 1 - (cosine_distance / 2)
                    cosine_distance = result.get("_distance", 0)
                    similarity_score = 1 - (cosine_distance / 2)

                    if similarity_score >= similarity_threshold:
                        similar_memory.append(
                            {
                                "memory_id": result["memory_id"],
                                "user_prompt": result["user_prompt"],
                                "relevant_devices": json.loads(
                                    result["relevant_devices"]
                                ),
                                "similarity_score": similarity_score,
                            }
                        )

                pass  # Similar memory records found
                return similar_memory

        except Exception as e:
            logger.error(f"Failed to search similar memory: {e}")
            return []

    def _create_memory_embedding_text(
        self, user_prompt: str, relevant_devices: List[Dict]
    ) -> str:
        """Create combined text for embedding from user prompt and relevant devices."""
        device_info = []
        for device in relevant_devices:
            if isinstance(device, dict) and "dev_id" in device:
                device_info.append(f"device_{device['dev_id']}")

        combined_text = user_prompt
        if device_info:
            combined_text += f" [devices: {', '.join(device_info)}]"

        return combined_text

    # ==================== API KEY OPERATIONS ====================

    def create_api_key(self, description: str = "") -> tuple[str, str]:
        """
        Create a new API key.

        Returns:
            (api_key_id, raw_api_key): The ID and the raw API key (only time it's returned)
        """
        if not self.is_available():
            raise RuntimeError("Database not available")

        api_key_id = str(uuid.uuid4())
        raw_api_key = f"hik_{uuid.uuid4().hex}"
        api_key_hash = hashlib.sha256(raw_api_key.encode()).hexdigest()
        timestamp = datetime.utcnow().isoformat() + "Z"

        record = {
            "api_key_id": api_key_id,
            "api_key_hash": api_key_hash,
            "created_at": timestamp,
            "last_seen": None,
            "description": description,
        }

        with self.get_table("api_keys") as table:
            table.add([record])

        pass  # API key created
        return api_key_id, raw_api_key

    def validate_api_key(self, raw_api_key: str) -> Optional[str]:
        """
        Validate an API key and return the key ID if valid.
        Also updates the last_seen timestamp.
        """
        if not self.is_available():
            return None

        api_key_hash = hashlib.sha256(raw_api_key.encode()).hexdigest()
        timestamp = datetime.utcnow().isoformat() + "Z"

        try:
            with self.get_table("api_keys") as table:
                results = (
                    table.search().where(f"api_key_hash = '{api_key_hash}'").to_list()
                )

                if results:
                    record = results[0]
                    api_key_id = record["api_key_id"]

                    # Update last_seen
                    record["last_seen"] = timestamp
                    table.delete(f"api_key_hash = '{api_key_hash}'")
                    table.add([record])

                    return api_key_id
                return None
        except Exception as e:
            logger.error(f"Error validating API key: {str(e)}")
            return None

    def list_api_keys(self) -> List[Dict[str, Any]]:
        """List all API keys (without the actual keys)."""
        if not self.is_available():
            return []

        try:
            with self.get_table("api_keys") as table:
                results = (
                    table.search()
                    .select(["api_key_id", "created_at", "last_seen", "description"])
                    .to_list()
                )

                return [
                    {
                        "api_key_id": row["api_key_id"],
                        "api_key_ui": f"hik_{'x' * 8}...{'x' * 8}",  # Masked display
                        "created_at": row["created_at"],
                        "last_seen": row["last_seen"],
                        "description": row["description"],
                    }
                    for row in sorted(
                        results, key=lambda x: x["created_at"], reverse=True
                    )
                ]
        except Exception as e:
            logger.error(f"Error listing API keys: {str(e)}")
            return []

    def delete_api_key(self, api_key_id: str) -> bool:
        """Delete an API key."""
        if not self.is_available():
            return False

        try:
            with self.get_table("api_keys") as table:
                table.delete(f"api_key_id = '{api_key_id}'")
                return True
        except Exception as e:
            logger.error(f"Error deleting API key {api_key_id}: {str(e)}")
            return False

    # ==================== CHAT HISTORY OPERATIONS ====================

    def create_chat_history(
        self,
        session_id: str,
        messages: List[Dict],
        title: str = None,
        chat_subject: str = None,
    ) -> str:
        """Create a new chat history record."""
        if not self.is_available():
            raise RuntimeError("Database not available")

        chat_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat() + "Z"

        record = {
            "chat_id": chat_id,
            "session_id": session_id,
            "messages_json": json.dumps(messages),
            "created_at": timestamp,
            "updated_at": timestamp,
            "title": title,
            "chat_subject": chat_subject,
        }

        with self.get_table("chat_history") as table:
            table.add([record])

        # Chat history created successfully
        return chat_id

    def get_chat_history(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """Get a chat history record by ID."""
        if not self.is_available():
            return None

        try:
            with self.get_table("chat_history") as table:
                results = table.search().where(f"chat_id = '{chat_id}'").to_list()

                if results:
                    result = results[0]
                    return {
                        "chat_id": result["chat_id"],
                        "session_id": result["session_id"],
                        "messages": json.loads(result["messages_json"]),
                        "created_at": result["created_at"],
                        "updated_at": result["updated_at"],
                        "title": result["title"],
                        "chat_subject": result["chat_subject"],
                    }
                return None
        except Exception as e:
            logger.error(f"Error getting chat history {chat_id}: {str(e)}")
            return None

    def get_chat_history_by_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get chat history by session ID."""
        if not self.is_available():
            return None

        try:
            with self.get_table("chat_history") as table:
                results = table.search().where(f"session_id = '{session_id}'").to_list()

                if results:
                    # Sort by updated_at and get the most recent
                    sorted_results = sorted(
                        results, key=lambda x: x["updated_at"], reverse=True
                    )
                    result = sorted_results[0]

                    return {
                        "chat_id": result["chat_id"],
                        "session_id": result["session_id"],
                        "messages": json.loads(result["messages_json"]),
                        "created_at": result["created_at"],
                        "updated_at": result["updated_at"],
                        "title": result["title"],
                        "chat_subject": result["chat_subject"],
                    }
                return None
        except Exception as e:
            logger.error(
                f"Error getting chat history by session {session_id}: {str(e)}"
            )
            return None

    def update_chat_history(
        self,
        chat_id: str,
        messages: List[Dict],
        title: str = None,
        chat_subject: str = None,
    ) -> bool:
        """Update a chat history record."""
        if not self.is_available():
            return False

        try:
            with self.get_table("chat_history") as table:
                # Get existing record
                existing = table.search().where(f"chat_id = '{chat_id}'").to_list()
                if not existing:
                    return False

                record = existing[0]
                timestamp = datetime.utcnow().isoformat() + "Z"

                # Update fields
                record["messages_json"] = json.dumps(messages)
                record["updated_at"] = timestamp
                if title is not None:
                    record["title"] = title
                if chat_subject is not None:
                    record["chat_subject"] = chat_subject

                # Delete old record and add updated one
                table.delete(f"chat_id = '{chat_id}'")
                table.add([record])

                return True
        except Exception as e:
            logger.error(f"Error updating chat history {chat_id}: {str(e)}")
            return False

    def update_chat_history_by_session(
        self,
        session_id: str,
        messages: List[Dict],
        title: str = None,
        chat_subject: str = None,
    ) -> str:
        """Update chat history by session ID, create if doesn't exist."""
        existing = self.get_chat_history_by_session(session_id)

        if existing:
            self.update_chat_history(existing["chat_id"], messages, title, chat_subject)
            return existing["chat_id"]
        else:
            return self.create_chat_history(session_id, messages, title, chat_subject)

    def update_chat_subject(self, session_id: str, chat_subject: str) -> bool:
        """Update only the chat subject for a session."""
        if not self.is_available():
            return False

        try:
            with self.get_table("chat_history") as table:
                results = table.search().where(f"session_id = '{session_id}'").to_list()

                if results:
                    record = results[0]
                    record["chat_subject"] = chat_subject
                    record["updated_at"] = datetime.utcnow().isoformat() + "Z"

                    table.delete(f"session_id = '{session_id}'")
                    table.add([record])
                    return True
                return False
        except Exception as e:
            logger.error(
                f"Error updating chat subject for session {session_id}: {str(e)}"
            )
            return False

    def list_recent_chats(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List recent chat histories."""
        if not self.is_available():
            return []

        try:
            with self.get_table("chat_history") as table:
                results = table.search().to_list()

                # Sort by updated_at descending and apply limit
                sorted_results = sorted(
                    results, key=lambda x: x["updated_at"], reverse=True
                )[:limit]

                formatted_results = []
                for row in sorted_results:
                    messages = json.loads(row["messages_json"])
                    first_message = messages[0]["content"] if messages else ""

                    title = row["title"] or row["chat_subject"]
                    if not title and first_message:
                        title = (
                            first_message[:50] + "..."
                            if len(first_message) > 50
                            else first_message
                        )

                    formatted_results.append(
                        {
                            "chat_id": row["chat_id"],
                            "session_id": row["session_id"],
                            "title": title,
                            "chat_subject": row["chat_subject"],
                            "updated_at": row["updated_at"],
                        }
                    )

                return formatted_results
        except Exception as e:
            logger.error(f"Error listing recent chats: {str(e)}")
            return []

    def delete_chat_history(self, chat_id: str) -> bool:
        """Delete a chat history record."""
        if not self.is_available():
            return False

        try:
            with self.get_table("chat_history") as table:
                table.delete(f"chat_id = '{chat_id}'")
                return True
        except Exception as e:
            logger.error(f"Error deleting chat history {chat_id}: {str(e)}")
            return False

    # ==================== HOME AUTOMATION OPERATIONS ====================

    @staticmethod
    def hash_json(record):
        """Generate a hash for a JSON record."""
        if isinstance(record, dict):
            record_str = json.dumps(record, sort_keys=True)
        else:
            record_str = json.dumps(record)
        return hashlib.sha256(record_str.encode()).hexdigest()

    @staticmethod
    def get_static_fields_only(record: dict, collection_name: str) -> dict:
        """
        Extract only static fields from a record for hash comparison.

        Args:
            record: The full record dictionary
            collection_name: Type of collection (devices, variables, actions)

        Returns:
            Dictionary with only static fields
        """
        static_fields = STATIC_FIELDS.get(collection_name, set())
        return {k: v for k, v in record.items() if k in static_fields}

    @staticmethod
    def hash_static_fields(record: dict, collection_name: str) -> str:
        """
        Generate a hash using only static fields for change detection.

        Args:
            record: The full record dictionary
            collection_name: Type of collection (devices, variables, actions)

        Returns:
            SHA256 hash of static fields only
        """
        static_record = LanceDBManager.get_static_fields_only(record, collection_name)
        record_str = json.dumps(static_record, sort_keys=True)
        hash_value = hashlib.sha256(record_str.encode()).hexdigest()
        return hash_value

    @staticmethod
    def get_embedding_fields_only(record: dict, collection_name: str) -> dict:
        """
        Extract only fields needed for embedding text generation.

        Args:
            record: The full record dictionary
            collection_name: Type of collection (devices, variables, actions)

        Returns:
            Dictionary with only embedding-relevant fields
        """
        embedding_fields = EMBEDDING_FIELDS.get(collection_name, set())
        return {k: v for k, v in record.items() if k in embedding_fields}

    def _create_item_embedding_text(
        self, item: dict, collection_name: str = "devices"
    ) -> str:
        """
        Create embedding text for a home automation item using only embedding-relevant fields.
        This method creates consistent text representation excluding dynamic semantic keywords.

        Args:
            item: The item dictionary
            collection_name: Type of collection (devices, variables, actions)

        Returns:
            Text string for embedding generation
        """
        # Extract only embedding-relevant fields
        embedding_record = self.get_embedding_fields_only(item, collection_name)

        # Create base text from static fields
        base_text = json.dumps(embedding_record, sort_keys=True)

        # Note: We deliberately do NOT include semantic keywords here
        # because those are generated dynamically and should not affect hash comparison
        return base_text

    def load_embeddings_to_vector_store(
        self,
        json_data: dict,
        collection_name: str,
        batch_size: int = 50,
        max_workers: int = 4,
    ):
        """
        Process home automation data and load embeddings into LanceDB with optimized parallel processing.

        Args:
            json_data (dict): A json object to embed.
            collection_name (str): The name of the collection (devices, variables, actions).
            batch_size (int): Number of records to process in each batch for embedding generation.
            max_workers (int): Maximum number of parallel workers for processing.

        Returns:
            list: A list of valid records.
        """
        if not self.is_available():
            logger.warning(f"⚠️ Database unavailable, skipping {collection_name}")
            return []

        # Handle different response formats
        if isinstance(json_data, dict) and "error" in json_data:
            logger.error(
                f"Encountered API error in {collection_name} retrieval: {json_data['error']}"
            )
            raise Exception(
                f"Error retrieving data for collection {collection_name}: {json_data['error']}"
            )

        # Extract data list
        data_list = self._extract_data_list(json_data, collection_name)
        if not data_list:
            logger.debug(f"No valid records found for {collection_name}")
            return []

        valid_records = [
            obj for obj in data_list if isinstance(obj, dict) and "id" in obj
        ]
        if not valid_records:
            logger.debug(f"No valid records found for {collection_name}")
            return []

        ids_to_query = {obj["id"] for obj in valid_records}
        logger.debug(
            f"🔍 {collection_name}: Processing {len(valid_records)} valid records with IDs: {sorted(list(ids_to_query)[:5])}{'...' if len(ids_to_query) > 5 else ''}"
        )

        # Get existing records from LanceDB
        existing_records = []
        table_exists = False
        try:
            with self.get_table(collection_name) as table:
                existing_records = table.search().to_list()
                table_exists = True
                logger.debug(
                    f"🔍 {collection_name}: Found {len(existing_records)} existing records in database"
                )
        except Exception as e:
            # Table might not exist or be empty
            logger.debug(f"🔍 {collection_name}: Table does not exist or is empty: {e}")
            pass

        existing_ids = {record["id"] for record in existing_records}
        missing_ids = ids_to_query - existing_ids
        removed_ids = existing_ids - ids_to_query
        matched_ids = existing_ids - removed_ids

        logger.debug(
            f"🔍 {collection_name}: Record analysis - Total: {len(ids_to_query)}, Existing: {len(existing_ids)}, Missing: {len(missing_ids)}, Removed: {len(removed_ids)}, Matched: {len(matched_ids)}"
        )

        matching_records = [obj for obj in valid_records if obj["id"] in matched_ids]
        missing_records = [obj for obj in valid_records if obj["id"] in missing_ids]
        out_of_date_records = []

        # Calculate update count using static field hashing
        update_count = len(missing_records)

        for record in matching_records:
            existing_record = next(
                (r for r in existing_records if r["id"] == record["id"]), None
            )
            if existing_record:
                # Use static fields only for hash comparison
                record_hash = self.hash_static_fields(record, collection_name)
                if existing_record["hash"] != record_hash:
                    out_of_date_records.append(record)
                    update_count += 1

        # Start performance timer
        start_time = time.time()

        logger.debug(
            f"🔍 {collection_name}: Update summary - Missing: {len(missing_records)}, Out-of-date: {len(out_of_date_records)}, Total updates needed: {update_count}"
        )

        if update_count > 10:
            logger.info(f"************* IMPORTANT *************")
            logger.info(
                f"⚠️ Hello Indigo requires vector embeddings updates for {update_count} items."
            )
            logger.info(
                f"⚠️ This will take some time, and the plugin will not be functional until complete."
            )
            logger.info(f"⚠️ Updates will post to the Indigo Log on progress.")
            logger.info(f"************* IMPORTANT *************")
        elif update_count > 0:
            logger.debug(
                f"🔍 {collection_name}: Processing {update_count} embedding updates"
            )

        # Process embeddings with optimized parallel processing
        try:
            embeddings_to_add = self._process_embeddings_parallel(
                out_of_date_records,
                missing_records,
                existing_records,
                collection_name,
                batch_size,
                max_workers,
                update_count,
            )
        except RuntimeError as e:
            # Embedding generation failed completely
            logger.error(f"❌ {collection_name} embedding generation failed: {e}")
            return []

        # Batch database operations with progress tracking
        operations_time = time.time()
        total_db_operations = (len(embeddings_to_add) if embeddings_to_add else 0) + (
            len(removed_ids) if removed_ids else 0
        )

        db_progress = None
        if total_db_operations >= 10:
            db_progress = create_progress_tracker(
                f"Database Operations ({collection_name})", total_db_operations
            )

        # Bulk add new embeddings
        if embeddings_to_add:
            try:
                if db_progress:
                    db_progress.update(0, f"adding {len(embeddings_to_add)} records")

                with self.get_table(collection_name) as table:
                    table.add(embeddings_to_add)

                if db_progress:
                    db_progress.update(
                        len(embeddings_to_add),
                        f"added {len(embeddings_to_add)} records",
                    )
                else:
                    logger.debug(
                        f"✅ Batch added {len(embeddings_to_add)} records to {collection_name}"
                    )

            except Exception as e:
                logger.error(f"Error batch adding embeddings to {collection_name}: {e}")
                if db_progress:
                    db_progress.error(f"failed to add {len(embeddings_to_add)} records")

        # Bulk remove deleted records
        if removed_ids:
            try:
                current_progress = len(embeddings_to_add) if embeddings_to_add else 0
                if db_progress:
                    db_progress.update(
                        current_progress, f"deleting {len(removed_ids)} records"
                    )

                with self.get_table(collection_name) as table:
                    # Batch delete using OR conditions for better performance
                    delete_conditions = " OR ".join(
                        [f"id = {removed_id}" for removed_id in removed_ids]
                    )
                    table.delete(delete_conditions)

                if db_progress:
                    db_progress.update(
                        total_db_operations, f"deleted {len(removed_ids)} records"
                    )
                else:
                    logger.debug(
                        f"✅ Bulk deleted {len(removed_ids)} records from {collection_name}"
                    )

            except Exception as e:
                logger.warning(
                    f"Error bulk removing deleted records from {collection_name}: {e}"
                )
                if db_progress:
                    db_progress.error(f"failed to delete {len(removed_ids)} records")

        # Complete database operations progress
        if db_progress:
            db_progress.complete("database operations completed")

        # Performance reporting
        total_time = time.time() - start_time
        db_time = time.time() - operations_time
        processing_time = operations_time - start_time

        if embeddings_to_add:
            logger.info(
                f"✅ Updated '{collection_name}' embeddings: {len(embeddings_to_add)} records "
                f"(Processing: {processing_time:.2f}s, DB ops: {db_time:.2f}s, Total: {total_time:.2f}s)"
            )
        else:
            # Provide more context about why nothing was updated
            if update_count > 0:
                logger.error(
                    f"❌ '{collection_name}' embedding generation failed: {update_count} records needed updates but none were processed ({total_time:.2f}s)"
                )
            elif not table_exists and len(valid_records) > 0:
                logger.warning(
                    f"⚠️ '{collection_name}' table does not exist but no embeddings were generated. "
                    f"This indicates a logic error. ({total_time:.2f}s)"
                )
            elif len(valid_records) == 0:
                logger.info(
                    f"✅ '{collection_name}' embeddings: no valid records to process ({total_time:.2f}s)"
                )
            else:
                logger.debug(
                    f"✅ '{collection_name}' embeddings up to date ({total_time:.2f}s)"
                )

        return valid_records

    def _process_embeddings_parallel(
        self,
        out_of_date_records: List[Dict],
        missing_records: List[Dict],
        existing_records: List[Dict],
        collection_name: str,
        batch_size: int,
        max_workers: int,
        update_count: int,
    ) -> List[Dict]:
        """
        Process embeddings using parallel processing and batch operations.

        Args:
            out_of_date_records: Records that exist in database but have outdated hashes
            missing_records: Records that don't exist in database
            existing_records: Current database records
            collection_name: Name of the collection
            batch_size: Batch size for embedding generation
            max_workers: Maximum parallel workers
            update_count: Number of records needing updates

        Returns:
            List of embedding records to add to database
        """
        all_records = out_of_date_records + missing_records
        total_records = len(all_records)

        if total_records == 0:
            return []

        # Since we already have pre-calculated out_of_date_records and missing_records,
        # we can directly use them without recalculating hashes
        records_to_process = all_records  # All records passed in need processing
        records_to_delete = [record["id"] for record in out_of_date_records]

        # Details about records to process will be shown in summary

        if not records_to_process:
            logger.info(f"✅ No {collection_name} records need embedding updates")
            return []

        logger.info(f"📊 Embedding change summary for {collection_name}:")
        logger.info(f"   Updates: {len(out_of_date_records)}")
        logger.info(f"   New: {len(missing_records)}")

        # Processing details logged in summary above

        # Bulk delete outdated records first with improved error handling
        if records_to_delete:
            delete_success = False
            try:
                # Validate record IDs to prevent injection-like issues
                validated_ids = []
                for record_id in records_to_delete:
                    if isinstance(record_id, (int, str)) and str(record_id).strip():
                        # Sanitize and validate the ID
                        sanitized_id = str(record_id).replace(
                            "'", "''"
                        )  # Escape single quotes
                        validated_ids.append(sanitized_id)
                    else:
                        logger.warning(f"⚠️ Skipping invalid record ID: {record_id}")

                if validated_ids:
                    with self.get_table(collection_name) as table:
                        # Use safer delete condition construction
                        # Note: IDs are integers in home automation tables, not strings
                        if len(validated_ids) == 1:
                            delete_condition = f"id = {validated_ids[0]}"
                        else:
                            id_list = ", ".join(validated_ids)
                            delete_condition = f"id IN ({id_list})"

                        # Delete operation details logged on error only
                        table.delete(delete_condition)
                        delete_success = True
                        # Bulk delete success - details in final summary
                else:
                    logger.warning("⚠️ No valid record IDs to delete")

            except Exception as e:
                error_msg = f"❌ Error bulk deleting outdated records: {e}"
                logger.error(error_msg)

                # Attempt individual deletes as fallback
                if not delete_success and validated_ids:
                    logger.warning(
                        "🔄 Attempting individual record deletion as fallback..."
                    )
                    individual_success = 0

                    for record_id in validated_ids[:10]:  # Limit fallback attempts
                        try:
                            with self.get_table(collection_name) as table:
                                table.delete(f"id = {record_id}")
                                individual_success += 1
                        except Exception as individual_e:
                            logger.warning(
                                f"⚠️ Failed to delete individual record {record_id}: {individual_e}"
                            )

                    if individual_success > 0:
                        logger.info(
                            f"✅ Individually deleted {individual_success} records as fallback"
                        )
                    else:
                        logger.error("❌ All individual delete attempts failed")

        # Generate semantic keywords and embedding texts in parallel
        embedding_data = self._generate_embedding_data_parallel(
            records_to_process, collection_name, max_workers, update_count > 10
        )

        # Extract texts for batch embedding generation with validation
        if not embedding_data:
            logger.warning("⚠️ No embedding data to process")
            return []

        texts = []
        for i, data in enumerate(embedding_data):
            if not data or not isinstance(data, dict):
                logger.warning(f"⚠️ Invalid embedding data at index {i}: {data}")
                texts.append("")
            else:
                text = data.get("text", "")
                if not text or not text.strip():
                    logger.warning(
                        f"⚠️ Empty text in embedding data for ID {data.get('id', 'unknown')}"
                    )
                    texts.append("")
                else:
                    texts.append(text)

        if not any(texts):
            logger.error("❌ No valid texts found for embedding generation")
            return []

        # Generate embeddings in batches with error handling
        # Batch processing details will be shown in progress updates
        try:
            embeddings = self.batch_embed_texts(texts, batch_size, collection_name)
        except Exception as e:
            logger.error(f"❌ Critical error in batch embedding generation: {e}")
            return []

        # Validate embedding results
        if not embeddings:
            logger.error("❌ No embeddings returned from batch generation")
            return []

        if len(embeddings) != len(embedding_data):
            logger.error(
                f"❌ Embedding count mismatch: {len(embeddings)} vs {len(embedding_data)}"
            )
            # Attempt partial recovery for successful embeddings
            min_count = min(len(embeddings), len(embedding_data))
            if min_count > 0:
                logger.warning(f"⚠️ Proceeding with {min_count} partial embeddings")
                embeddings = embeddings[:min_count]
                embedding_data = embedding_data[:min_count]
            else:
                return []

        # Create final embedding records with validation
        embeddings_to_add = []
        failed_count = 0

        for i, (data, embedding) in enumerate(zip(embedding_data, embeddings)):
            try:
                # Validate embedding data
                if not data or not isinstance(data, dict):
                    logger.warning(f"⚠️ Invalid data structure at index {i}")
                    failed_count += 1
                    continue

                # Validate embedding
                if (
                    not embedding
                    or not isinstance(embedding, list)
                    or len(embedding) == 0
                ):
                    logger.warning(
                        f"⚠️ Invalid or empty embedding for ID {data.get('id', 'unknown')}"
                    )
                    failed_count += 1
                    continue

                # Create embedding record with validation
                record = {
                    "id": data.get("id", f"unknown_{i}"),
                    "name": data.get("name", ""),
                    "text": data.get("original_text", data.get("text", "")),
                    "hash": data.get("hash", ""),
                    "embedding": embedding,
                }

                # Validate required fields
                if not record["id"] or not record["hash"]:
                    logger.warning(
                        f"⚠️ Missing required fields in record {i}: id={record['id']}, hash={record['hash']}"
                    )
                    failed_count += 1
                    continue

                embeddings_to_add.append(record)

            except Exception as e:
                logger.error(f"❌ Error creating embedding record {i}: {e}")
                failed_count += 1
                continue

        # Report processing results
        success_count = len(embeddings_to_add)
        total_count = len(embedding_data)

        if failed_count > 0:
            logger.warning(
                f"⚠️ Embedding processing completed with {failed_count} failures out of {total_count} records"
            )
            if failed_count > total_count * 0.5:  # More than 50% failed
                logger.error(
                    f"❌ High failure rate in embedding processing: {failed_count}/{total_count} failed"
                )

        # Success count included in main summary
        return embeddings_to_add

    def _generate_embedding_data_parallel(
        self,
        records: List[Dict],
        collection_name: str,
        max_workers: int,
        show_progress: bool = False,
    ) -> List[Dict]:
        """
        Generate embedding text and semantic keywords for records using batch processing.

        Args:
            records: List of records to process
            max_workers: Maximum parallel workers (now used for batch size)
            show_progress: Whether to show progress updates

        Returns:
            List of dictionaries with embedding data
        """
        embedding_data = []
        total_records = len(records)

        # Use max_workers as an indicator for batch size (convert from thread count to batch size)
        keyword_batch_size = max(5, min(15, max_workers * 3))  # 5-15 devices per batch

        logger.debug(
            f"🏷️  Processing {total_records} records in batches of {keyword_batch_size}"
        )

        try:
            # Import batch keyword generator
            from hello_indigo_api.agents.common.semantic_search import (
                generate_batch_device_keywords,
            )

            # Generate keywords for all devices in batches
            all_keywords = generate_batch_device_keywords(
                records, batch_size=keyword_batch_size, collection_name=collection_name
            )

            # Process each record with its generated keywords
            failed_count = 0
            for i, record in enumerate(records):
                try:
                    # Extract only embedding-relevant fields for base text
                    embedding_record = self.get_embedding_fields_only(
                        record, collection_name
                    )

                    # Get pre-generated semantic keywords
                    record_id = str(record.get("id", ""))
                    semantic_keywords = all_keywords.get(record_id, [])

                    # Create enhanced embedding text
                    base_text = json.dumps(embedding_record, sort_keys=True)
                    if semantic_keywords:
                        keywords_text = " ".join(semantic_keywords)
                        text_for_embedding = f"{base_text} {keywords_text}"
                    else:
                        # Fallback to base text only if no keywords
                        text_for_embedding = base_text

                    embedding_data.append(
                        {
                            "id": record["id"],
                            "name": record["name"],
                            "text": text_for_embedding,
                            "original_text": json.dumps(record),
                            "hash": self.hash_static_fields(record, collection_name),
                        }
                    )

                    # Progress reporting
                    if show_progress and (i + 1) % max(1, total_records // 10) == 0:
                        current_progress = int((i + 1) / total_records * 100)
                        logger.info(
                            f"🚀 Processing records: {current_progress}% complete ({i + 1}/{total_records})"
                        )

                except Exception as e:
                    logger.error(
                        f"Error processing record {record.get('id', 'unknown')}: {e}"
                    )
                    failed_count += 1
                    # Add record with fallback text
                    try:
                        embedding_record = self.get_embedding_fields_only(
                            record, collection_name
                        )
                        fallback_text = json.dumps(embedding_record, sort_keys=True)
                        embedding_data.append(
                            {
                                "id": record["id"],
                                "name": record["name"],
                                "text": fallback_text,
                                "original_text": json.dumps(record),
                                "hash": self.hash_static_fields(
                                    record, collection_name
                                ),
                            }
                        )
                    except Exception:
                        # Skip this record entirely if it can't be processed
                        continue

        except Exception as e:
            logger.error(f"❌ Critical error in batch processing: {e}")
            # Fallback to simple processing without keywords
            for record in records:
                try:
                    embedding_record = self.get_embedding_fields_only(
                        record, collection_name
                    )
                    fallback_text = json.dumps(embedding_record, sort_keys=True)
                    embedding_data.append(
                        {
                            "id": record["id"],
                            "name": record["name"],
                            "text": fallback_text,
                            "original_text": json.dumps(record),
                            "hash": self.hash_static_fields(record, collection_name),
                        }
                    )
                except Exception:
                    continue

        # Report processing results
        success_count = len(embedding_data)
        if total_records > 0:
            success_rate = success_count / total_records
            if success_rate < 0.8:  # Less than 80% success
                logger.warning(
                    f"⚠️ Processing completed with {success_count}/{total_records} successful records"
                )

            # If completely failed and we have records to process, raise error
            if success_count == 0:
                error_msg = f"Failed to generate embeddings for any of the {total_records} {collection_name} records"
                logger.error(f"❌ {error_msg}")
                raise RuntimeError(error_msg)

        return embedding_data

    def _extract_data_list(self, json_data, collection_name):
        """Extract data list from various response formats."""
        if isinstance(json_data, dict) and "data" in json_data:
            return json_data["data"]
        elif isinstance(json_data, list):
            return json_data
        elif isinstance(json_data, dict):
            # Look for common keys
            for key in ["devices", "variables", "actions", "actionGroups", "data"]:
                if key in json_data and isinstance(json_data[key], list):
                    return json_data[key]
            # If no list found, assume the dict itself contains the data
            return [json_data]
        else:
            raise ValueError(
                f"Unexpected data format for {collection_name}: {type(json_data)}"
            )

    def search_home_automation_items(
        self,
        query_text: str,
        collection_name: str,
        top_k: int = 10,
        similarity_threshold: float = 0.55,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar home automation items using vector similarity.

        Args:
            query_text: The search query
            collection_name: Which collection to search (devices, variables, actions)
            top_k: Number of results to return
            similarity_threshold: Minimum similarity score

        Returns:
            List of similar items with similarity scores
        """
        if not self.is_available():
            return []

        try:
            # Generate query embedding
            from hello_indigo_api.agents.common.openai_client import emb_text

            query_embedding = emb_text(query_text)

            with self.get_table(collection_name) as table:
                # Check table size for debugging
                try:
                    total_items = table.count_rows()
                    logger.debug(
                        f"🔍 Table '{collection_name}' contains {total_items} items before search"
                    )
                except Exception as e:
                    logger.debug(f"🔍 Could not count rows in '{collection_name}': {e}")

                # Perform vector search with cosine metric
                results = (
                    table.search(query_embedding)
                    .metric("cosine")
                    .limit(top_k)
                    .to_list()
                )
                logger.debug(
                    f"🔍 Raw vector search returned {len(results)} results for '{collection_name}'"
                )

                # Format results and filter by similarity threshold
                similar_items = []
                for i, result in enumerate(results):
                    # For cosine metric, _distance is already cosine distance (0 to 2)
                    # Convert to similarity: cosine_similarity = 1 - (cosine_distance / 2)
                    cosine_distance = result.get("_distance", 0)
                    similarity_score = 1 - (cosine_distance / 2)

                    # Log first few results regardless of threshold for debugging
                    if i < 5:
                        logger.debug(
                            f"🔍 {collection_name}[{i}]: '{result.get('name', 'N/A')}' score={similarity_score:.4f} (threshold={similarity_threshold})"
                        )

                    if similarity_score >= similarity_threshold:
                        similar_items.append(
                            {
                                "id": result["id"],
                                "name": result["name"],
                                "text": result["text"],
                                "similarity_score": similarity_score,
                            }
                        )

                logger.debug(
                    f"🔍 {len(similar_items)} items from '{collection_name}' passed similarity threshold {similarity_threshold}"
                )
                return similar_items

        except Exception as e:
            logger.error(f"Failed to search {collection_name}: {e}")
            return []

    def get_collection_stats(self, collection_name: str = None) -> Dict[str, Any]:
        """Get statistics about collections."""
        if not self.is_available():
            return {"error": "Database not available"}

        try:
            if collection_name:
                # Stats for specific collection
                with self.get_table(collection_name) as table:
                    count = len(table.search().to_list())
                    return {
                        "collection_name": collection_name,
                        "total_entities": count,
                        "dimension": self.dimension,
                    }
            else:
                # Stats for all collections
                stats = {}
                for table_name in self.db.table_names():
                    try:
                        with self.get_table(table_name) as table:
                            count = len(table.search().to_list())
                            stats[table_name] = count
                    except Exception as e:
                        stats[table_name] = f"Error: {str(e)}"

                return {
                    "database_path": self.db_path,
                    "tables": stats,
                    "dimension": self.dimension,
                }
        except Exception as e:
            return {"error": str(e)}

    def batch_embed_texts(
        self, texts: List[str], batch_size: int = 50, collection_name: str = "items"
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batches for improved performance.

        Args:
            texts: List of text strings to embed
            batch_size: Number of texts to process in each batch

        Returns:
            List of embeddings corresponding to the input texts
        """
        if not texts:
            return []

        # Filter out empty texts and track their positions
        valid_texts = []
        text_positions = []

        for i, text in enumerate(texts):
            if text and text.strip():
                valid_texts.append(text.strip())
                text_positions.append(i)
            else:
                logger.warning(f"⚠️ Skipping empty text at position {i}")

        if not valid_texts:
            logger.warning("⚠️ No valid texts to embed, returning empty lists")
            return [[] for _ in texts]

        embeddings = [
            [] for _ in texts
        ]  # Initialize with empty lists for all positions
        from hello_indigo_api.agents.common.openai_client import _get_client

        client = _get_client()
        model = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

        max_retries = 3
        base_delay = 2.0
        successful_batches = 0
        failed_batches = []

        # Add progress tracking for embedding generation
        total_batches = (len(valid_texts) + batch_size - 1) // batch_size
        progress = None
        if len(valid_texts) >= 10:
            progress = create_progress_tracker(
                f"Embedding Generation ({collection_name})", len(valid_texts)
            )

        try:
            # Process valid texts in batches
            for batch_idx in range(0, len(valid_texts), batch_size):
                batch = valid_texts[batch_idx : batch_idx + batch_size]
                batch_positions = text_positions[batch_idx : batch_idx + batch_size]

                batch_num = batch_idx // batch_size + 1

                # Retry logic for each batch
                batch_success = False
                for attempt in range(max_retries):
                    try:
                        # OpenAI embeddings API with timeout
                        response = client.embeddings.create(
                            model=model,
                            input=batch,
                            timeout=60.0,  # 60 second timeout per batch
                        )

                        # Validate response
                        if not response or not response.data:
                            raise ValueError(
                                "Invalid response from OpenAI embeddings API"
                            )

                        if len(response.data) != len(batch):
                            raise ValueError(
                                f"Response count mismatch: got {len(response.data)}, expected {len(batch)}"
                            )

                        # Extract and validate embeddings
                        batch_embeddings = []
                        for data in response.data:
                            if not data.embedding or len(data.embedding) == 0:
                                raise ValueError("Empty embedding in response")
                            batch_embeddings.append(data.embedding)

                        # Place embeddings in correct positions
                        for embedding, pos in zip(batch_embeddings, batch_positions):
                            embeddings[pos] = embedding

                        successful_batches += 1
                        batch_success = True

                        # Update progress tracking
                        if progress:
                            texts_processed = min(
                                batch_idx + len(batch), len(valid_texts)
                            )
                            progress.update(
                                texts_processed,
                                f"batch {batch_num}/{total_batches} complete",
                            )

                        break

                    except Exception as e:
                        error_msg = f"Batch {batch_num} attempt {attempt + 1}/{max_retries} failed: {e}"

                        if attempt < max_retries - 1:
                            delay = base_delay * (2**attempt)
                            logger.warning(
                                f"⚠️ {error_msg}, retrying in {delay:.1f}s..."
                            )
                            import time

                            time.sleep(delay)
                        else:
                            logger.error(f"❌ {error_msg}, all retries exhausted")

                # Track failed batches for fallback processing
                if not batch_success:
                    failed_batches.extend(
                        [(text, pos) for text, pos in zip(batch, batch_positions)]
                    )

            logger.info(
                f"📊 Batch processing summary: {successful_batches}/{total_batches} batches successful"
            )

            # Fallback to individual embeddings for failed texts
            if failed_batches:
                logger.warning(
                    f"🔄 Processing {len(failed_batches)} failed texts individually..."
                )
                from hello_indigo_api.agents.common.openai_client import emb_text

                for text, pos in failed_batches:
                    try:
                        individual_embedding = emb_text(text)
                        if individual_embedding:  # emb_text returns [] on failure
                            embeddings[pos] = individual_embedding
                        else:
                            logger.error(
                                f"❌ Failed to generate embedding for text at position {pos}"
                            )
                    except Exception as e:
                        logger.error(
                            f"❌ Individual embedding failed for position {pos}: {e}"
                        )

            # Count successful embeddings
            success_count = sum(1 for emb in embeddings if emb)

            # Complete progress tracking
            if progress:
                progress.complete(
                    f"generated {success_count}/{len(texts)} embeddings successfully"
                )
            else:
                logger.debug(
                    f"✅ Generated {success_count}/{len(texts)} embeddings successfully"
                )

            return embeddings

        except Exception as e:
            logger.error(f"❌ Critical error in batch embedding generation: {e}")
            # Last resort fallback
            logger.debug(
                "🔄 Falling back to individual embedding generation for all texts"
            )
            from hello_indigo_api.agents.common.openai_client import emb_text

            result_embeddings = []
            for text in texts:
                try:
                    if text and text.strip():
                        embedding = emb_text(text.strip())
                        result_embeddings.append(embedding if embedding else [])
                    else:
                        result_embeddings.append([])
                except Exception as e:
                    logger.error(f"❌ Fallback embedding failed for text: {e}")
                    result_embeddings.append([])

            return result_embeddings

    def batch_add_home_automation_items(
        self, collection_name: str, items: List[Dict[str, Any]], batch_size: int = 50
    ) -> bool:
        """
        Add multiple home automation items with batch embedding generation.

        Args:
            collection_name: Name of the collection ('devices', 'variables', 'actions')
            items: List of item dictionaries to add
            batch_size: Batch size for embedding generation

        Returns:
            True if successful, False otherwise
        """
        if not self.is_available() or not items:
            return False

        try:
            # Extract texts for batch embedding
            texts = []
            for item in items:
                text = self._create_item_embedding_text(item, collection_name)
                texts.append(text)

            # Generate embeddings in batches
            embeddings = self.batch_embed_texts(texts, batch_size, collection_name)

            if len(embeddings) != len(items):
                logger.error(
                    f"❌ Embedding count mismatch: {len(embeddings)} vs {len(items)}"
                )
                return False

            # Create records with embeddings
            records = []
            for item, embedding in zip(items, embeddings):
                record = {
                    "id": str(item.get("id", "")),
                    "name": item.get("name", ""),
                    "text": texts[len(records)],  # Use corresponding text
                    "data": json.dumps(item),
                    "vector": embedding,
                }
                records.append(record)

            # Add all records to the collection
            with self.get_table(collection_name) as table:
                table.add(records)

            logger.info(f"✅ Batch added {len(records)} items to {collection_name}")
            return True

        except Exception as e:
            logger.error(f"❌ Batch add to {collection_name} failed: {e}")
            return False

    def close(self):
        """Close the database connection."""
        try:
            if self.db:
                # LanceDB connections are automatically managed
                self.db = None
                # Database connection closed
        except Exception as e:
            logger.error(f"Error closing database connection: {e}")
