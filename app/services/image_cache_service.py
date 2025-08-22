# app/services/image_cache_service.py
import aiohttp
import asyncio
import hashlib
import logging
from typing import List, Optional, Dict, Tuple
from io import BytesIO
from PIL import Image
from datetime import datetime
import re

from app.core.async_supabase import async_supabase_client

logger = logging.getLogger(__name__)

# Supabase Storage bucket for cached images
CACHE_BUCKET = "menu-images-cache"


def normalize_item_name(name: str) -> str:
    """Normalize menu item name for matching similar items"""
    # Convert to lowercase and remove special characters
    normalized = name.lower().strip()
    # Remove common variations
    normalized = re.sub(r'[^\w\s]', '', normalized)
    # Remove extra spaces
    normalized = re.sub(r'\s+', ' ', normalized)
    # Remove common suffixes/prefixes that don't affect the dish
    remove_words = ['large', 'small', 'medium', 'xl', 'mini', 'jumbo', 'special', 'deluxe', 'premium']
    words = normalized.split()
    words = [w for w in words if w not in remove_words]
    return ' '.join(words)


def get_item_category(name: str) -> str:
    """Determine food category for better matching"""
    name_lower = name.lower()
    
    categories = {
        'pizza': ['pizza', 'margherita', 'pepperoni', 'hawaiian'],
        'burger': ['burger', 'cheeseburger', 'hamburger', 'patty'],
        'pasta': ['pasta', 'spaghetti', 'penne', 'lasagna', 'ravioli', 'fettuccine'],
        'salad': ['salad', 'caesar', 'greek', 'garden'],
        'sandwich': ['sandwich', 'sub', 'hoagie', 'panini', 'wrap'],
        'chicken': ['chicken', 'wings', 'nuggets', 'tenders'],
        'seafood': ['fish', 'salmon', 'tuna', 'shrimp', 'lobster', 'crab'],
        'soup': ['soup', 'chowder', 'bisque', 'broth'],
        'dessert': ['cake', 'pie', 'ice cream', 'brownie', 'cookie', 'pudding', 'tiramisu'],
        'steak': ['steak', 'ribeye', 'sirloin', 'filet'],
        'asian': ['sushi', 'ramen', 'pho', 'pad thai', 'curry', 'stir fry'],
        'mexican': ['taco', 'burrito', 'quesadilla', 'enchilada', 'fajita']
    }
    
    for category, keywords in categories.items():
        if any(keyword in name_lower for keyword in keywords):
            return category
    
    return 'general'


async def search_cached_images(item_name: str, item_description: str = None, limit: int = 3) -> List[str]:
    """
    Search for cached images in Supabase that match the menu item
    Returns list of Supabase Storage URLs
    """
    try:
        normalized_name = normalize_item_name(item_name)
        category = get_item_category(item_name)
        
        # First try exact normalized name match
        query = await async_supabase_client.table_select(
            "cached_food_images",
            "*",
            filters={
                "normalized_name": ("eq", normalized_name),
                "is_active": ("eq", True)
            },
            limit=limit
        )
        
        if query and len(query) >= limit:
            logger.info(f"Found exact match for '{item_name}' in cache")
            return [item['storage_url'] for item in query[:limit]]
        
        existing_urls = [item['storage_url'] for item in query] if query else []
        
        # If not enough, try category match with similar names
        remaining = limit - len(existing_urls)
        if remaining > 0 and category != 'general':
            # Search for items in same category
            category_query = await async_supabase_client.table_select(
                "cached_food_images",
                "*",
                filters={
                    "category": ("eq", category),
                    "is_active": ("eq", True)
                },
                limit=remaining * 3  # Get more to filter
            )
            
            if category_query:
                # Score matches based on name similarity
                scored_matches = []
                for item in category_query:
                    if item['storage_url'] in existing_urls:
                        continue
                    
                    # Calculate similarity score
                    item_words = set(item['normalized_name'].split())
                    search_words = set(normalized_name.split())
                    
                    # Jaccard similarity
                    intersection = item_words.intersection(search_words)
                    union = item_words.union(search_words)
                    similarity = len(intersection) / len(union) if union else 0
                    
                    if similarity > 0.3:  # Threshold for similarity
                        scored_matches.append((similarity, item['storage_url']))
                
                # Sort by similarity and take best matches
                scored_matches.sort(reverse=True)
                for _, url in scored_matches[:remaining]:
                    existing_urls.append(url)
                
                if len(existing_urls) > len(query if query else []):
                    logger.info(f"Found {len(existing_urls)} similar images for '{item_name}' in category '{category}'")
        
        return existing_urls
        
    except Exception as e:
        logger.error(f"Error searching cached images: {str(e)}")
        return []


async def download_and_store_image(image_url: str, item_name: str, 
                                  item_description: str = None) -> Optional[str]:
    """
    Download image from URL and store in Supabase Storage
    Returns the permanent Supabase Storage URL
    """
    try:
        # Download image
        async with aiohttp.ClientSession() as session:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            async with session.get(image_url, headers=headers, timeout=10) as response:
                if response.status != 200:
                    logger.error(f"Failed to download image: {response.status}")
                    return None
                
                image_data = await response.read()
        
        # Validate and optimize image
        try:
            img = Image.open(BytesIO(image_data))
            
            # Convert RGBA to RGB if needed
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            
            # Resize if too large (max 1920px width)
            if img.width > 1920:
                ratio = 1920 / img.width
                new_height = int(img.height * ratio)
                img = img.resize((1920, new_height), Image.Resampling.LANCZOS)
            
            # Save optimized image
            output = BytesIO()
            img.save(output, format='JPEG', quality=85, optimize=True)
            optimized_data = output.getvalue()
            
        except Exception as e:
            logger.error(f"Error processing image: {str(e)}")
            optimized_data = image_data  # Use original if processing fails
        
        # Generate unique filename
        content_hash = hashlib.md5(optimized_data).hexdigest()[:12]
        normalized_name = normalize_item_name(item_name)
        safe_name = re.sub(r'[^\w\s-]', '', normalized_name).replace(' ', '-')[:30]
        filename = f"{safe_name}_{content_hash}.jpg"
        
        # Upload to Supabase Storage
        storage_path = f"cached/{get_item_category(item_name)}/{filename}"
        
        result = await async_supabase_client.storage_upload(
            CACHE_BUCKET,
            storage_path,
            optimized_data,
            {
                "content-type": "image/jpeg",
                "cache-control": "public, max-age=31536000"  # Cache for 1 year
            }
        )
        
        if not result:
            logger.error("Failed to upload image to Supabase Storage")
            return None
        
        # Get public URL
        storage_url = await async_supabase_client.storage_get_public_url(
            CACHE_BUCKET,
            storage_path
        )
        
        # Store metadata in database
        await async_supabase_client.table_insert("cached_food_images", {
            "storage_path": storage_path,
            "storage_url": storage_url,
            "original_url": image_url,
            "item_name": item_name,
            "normalized_name": normalized_name,
            "category": get_item_category(item_name),
            "description": item_description,
            "file_size": len(optimized_data),
            "image_width": img.width,
            "image_height": img.height,
            "created_at": datetime.utcnow().isoformat(),
            "is_active": True
        })
        
        logger.info(f"Successfully cached image for '{item_name}' at {storage_path}")
        return storage_url
        
    except Exception as e:
        logger.error(f"Error downloading and storing image: {str(e)}")
        return None


async def cache_images_batch(images_with_items: List[Tuple[str, str, str]]) -> Dict[str, str]:
    """
    Cache multiple images in parallel
    Input: List of (image_url, item_name, item_description)
    Returns: Dict mapping original URLs to Supabase Storage URLs
    """
    tasks = []
    for image_url, item_name, item_description in images_with_items:
        tasks.append(download_and_store_image(image_url, item_name, item_description))
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    url_mapping = {}
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Error caching image: {result}")
            continue
        
        if result:  # Successfully cached
            original_url = images_with_items[i][0]
            url_mapping[original_url] = result
    
    return url_mapping