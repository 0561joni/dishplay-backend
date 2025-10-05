#!/usr/bin/env python3
"""
Quick test to fetch items from items_without_pictures table
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase_client

# Load environment
load_dotenv()

print("=" * 60)
print("Testing Supabase Connection")
print("=" * 60)

try:
    print("\n1. Getting Supabase client...")
    supabase = get_supabase_client()
    print("   ✓ Supabase client initialized")

    print("\n2. Fetching items from items_without_pictures...")
    response = supabase.table('items_without_pictures') \
        .select('id, title, description, processed') \
        .execute()

    print(f"   ✓ Query executed successfully")
    print(f"   Response type: {type(response)}")
    print(f"   Response.data type: {type(response.data)}")
    print(f"   Number of items: {len(response.data) if response.data else 0}")

    if response.data:
        print("\n3. Items found:")
        for i, item in enumerate(response.data, 1):
            processed_status = "✓" if item.get('processed') else "○"
            print(f"   {processed_status} {i}. [{item['id']}] {item['title']}")
            if item.get('description'):
                print(f"      Description: {item['description'][:60]}...")
    else:
        print("\n   ✗ No items found in the table")

    print("\n" + "=" * 60)
    print("Test completed successfully!")
    print("=" * 60)

except Exception as e:
    print(f"\n✗ ERROR: {str(e)}")
    import traceback
    traceback.print_exc()
