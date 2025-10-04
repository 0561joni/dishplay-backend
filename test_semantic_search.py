#!/usr/bin/env python3
"""Test semantic search functionality"""

import os
import sys
import asyncio
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_semantic_search():
    """Test semantic search with sample menu items"""

    # Check environment variables
    openai_key = os.getenv("OPENAI_API_KEY")
    supabase_url = os.getenv("SUPABASE_URL")

    print(f"OPENAI_API_KEY: {'[OK]' if openai_key else '[MISSING]'}")
    print(f"SUPABASE_URL: {'[OK]' if supabase_url else '[MISSING]'}")
    print()

    if not openai_key or not supabase_url:
        print("Missing environment variables - cannot test")
        return False

    try:
        from app.services.semantic_search_service import search_similar_dishes

        # Test items - common dishes that should have matches
        test_items = [
            {
                "name": "Margherita Pizza",
                "description": "Fresh tomatoes, mozzarella, basil"
            },
            {
                "name": "Caesar Salad",
                "description": "Romaine lettuce, parmesan, croutons"
            },
            {
                "name": "Grilled Salmon",
                "description": "Atlantic salmon with lemon herbs"
            },
            {
                "name": "Chocolate Cake",
                "description": "Rich chocolate cake with vanilla ice cream"
            }
        ]

        print("Testing semantic search for sample menu items...")
        print("=" * 80)

        for item in test_items:
            print(f"\nSearching for: {item['name']}")
            print(f"Description: {item['description']}")
            print("-" * 80)

            matches = await search_similar_dishes(
                query_name=item['name'],
                query_description=item['description'],
                top_k=3,
                threshold=0.7
            )

            if matches:
                print(f"Found {len(matches)} match(es):\n")
                for i, match in enumerate(matches, 1):
                    print(f"  {i}. {match['title']}")
                    print(f"     Similarity: {match['similarity']:.3f} ({match['similarity']*100:.1f}%)")
                    print(f"     Description: {match['description'][:100]}...")
                    print(f"     Image URL: {match['image_url']}")
                    print()
            else:
                print("  [NO MATCHES FOUND - will be logged to items_without_pictures]")
                print()

        print("=" * 80)
        print("\n[OK] Semantic search test completed successfully!")
        return True

    except Exception as e:
        print(f"[ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Semantic Search Test")
    print("=" * 80)
    print()

    success = asyncio.run(test_semantic_search())

    print()
    if success:
        print("[OK] All tests passed!")
    else:
        print("[FAILED] Tests failed!")
