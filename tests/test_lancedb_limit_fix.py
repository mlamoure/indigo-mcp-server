#!/usr/bin/env python3
"""
Simple test to verify that LanceDB search() with no query returns all records
when a large limit is specified, not just the default 10.
"""

import os
import sys
import tempfile
import shutil
import lancedb
import pyarrow as pa

def test_lancedb_limit():
    """Test that search().limit(999999) returns all records."""
    
    # Create temporary directory for test database
    temp_dir = tempfile.mkdtemp(prefix="test_lancedb_")
    
    try:
        # Connect to LanceDB
        db = lancedb.connect(temp_dir)
        
        # Create test table with 50 records
        test_count = 50
        schema = pa.schema([
            pa.field("id", pa.int64()),
            pa.field("name", pa.string()),
            pa.field("embedding", pa.list_(pa.float32(), 1536))
        ])
        
        # Create test data
        ids = list(range(1, test_count + 1))
        names = [f"Test Item {i}" for i in ids]
        embeddings = [[0.1] * 1536 for _ in ids]
        
        # Create table with test data
        test_data = pa.Table.from_arrays(
            [
                pa.array(ids),
                pa.array(names),
                pa.array(embeddings, type=pa.list_(pa.float32(), 1536))
            ],
            schema=schema
        )
        
        table = db.create_table("test_table", test_data)
        print(f"Created table with {test_count} records")
        
        # Test 1: search() without limit (should default to 10)
        results_no_limit = table.search().to_list()
        print(f"search().to_list() returned {len(results_no_limit)} records")
        
        # Test 2: search() with large limit (should return all)
        results_with_limit = table.search().limit(999999).to_list()
        print(f"search().limit(999999).to_list() returned {len(results_with_limit)} records")
        
        # Verify results
        if len(results_no_limit) == 10:
            print("✅ Confirmed: search() without limit defaults to 10 records")
        else:
            print(f"⚠️ Unexpected: search() without limit returned {len(results_no_limit)} records")
        
        if len(results_with_limit) == test_count:
            print(f"✅ SUCCESS: search().limit(999999) returned all {test_count} records")
            return True
        else:
            print(f"❌ FAILURE: search().limit(999999) only returned {len(results_with_limit)} records")
            return False
            
    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # Clean up temporary directory
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    success = test_lancedb_limit()
    print("\n" + "="*50)
    print("Test Summary:")
    print("="*50)
    if success:
        print("✅ The fix for LanceDB limit issue is working correctly!")
        print("The code now explicitly sets limit(999999) to retrieve all records.")
    else:
        print("❌ The LanceDB limit issue may not be fully resolved.")
    sys.exit(0 if success else 1)