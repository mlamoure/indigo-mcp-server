#!/usr/bin/env python3
"""
Test to demonstrate why the LanceDB limit bug wasn't caught.
With exactly 10 items, the bug is invisible because the default limit is 10.
"""

import os
import sys
import tempfile
import shutil
import lancedb
import pyarrow as pa

def test_vector_store_with_10_items():
    """Test that shows the bug is invisible with exactly 10 items."""
    
    # Create temporary directory for test database
    temp_dir = tempfile.mkdtemp(prefix="test_lancedb_10_")
    
    try:
        # Connect to LanceDB
        db = lancedb.connect(temp_dir)
        
        # Create test table with EXACTLY 10 records (the default limit)
        test_count = 10
        schema = pa.schema([
            pa.field("id", pa.int64()),
            pa.field("name", pa.string()),
            pa.field("hash", pa.string()),
            pa.field("embedding", pa.list_(pa.float32(), 1536))
        ])
        
        # Create test data
        ids = list(range(1, test_count + 1))
        names = [f"Test Item {i}" for i in ids]
        hashes = [f"hash_{i}" for i in ids]
        embeddings = [[0.1] * 1536 for _ in ids]
        
        # Create table with test data
        test_data = pa.Table.from_arrays(
            [
                pa.array(ids),
                pa.array(names),
                pa.array(hashes),
                pa.array(embeddings, type=pa.list_(pa.float32(), 1536))
            ],
            schema=schema
        )
        
        table = db.create_table("test_table", test_data)
        print(f"✅ Created table with {test_count} records")
        
        # Simulate what the validation code does (the buggy version)
        print("\n--- Simulating BUGGY validation code ---")
        buggy_rows = table.search().to_list()  # No limit specified
        print(f"Buggy code: table.search().to_list() returned {len(buggy_rows)} records")
        
        # Check if all IDs are found
        buggy_ids = {row['id'] for row in buggy_rows}
        missing_ids = set(ids) - buggy_ids
        
        if missing_ids:
            print(f"❌ PROBLEM DETECTED: Missing IDs: {missing_ids}")
            print("   The validation would think these records need regeneration!")
        else:
            print(f"✅ NO PROBLEM DETECTED: All {test_count} IDs found")
            print("   The bug is INVISIBLE with exactly 10 items!")
        
        # Now show what the fixed code does
        print("\n--- Simulating FIXED validation code ---")
        fixed_rows = table.search().limit(999999).to_list()
        print(f"Fixed code: table.search().limit(999999).to_list() returned {len(fixed_rows)} records")
        
        fixed_ids = {row['id'] for row in fixed_rows}
        missing_ids_fixed = set(ids) - fixed_ids
        
        if missing_ids_fixed:
            print(f"❌ Missing IDs: {missing_ids_fixed}")
        else:
            print(f"✅ All {test_count} IDs found")
        
        # Test with 11 items to show when the bug appears
        print("\n" + "="*60)
        print("NOW TESTING WITH 11 ITEMS (ONE MORE THAN DEFAULT LIMIT)")
        print("="*60)
        
        # Add one more record
        new_record = pa.Table.from_arrays(
            [
                pa.array([11]),
                pa.array(["Test Item 11"]),
                pa.array(["hash_11"]),
                pa.array([[0.1] * 1536], type=pa.list_(pa.float32(), 1536))
            ],
            schema=schema
        )
        table.add(new_record)
        
        # Test buggy version with 11 items
        buggy_rows_11 = table.search().to_list()
        print(f"\nBuggy code with 11 items: returned {len(buggy_rows_11)} records")
        
        buggy_ids_11 = {row['id'] for row in buggy_rows_11}
        all_ids_11 = set(range(1, 12))
        missing_ids_11 = all_ids_11 - buggy_ids_11
        
        if missing_ids_11:
            print(f"❌ BUG EXPOSED: Missing ID {missing_ids_11}")
            print("   The 11th record would trigger unnecessary regeneration!")
        else:
            print(f"✅ All 11 IDs found (unexpected)")
        
        # Test fixed version with 11 items  
        fixed_rows_11 = table.search().limit(999999).to_list()
        print(f"\nFixed code with 11 items: returned {len(fixed_rows_11)} records")
        
        fixed_ids_11 = {row['id'] for row in fixed_rows_11}
        missing_ids_fixed_11 = all_ids_11 - fixed_ids_11
        
        if missing_ids_fixed_11:
            print(f"❌ Missing IDs: {missing_ids_fixed_11}")
        else:
            print(f"✅ All 11 IDs found correctly")
        
        return True
            
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
    print("DEMONSTRATION: Why the LanceDB limit bug wasn't caught")
    print("========================================================\n")
    
    success = test_vector_store_with_10_items()
    
    print("\n" + "="*60)
    print("CONCLUSION:")
    print("="*60)
    print("📌 With exactly 10 items, the bug is INVISIBLE")
    print("📌 With 11+ items, the bug causes data loss") 
    print("📌 Most tests probably used small datasets (<= 10 items)")
    print("📌 This is why comprehensive testing with various data sizes is critical!")
    
    sys.exit(0 if success else 1)