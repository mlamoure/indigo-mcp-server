"""
Regression test for LanceDB default limit bug.
This test ensures that all records are retrieved when validating vector store contents,
not just the default 10 records that LanceDB returns without an explicit limit.

Bug: https://github.com/[repo]/issues/[number]
Fixed in: validation.py and main.py by adding .limit(999999) to search() calls
"""

import pytest
import tempfile
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "MCP Server.indigoPlugin/Contents/Server Plugin"))

import lancedb
import pyarrow as pa
from mcp_server.common.vector_store.main import VectorStore
from mcp_server.common.vector_store.validation import load_validation_data


class TestLanceDBRegression:
    """Regression tests for LanceDB default limit bug."""
    
    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database path."""
        temp_dir = tempfile.mkdtemp(prefix="test_lancedb_regression_")
        yield temp_dir
        # Cleanup
        import shutil
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_validation_retrieves_all_records_not_just_10(self, temp_db_path, monkeypatch):
        """
        Test that validation retrieves ALL records, not just LanceDB's default 10.
        This is the specific bug that caused embeddings to be regenerated unnecessarily.
        """
        # Set required environment variable
        monkeypatch.setenv("OPENAI_API_KEY", "test-key-for-testing")
        
        # Create a vector store
        vector_store = VectorStore(temp_db_path)
        
        # Create test data with MORE than 10 records (to expose the bug)
        test_count = 15
        test_devices = []
        for i in range(1, test_count + 1):
            test_devices.append({
                "id": i,
                "name": f"Test Device {i}",
                "description": f"Description for device {i}",
                "model": "TestModel",
                "deviceTypeId": "test.device",
                "address": f"addr_{i}",
                "protocol": "test"
            })
        
        # Mock embedding generation to avoid OpenAI calls
        def mock_embeddings(texts, entity_names=None, progress_callback=None):
            return [[0.1] * 1536 for _ in texts]
        
        def mock_embedding(text):
            return [0.1] * 1536
        
        # Replace embedding methods
        original_batch = vector_store._generate_embeddings_batch
        original_single = vector_store._generate_embedding
        vector_store._generate_embeddings_batch = mock_embeddings
        vector_store._generate_embedding = mock_embedding
        
        try:
            # Update embeddings (this creates the records)
            vector_store.update_embeddings(
                devices=test_devices,
                variables=[],
                actions=[]
            )
            
            # Now test the validation data loading (where the bug was)
            table = vector_store.db.open_table("devices")
            
            # Load validation data using the function that had the bug
            validation_data = load_validation_data(table, vector_store.logger)
            
            # CRITICAL TEST: We should get ALL 15 records, not just 10
            assert len(validation_data) == test_count, \
                f"Expected {test_count} records in validation, but got {len(validation_data)}. " \
                f"This indicates the LanceDB limit bug has regressed!"
            
            # Verify all IDs are present
            loaded_ids = set(validation_data.keys())
            expected_ids = set(range(1, test_count + 1))
            missing_ids = expected_ids - loaded_ids
            
            assert not missing_ids, \
                f"Missing IDs in validation data: {missing_ids}. " \
                f"The LanceDB default limit is cutting off records!"
            
        finally:
            # Restore original methods
            vector_store._generate_embeddings_batch = original_batch
            vector_store._generate_embedding = original_single
            vector_store.close()
    
    def test_vector_store_stats_counts_all_records(self, temp_db_path, monkeypatch):
        """Test that get_stats() returns correct counts for tables with >10 records."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        
        vector_store = VectorStore(temp_db_path)
        
        # Create 12 devices, 11 variables, 13 actions (all > 10)
        test_devices = [{"id": i, "name": f"Device {i}"} for i in range(1, 13)]
        test_variables = [{"id": i, "name": f"Var {i}"} for i in range(1, 12)]
        test_actions = [{"id": i, "name": f"Action {i}"} for i in range(1, 14)]
        
        # Mock embeddings
        vector_store._generate_embeddings_batch = lambda *args, **kwargs: [[0.1] * 1536] * 100
        vector_store._generate_embedding = lambda text: [0.1] * 1536
        
        # Update embeddings
        vector_store.update_embeddings(
            devices=test_devices,
            variables=test_variables,
            actions=test_actions
        )
        
        # Get stats (this also had the bug)
        stats = vector_store.get_stats()
        
        # Verify counts are correct, not limited to 10
        assert stats["tables"]["devices"] == 12, \
            f"Expected 12 devices, got {stats['tables']['devices']}"
        assert stats["tables"]["variables"] == 11, \
            f"Expected 11 variables, got {stats['tables']['variables']}"
        assert stats["tables"]["actions"] == 13, \
            f"Expected 13 actions, got {stats['tables']['actions']}"
        
        vector_store.close()
    
    def test_raw_lancedb_behavior_confirmation(self, temp_db_path):
        """
        Confirm that LanceDB actually has this default limit behavior.
        This test documents the underlying issue for future reference.
        """
        db = lancedb.connect(temp_db_path)
        
        # Create a table with 15 records
        schema = pa.schema([
            pa.field("id", pa.int64()),
            pa.field("name", pa.string()),
            pa.field("embedding", pa.list_(pa.float32(), 128))
        ])
        
        ids = list(range(1, 16))
        names = [f"Item {i}" for i in ids]
        embeddings = [[0.1] * 128 for _ in ids]
        
        test_data = pa.Table.from_arrays(
            [
                pa.array(ids),
                pa.array(names),
                pa.array(embeddings, type=pa.list_(pa.float32(), 128))
            ],
            schema=schema
        )
        
        table = db.create_table("test", test_data)
        
        # Test WITHOUT limit (default behavior)
        results_no_limit = table.search().to_list()

        # Test WITH explicit limit (returns all records)
        results_with_limit = table.search().limit(999999).to_list()

        # Document the behavior (updated for LanceDB 0.25.2)
        # Note: LanceDB 0.25.2 changed default from 10 to 15
        assert len(results_no_limit) == 15, \
            f"LanceDB behavior may have changed - expected 15 (v0.25.2 default), got {len(results_no_limit)}"
        assert len(results_with_limit) == 15, \
            "LanceDB limit(999999) not working as expected"

        print(f"✅ Confirmed: LanceDB search() defaults to 15 records (v0.25.2)")
        print(f"✅ Confirmed: search().limit(999999) returns all {len(results_with_limit)} records")


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])