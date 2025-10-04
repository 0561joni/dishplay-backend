#!/usr/bin/env python3
"""Check what's in the dish_embeddings database"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_database_contents():
    """Check database contents"""
    try:
        from app.core.supabase_client import get_supabase_client

        supabase = get_supabase_client()

        # Get total count
        response = supabase.table("dish_embeddings").select("title", count="exact").limit(1).execute()
        total = response.count
        print(f"Total dishes in database: {total}")
        print()

        # Search for common terms
        search_terms = ["salad", "salmon", "cake", "chocolate", "fish", "dessert"]

        for term in search_terms:
            response = supabase.table("dish_embeddings").select("title").ilike("title", f"%{term}%").limit(5).execute()
            if response.data:
                print(f"Dishes containing '{term}': ({len(response.data)} shown)")
                for item in response.data:
                    print(f"  - {item['title']}")
                print()
            else:
                print(f"No dishes found containing '{term}'")
                print()

        return True

    except Exception as e:
        print(f"[ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Database Contents Check")
    print("=" * 80)
    print()

    test_database_contents()
