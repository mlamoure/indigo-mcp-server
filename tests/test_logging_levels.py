"""
Test script to verify logging level changes for vector store operations.
"""

import sys
import os
import logging
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
    
    # Create manager with mocked vector store
    with patch('mcp_server.common.vector_store.vector_store_manager.VectorStore') as MockVectorStore:
        # Mock the vector store instance
        mock_vs = Mock()
        mock_vs.update_embeddings = Mock()
        MockVectorStore.return_value = mock_vs
        
        manager = VectorStoreManager(mock_provider, "/tmp/test_db", logger=logger, update_interval=0)
        manager.vector_store = mock_vs  # Ensure vector store is set
        
        # Clear previous logs
        log_capture.clear()
        
        # Trigger update
        manager.update_now()
        
        # Check that routine sync messages are DEBUG level
        info_logs = [msg for level, msg in log_capture if level == 'INFO']
        debug_logs = [msg for level, msg in log_capture if level == 'DEBUG']
        
        print(f"INFO logs: {len(info_logs)}")
        print(f"DEBUG logs: {len(debug_logs)}")
        
        # Verify sync start/complete are debug level
        assert any("Starting vector store synchronization" in msg for level, msg in log_capture if level == 'DEBUG'), \
            "Sync start should be DEBUG level"
        assert any("synchronization completed" in msg for level, msg in log_capture if level == 'DEBUG'), \
            "Sync complete should be DEBUG level"
    
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