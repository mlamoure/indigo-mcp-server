#!/usr/bin/env python3
"""
Test the search functionality changes without importing the full vector store.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'MCP Server.indigoPlugin/Contents/Server Plugin'))

def test_query_parser_changes():
    """Test that query parser has updated defaults."""
    try:
        from mcp_server.tools.search_entities.query_parser import QueryParser
        
        parser = QueryParser()
        
        # Test default parameters
        result = parser.parse("test query")
        
        print("✓ QueryParser imports successfully")
        print(f"Default threshold: {result['threshold']} (should be 0.15)")
        print(f"Default top_k: {result['top_k']} (should be 1000)")
        
        assert result['threshold'] == 0.15, f"Expected 0.15, got {result['threshold']}"
        assert result['top_k'] == 1000, f"Expected 1000, got {result['top_k']}"
        
        print("✓ Query parser defaults are correct")
        return True
        
    except Exception as e:
        print(f"✗ QueryParser test failed: {e}")
        return False

def test_result_formatter_changes():
    """Test that result formatter returns all device properties."""
    try:
        from mcp_server.tools.search_entities.result_formatter import ResultFormatter
        
        formatter = ResultFormatter()
        
        # Test device with multiple properties
        test_device = {
            "id": 123,
            "name": "Test Device",
            "type": "dimmer",
            "model": "Test Model",
            "address": "1.2.3.4",
            "enabled": True,
            "brightness": 75,
            "onState": True,
            "protocol": "Test Protocol",
            "batteryLevel": 85,
            "_internal_field": "should be filtered"
        }
        
        formatted_fields = formatter._format_device_fields(test_device)
        
        print("✓ ResultFormatter imports successfully")
        print(f"Formatted fields: {list(formatted_fields.keys())}")
        
        # Should include all non-internal fields
        expected_fields = {"id", "name", "type", "model", "address", "enabled", 
                          "brightness", "onState", "protocol", "batteryLevel"}
        actual_fields = set(formatted_fields.keys())
        
        assert expected_fields.issubset(actual_fields), f"Missing fields: {expected_fields - actual_fields}"
        assert "_internal_field" not in actual_fields, "Internal field should be filtered out"
        
        print("✓ Result formatter includes all device properties")
        return True
        
    except Exception as e:
        print(f"✗ ResultFormatter test failed: {e}")
        return False

def test_syntax_validation():
    """Test that all modified files have valid Python syntax."""
    files_to_check = [
        "MCP Server.indigoPlugin/Contents/Server Plugin/mcp_server/tools/search_entities/query_parser.py",
        "MCP Server.indigoPlugin/Contents/Server Plugin/mcp_server/tools/search_entities/result_formatter.py",
        "MCP Server.indigoPlugin/Contents/Server Plugin/mcp_server/common/vector_store/main.py"
    ]
    
    import ast
    
    for file_path in files_to_check:
        try:
            with open(file_path, 'r') as f:
                content = f.read()
            
            ast.parse(content)
            print(f"✓ {file_path} has valid syntax")
            
        except SyntaxError as e:
            print(f"✗ Syntax error in {file_path}: {e}")
            return False
        except Exception as e:
            print(f"✗ Error checking {file_path}: {e}")
            return False
    
    return True

def main():
    """Run all tests."""
    print("Testing search functionality changes...")
    print("=" * 50)
    
    tests = [
        test_syntax_validation,
        test_query_parser_changes,
        test_result_formatter_changes,
    ]
    
    passed = 0
    for test in tests:
        try:
            if test():
                passed += 1
            print()
        except Exception as e:
            print(f"✗ Test {test.__name__} failed with exception: {e}")
            print()
    
    print(f"Results: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("🎉 All tests passed!")
        return True
    else:
        print("❌ Some tests failed")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)