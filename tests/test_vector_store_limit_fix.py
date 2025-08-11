#!/usr/bin/env python3
"""
Test script to verify that the vector store correctly retrieves all records
instead of being limited by LanceDB's default limit.
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "MCP Server.indigoPlugin/Contents/Server Plugin"))

from mcp_server.common.vector_store.main import VectorStore
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("TestVectorStore")


def create_test_entities(count: int):
    """Create test entities for testing."""
    entities = []
    for i in range(count):
        entities.append({
            "id": i + 1,
            "name": f"Test Device {i + 1}",
            "description": f"Test device number {i + 1}",
            "model": "TestModel",
            "deviceTypeId": "test.device",
            "address": f"test_{i + 1}",
            "protocol": "test"
        })
    return entities


def test_vector_store_limit_fix():
    """Test that all records are retrieved when checking table counts."""
    
    # Create temporary directory for test database
    temp_dir = tempfile.mkdtemp(prefix="test_vector_store_")
    db_path = os.path.join(temp_dir, "test_db")
    
    try:
        # Set up OpenAI API key (use a dummy key for testing - we'll mock the calls)
        os.environ["OPENAI_API_KEY"] = "test-key-for-testing"
        
        # Create vector store
        logger.info(f"Creating vector store at: {db_path}")
        vector_store = VectorStore(db_path, logger=logger)
        
        # Create 50 test entities (more than the default limit of 10)
        test_count = 50
        test_entities = create_test_entities(test_count)
        logger.info(f"Created {test_count} test entities")
        
        # Mock the embedding generation to avoid API calls
        original_generate_embeddings = vector_store._generate_embeddings_batch
        def mock_embeddings(texts, entity_names=None, progress_callback=None):
            # Return dummy embeddings
            return [[0.1] * 1536 for _ in texts]
        vector_store._generate_embeddings_batch = mock_embeddings
        
        # Mock individual embedding generation as well
        original_generate_embedding = vector_store._generate_embedding
        def mock_embedding(text):
            return [0.1] * 1536
        vector_store._generate_embedding = mock_embedding
        
        # Skip keyword generation by directly adding records
        # This avoids the OpenAI API call issue in the test
        
        # Update embeddings for test entities
        logger.info("Updating embeddings for test entities...")
        vector_store._update_entity_embeddings("devices", test_entities)
        
        # Now test that we can retrieve all records
        logger.info("Testing record retrieval...")
        stats = vector_store.get_stats()
        
        device_count = stats["tables"]["devices"]
        logger.info(f"Retrieved {device_count} devices from stats")
        
        # Verify we got all records, not just 10
        if device_count == test_count:
            logger.info(f"✅ SUCCESS: Retrieved all {test_count} records (not limited to 10)")
            return True
        elif device_count == 10:
            logger.error(f"❌ FAILURE: Only retrieved 10 records (default limit still in effect)")
            return False
        else:
            logger.warning(f"⚠️ UNEXPECTED: Retrieved {device_count} records (expected {test_count})")
            return False
            
    except Exception as e:
        logger.error(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # Clean up temporary directory
        if os.path.exists(temp_dir):
            logger.info(f"Cleaning up temporary directory: {temp_dir}")
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    success = test_vector_store_limit_fix()
    sys.exit(0 if success else 1)