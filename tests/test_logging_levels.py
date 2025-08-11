"""
Test script to verify logging level changes for vector store operations.
"""

import sys
import os
import logging
import pytest
from unittest.mock import Mock, MagicMock, patch

# Add plugin directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "MCP Server.indigoPlugin", "Contents", "Server Plugin"))

def test_vector_store_logging():
    """Test that routine vector store operations use appropriate logging levels."""
    
    # Configure logging to capture all levels
    logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')
    logger = logging.getLogger("Plugin")
    
    # Capture log output
    log_capture = []
    
    class LogCapture(logging.Handler):
        def emit(self, record):
            log_capture.append((record.levelname, record.getMessage()))
    
    handler = LogCapture()
    logger.addHandler(handler)
    
    # Test 1: Vector Store Manager logging
    print("\n=== Testing VectorStoreManager logging ===")
    from mcp_server.common.vector_store.vector_store_manager import VectorStoreManager
    
    # Mock data provider
    mock_provider = Mock()
    mock_provider.get_all_entities_for_vector_store.return_value = {
        "devices": [{"id": 1, "name": "Test Light"}],
        "variables": [],
        "actions": []
    }
    
    # Comprehensive mocking to prevent time-consuming operations but allow logging
    with patch('mcp_server.common.vector_store.main.VectorStore') as MockVectorStore, \
         patch('mcp_server.common.openai_client.main.perform_completion') as MockLLM, \
         patch('threading.Thread') as MockThread, \
         patch('lancedb.connect') as MockLanceDB:
        
        # Create mock vector store that allows logging to pass through
        mock_vs = Mock()
        mock_vs.update_embeddings = Mock(return_value=None)  # Quick mock return
        mock_vs.close = Mock(return_value=None)
        mock_vs.get_stats = Mock(return_value={"entity_count": 1})
        MockVectorStore.return_value = mock_vs
        
        # Mock LLM to prevent any OpenAI calls
        MockLLM.return_value = "mocked response"
        
        # Mock threading to prevent background threads
        mock_thread = Mock()
        mock_thread.start = Mock()
        mock_thread.is_alive = Mock(return_value=False)
        mock_thread.join = Mock()
        MockThread.return_value = mock_thread
        
        # Mock LanceDB to prevent database operations
        mock_db = Mock()
        mock_db.table_names = Mock(return_value=["devices", "variables", "actions"])  # Pretend tables exist
        mock_table = Mock()
        mock_table.search = Mock(return_value=Mock())
        mock_table.search.return_value.to_list = Mock(return_value=[])
        mock_db.open_table = Mock(return_value=mock_table)
        MockLanceDB.return_value = mock_db
        
        manager = VectorStoreManager(mock_provider, "/tmp/test_db", logger=logger, update_interval=0)
        
        # Initialize the vector store - this should now be fast
        manager.start()
        
        # Clear previous logs
        log_capture.clear()
        
        # Trigger update - this should generate logs but do no actual work
        manager.update_now()
        
        # Check that routine sync messages are DEBUG level
        info_logs = [msg for level, msg in log_capture if level == 'INFO']
        debug_logs = [msg for level, msg in log_capture if level == 'DEBUG']
        
        print(f"INFO logs: {len(info_logs)}")
        print(f"DEBUG logs: {len(debug_logs)}")
        
        # Debug: Print all captured logs
        print("All captured logs:")
        for level, msg in log_capture:
            print(f"  {level}: {repr(msg)}")

        # Verify sync start/complete are debug level (updated to match actual log messages)
        assert any("Starting vector store synchronization" in msg for level, msg in log_capture if level == 'DEBUG'), \
            f"Sync start should be DEBUG level. Found: {[msg for level, msg in log_capture if level == 'DEBUG']}"
        assert any("synchronization completed" in msg for level, msg in log_capture if level == 'DEBUG'), \
            f"Sync complete should be DEBUG level. Found: {[msg for level, msg in log_capture if level == 'DEBUG']}"
    
    # Test 2: Validation logging
    print("\n=== Testing validation logging ===")
    from mcp_server.common.vector_store.validation import log_validation_summary, ValidationResult
    
    # Create validation result with no issues
    result = ValidationResult()
    result.total_checked = 10
    result.valid_count = 10
    
    log_capture.clear()
    log_validation_summary(result, "devices", logger)
    
    # Should only have debug logs when everything is up to date
    info_logs = [msg for level, msg in log_capture if level == 'INFO']
    debug_logs = [msg for level, msg in log_capture if level == 'DEBUG']
    
    print(f"INFO logs when all valid: {len(info_logs)}")
    print(f"DEBUG logs when all valid: {len(debug_logs)}")
    
    assert len(info_logs) == 0, "No INFO logs when everything is up to date"
    assert len(debug_logs) > 0, "Should have DEBUG logs for status"
    
    print("\n✅ All logging level tests passed!")
    print("\nSummary:")
    print("- Routine sync operations log at DEBUG level")
    print("- Validation details log at DEBUG level")
    print("- Only actual entity updates trigger INFO level logs")
    
if __name__ == "__main__":
    test_vector_store_logging()