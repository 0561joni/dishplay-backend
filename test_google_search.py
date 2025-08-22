#!/usr/bin/env python3
"""
Test script for Google CSE image search integration
"""
import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set the Google API credentials from your test file
os.environ["GOOGLE_CSE_API_KEY"] = "AIzaSyDswDhLoXmkJ6PusnVSWz2N19eoiT9WZgw"
os.environ["GOOGLE_CSE_ID"] = "c72204955425844de"

# Import after setting env vars
from app.services.google_search_service import search_images_for_item, search_images_batch

async def test_single_item():
    """Test searching for a single menu item"""
    print("\n=== Testing Single Item Search ===")
    
    test_items = [
        ("Margherita Pizza", "Fresh tomatoes, mozzarella, basil"),
        ("Caesar Salad", "Romaine lettuce, parmesan, croutons"),
        ("Grilled Salmon", "Atlantic salmon with lemon herbs"),
        ("Chocolate Cake", "Rich chocolate cake with vanilla ice cream")
    ]
    
    for name, description in test_items:
        print(f"\nSearching for: {name}")
        print(f"Description: {description}")
        
        images = await search_images_for_item(name, description, limit=2)
        
        if images:
            print(f"Found {len(images)} images:")
            for i, url in enumerate(images, 1):
                print(f"  {i}. {url[:100]}...")
        else:
            print("  No images found")

async def test_batch_search():
    """Test batch searching for multiple items"""
    print("\n=== Testing Batch Search ===")
    
    items = [
        {"id": "1", "name": "Beef Burger", "description": "Juicy beef patty with lettuce and tomato"},
        {"id": "2", "name": "Chicken Wings", "description": "Crispy fried chicken wings with buffalo sauce"},
        {"id": "3", "name": "Greek Salad", "description": "Fresh vegetables with feta cheese and olives"},
        {"id": "4", "name": "Tiramisu", "description": "Italian coffee-flavored dessert"}
    ]
    
    print(f"\nSearching for {len(items)} items in batch...")
    
    results = await search_images_batch(items, limit_per_item=2)
    
    for item in items:
        print(f"\n{item['name']}:")
        if item['id'] in results:
            images = results[item['id']]
            if images:
                print(f"  Found {len(images)} images")
                for i, (url, source) in enumerate(images, 1):
                    print(f"    {i}. Source: {source}, URL: {url[:80]}...")
            else:
                print("  No images found")
        else:
            print("  Error or no results")

async def main():
    """Run all tests"""
    print("Starting Google CSE Image Search Tests")
    print("=" * 50)
    
    await test_single_item()
    await test_batch_search()
    
    print("\n" + "=" * 50)
    print("Tests completed!")

if __name__ == "__main__":
    asyncio.run(main())