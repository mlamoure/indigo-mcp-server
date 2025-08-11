"""
Tests for the vector store validation module.
This module was previously untested and contained the LanceDB limit bug.
"""

import pytest
import json
from unittest.mock import Mock, MagicMock
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "MCP Server.indigoPlugin/Contents/Server Plugin"))

from mcp_server.common.vector_store.validation import (
    ValidationIssueType,
    ValidationIssue,
    ValidationResult,
    load_validation_data,
    detect_keyword_completeness,
    validate_embedding,
    validate_stored_data,
    perform_comprehensive_validation,
    prioritize_updates,
    log_validation_summary
)


class TestValidationDataStructures:
    """Test validation data structures and classes."""
    
    def test_validation_issue_creation(self):
        """Test ValidationIssue creation and string representation."""
        issue = ValidationIssue(123, ValidationIssueType.MISSING_RECORD, "Not found")
        assert issue.entity_id == 123
        assert issue.issue_type == ValidationIssueType.MISSING_RECORD
        assert issue.details == "Not found"
        assert str(issue) == "missing_record[123]: Not found"
    
    def test_validation_result_operations(self):
        """Test ValidationResult methods."""
        result = ValidationResult()
        
        # Add issues
        result.add_issue(1, ValidationIssueType.MISSING_RECORD, "Missing")
        result.add_issue(2, ValidationIssueType.HASH_MISMATCH, "Changed")
        result.add_issue(3, ValidationIssueType.MISSING_RECORD, "Also missing")
        
        # Add valid entries
        result.add_valid()
        result.add_valid()
        result.total_checked = 5
        
        # Test issue retrieval
        assert len(result.issues) == 3
        assert result.valid_count == 2
        assert result.has_issues() == True
        
        # Test filtering by type
        missing_issues = result.get_issues_by_type(ValidationIssueType.MISSING_RECORD)
        assert len(missing_issues) == 2
        
        # Test entity ID retrieval
        missing_ids = result.get_entity_ids_by_type(ValidationIssueType.MISSING_RECORD)
        assert missing_ids == {1, 3}
        
        # Test summary
        summary = result.summary()
        assert summary["total_checked"] == 5
        assert summary["valid_count"] == 2
        assert summary["total_issues"] == 3
        assert summary["missing_record"] == 2
        assert summary["hash_mismatch"] == 1


class TestLoadValidationData:
    """Test the load_validation_data function that had the bug."""
    
    def test_load_validation_data_with_various_sizes(self):
        """Test loading validation data with different table sizes."""
        # Create mock logger
        logger = Mock()
        
        # Test with different row counts
        test_cases = [
            (0, "empty table"),
            (1, "single record"),
            (10, "exactly 10 records (edge case)"),
            (11, "11 records (exposes bug)"),
            (50, "50 records"),
            (100, "100 records"),
        ]
        
        for count, description in test_cases:
            # Create mock table
            mock_table = Mock()
            
            # Create mock rows
            mock_rows = []
            for i in range(count):
                mock_rows.append({
                    "id": i + 1,
                    "hash": f"hash_{i+1}",
                    "text": f"text_{i+1}",
                    "embedding": [0.1] * 10,
                    "name": f"Entity {i+1}",
                    "data": json.dumps({"id": i + 1})
                })
            
            # Mock search to return all rows WITH LIMIT
            mock_search = Mock()
            mock_search.limit.return_value.to_list.return_value = mock_rows
            mock_table.search.return_value = mock_search
            
            # Load validation data
            result = load_validation_data(mock_table, logger)
            
            # Verify all records were loaded
            assert len(result) == count, \
                f"Failed for {description}: expected {count}, got {len(result)}"
            
            # Verify limit was called (the fix)
            mock_search.limit.assert_called_once_with(999999)
    
    def test_load_validation_data_handles_errors(self):
        """Test that load_validation_data handles errors gracefully."""
        logger = Mock()
        
        # Test with table that raises exception
        mock_table = Mock()
        mock_table.search.side_effect = Exception("Database error")
        
        result = load_validation_data(mock_table, logger)
        
        # Should return empty dict on error
        assert result == {}
        logger.warning.assert_called()
    
    def test_load_validation_data_skips_invalid_rows(self):
        """Test that invalid rows are skipped."""
        logger = Mock()
        mock_table = Mock()
        
        # Mix of valid and invalid rows
        mock_rows = [
            {"id": 1, "hash": "h1", "text": "t1", "embedding": [], "name": "E1", "data": "{}"},
            {"id": None, "hash": "h2"},  # Missing ID
            {"id": 3, "hash": "h3", "text": "t3", "embedding": [], "name": "E3", "data": "{}"},
        ]
        
        mock_search = Mock()
        mock_search.limit.return_value.to_list.return_value = mock_rows
        mock_table.search.return_value = mock_search
        
        result = load_validation_data(mock_table, logger)
        
        # Should skip row with None ID
        assert len(result) == 2
        assert 1 in result
        assert 3 in result


class TestValidationHelpers:
    """Test validation helper functions."""
    
    def test_detect_keyword_completeness(self):
        """Test keyword detection logic."""
        # Basic JSON without keywords
        text1 = '{"name": "Light", "model": "Switch"}'
        assert detect_keyword_completeness(text1, "Light") == False
        
        # Text with semantic keywords
        text2 = '{"name": "Light"} dimmer lighting automation control smart'
        assert detect_keyword_completeness(text2, "Light") == True
        
        # Empty text
        assert detect_keyword_completeness("", "Device") == False
        assert detect_keyword_completeness(None, "Device") == False
        
        # Non-JSON text with extra words
        text3 = "Device sensor temperature climate hvac monitoring automation"
        assert detect_keyword_completeness(text3, "Device") == True
    
    def test_validate_embedding(self):
        """Test embedding validation."""
        # Valid embedding
        valid = [0.1] * 1536
        assert validate_embedding(valid) == True
        
        # Wrong dimension
        wrong_dim = [0.1] * 100
        assert validate_embedding(wrong_dim) == False
        
        # Empty embedding
        assert validate_embedding([]) == False
        assert validate_embedding(None) == False
        
        # Contains NaN
        with_nan = [0.1] * 1535 + [float('nan')]
        assert validate_embedding(with_nan) == False
        
        # Not a list
        assert validate_embedding("not a list") == False
    
    def test_validate_stored_data(self):
        """Test stored data validation."""
        # Valid JSON with ID
        valid = '{"id": 123, "name": "Device"}'
        assert validate_stored_data(valid) == True
        
        # Valid but no ID
        no_id = '{"name": "Device"}'
        assert validate_stored_data(no_id) == False
        
        # Invalid JSON
        assert validate_stored_data("not json") == False
        assert validate_stored_data("") == False
        assert validate_stored_data(None) == False
        
        # JSON array instead of object
        assert validate_stored_data('[1, 2, 3]') == False


class TestComprehensiveValidation:
    """Test the comprehensive validation function."""
    
    def test_perform_comprehensive_validation_all_valid(self):
        """Test validation when all entities are valid."""
        # Current entities
        current = [
            {"id": 1, "name": "Device1", "model": "M1"},
            {"id": 2, "name": "Device2", "model": "M2"},
        ]
        
        # Stored validation data (matching)
        def mock_hash(entity, entity_type):
            return f"hash_{entity['id']}"
        
        validation_data = {
            1: {
                "hash": "hash_1",
                "text": "text with keywords lighting automation control",  # Need keywords
                "embedding": [0.1] * 1536,
                "name": "Device1",
                "data": '{"id": 1}'
            },
            2: {
                "hash": "hash_2",
                "text": "text with keywords lighting dimmer smart",  # Need keywords
                "embedding": [0.1] * 1536,
                "name": "Device2",
                "data": '{"id": 2}'
            }
        }
        
        result = perform_comprehensive_validation(
            current, validation_data, "devices", mock_hash
        )
        
        assert result.valid_count == 2
        assert not result.has_issues()
    
    def test_perform_comprehensive_validation_with_missing(self):
        """Test validation with missing records."""
        current = [
            {"id": 1, "name": "Device1"},
            {"id": 2, "name": "Device2"},
            {"id": 3, "name": "Device3"},  # Not in store
        ]
        
        validation_data = {
            1: {"hash": "h1", "text": "t1", "embedding": [0.1] * 1536, 
                "name": "Device1", "data": '{"id": 1}'},
            2: {"hash": "h2", "text": "t2", "embedding": [0.1] * 1536,
                "name": "Device2", "data": '{"id": 2}'},
        }
        
        def mock_hash(entity, entity_type):
            return f"h{entity['id']}"
        
        result = perform_comprehensive_validation(
            current, validation_data, "devices", mock_hash
        )
        
        # Should detect missing record
        missing_issues = result.get_issues_by_type(ValidationIssueType.MISSING_RECORD)
        assert len(missing_issues) == 1
        assert missing_issues[0].entity_id == 3
    
    def test_perform_comprehensive_validation_with_changes(self):
        """Test validation with changed entities."""
        current = [
            {"id": 1, "name": "Updated Device", "model": "NewModel"},
        ]
        
        validation_data = {
            1: {"hash": "old_hash", "text": "t1", "embedding": [0.1] * 1536,
                "name": "Old Device", "data": '{"id": 1}'},
        }
        
        def mock_hash(entity, entity_type):
            return "new_hash"  # Different from stored
        
        result = perform_comprehensive_validation(
            current, validation_data, "devices", mock_hash
        )
        
        # Should detect hash mismatch
        hash_issues = result.get_issues_by_type(ValidationIssueType.HASH_MISMATCH)
        assert len(hash_issues) == 1
    
    def test_perform_comprehensive_validation_orphaned_records(self):
        """Test detection of orphaned records."""
        current = [
            {"id": 1, "name": "Device1"},
        ]
        
        validation_data = {
            1: {"hash": "h1", "text": "t1", "embedding": [0.1] * 1536,
                "name": "Device1", "data": '{"id": 1}'},
            999: {"hash": "h999", "text": "t999", "embedding": [0.1] * 1536,
                  "name": "Deleted Device", "data": '{"id": 999}'},  # Orphaned
        }
        
        def mock_hash(entity, entity_type):
            return f"h{entity['id']}"
        
        result = perform_comprehensive_validation(
            current, validation_data, "devices", mock_hash
        )
        
        # Should detect orphaned record
        orphaned_issues = result.get_issues_by_type(ValidationIssueType.MISSING_RECORD)
        orphaned_ids = [issue.entity_id for issue in orphaned_issues]
        assert 999 in orphaned_ids


class TestPrioritization:
    """Test update prioritization logic."""
    
    def test_prioritize_updates(self):
        """Test that updates are correctly prioritized."""
        result = ValidationResult()
        
        # Add various issue types
        result.add_issue(1, ValidationIssueType.MISSING_RECORD, "Missing")
        result.add_issue(2, ValidationIssueType.INVALID_EMBEDDING, "Bad embed")
        result.add_issue(3, ValidationIssueType.CORRUPTED_DATA, "Corrupt")
        result.add_issue(4, ValidationIssueType.HASH_MISMATCH, "Changed")
        result.add_issue(5, ValidationIssueType.MISSING_KEYWORDS, "No keywords")
        
        priorities = prioritize_updates(result)
        
        # Critical issues (prevent search)
        assert 1 in priorities["critical"]  # Missing record
        assert 2 in priorities["critical"]  # Invalid embedding
        assert 3 in priorities["critical"]  # Corrupted data
        
        # High priority (affects accuracy)
        assert 4 in priorities["high"]  # Hash mismatch
        
        # Medium priority (affects quality)
        assert 5 in priorities["medium"]  # Missing keywords
        
        # No overlap between priority levels
        critical = set(priorities["critical"])
        high = set(priorities["high"])
        medium = set(priorities["medium"])
        assert not (critical & high)
        assert not (critical & medium)
        assert not (high & medium)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])