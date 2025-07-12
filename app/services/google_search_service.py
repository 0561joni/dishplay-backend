# app/services/google_search_service.py
import httpx
import logging
import os
from typing import List, Optional, Dict
import asyncio
from urllib.parse import quote

logger = logging.getLogger(__name__)

GOOGLE_CSE_API_KEY = os.getenv("GOOGLE_CSE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
GOOGLE_SEARCH_URL = "https://www.googleapis.com/customsearch/v1"

async def search_images_for_item(query: str, limit: int = 2) -> List[str]:
    """Search for images using Google Custom Search API"""
    
    if not GOOGLE_CSE_API_KEY or not GOOGLE_CSE_ID:
        logger.error("Google CSE credentials not configured")
        return []
    
    try:
        async with httpx.AsyncClient() as client:
            params = {
                "key": GOOGLE_CSE_API_KEY,
                "cx": GOOGLE_CSE_ID,
                "q": query,
                "searchType": "image",
                "num": min(limit, 10),  # Google CSE allows max 10 results per request
                "safe": "active",
                "imgType": "photo",
                "imgSize": "large"
            }
            
            logger.info(f"Searching images for: {query}")
            
            response = await client.get(GOOGLE_SEARCH_URL, params=params, timeout=10.0)
            
            if response.status_code != 200:
                logger.error(f"Google CSE API error: {response.status_code} - {response.text}")
                return []
            
            data = response.json()
            
            # Extract image URLs
            image_urls = []
            items = data.get("items", [])
            
            for item in items[:limit]:
                # Try to get the direct image link
                image_url = item.get("link")
                
                # Validate image URL
                if image_url and is_valid_image_url(image_url):
                    image_urls.append(image_url)
                
                # Stop when we have enough images
                if len(image_urls) >= limit:
                    break
            
            logger.info(f"Found {len(image_urls)} images for query: {query}")
            return image_urls
            
    except httpx.TimeoutException:
        logger.error(f"Timeout searching images for: {query}")
        return []
    except Exception as e:
        logger.error(f"Error searching images for '{query}': {str(e)}")
        return []

def is_valid_image_url(url: str) -> bool:
    """Validate if URL is likely a valid image URL"""
    if not url or not url.startswith(("http://", "https://")):
        return False
    
    # Check for common image extensions
    image_extensions = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")
    url_lower = url.lower()
    
    # Check if URL ends with image extension
    if any(url_lower.endswith(ext) for ext in image_extensions):
        return True
    
    # Check if URL contains image extension before query parameters
    for ext in image_extensions:
        if ext in url_lower.split("?")[0]:
            return True
    
    # Allow URLs from known image hosting services
    known_hosts = ["googleusercontent.com", "gstatic.com", "imgur.com", "cloudinary.com"]
    if any(host in url_lower for host in known_hosts):
        return True
    
    return True  # Be permissive for now

async def search_images_batch(items: List[Dict[str, str]], limit_per_item: int = 2) -> Dict[str, List[str]]:
    """Search images for multiple items concurrently"""
    
    async def search_with_id(item_id: str, query: str):
        images = await search_images_for_item(query, limit_per_item)
        return (item_id, images)
    
    tasks = []
    for item in items:
        query = f"{item['name']} food"
        if item.get('description'):
            query += f" {item['description'][:30]}"
        
        tasks.append(search_with_id(item['id'], query))
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    image_map = {}
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Error in batch image search: {result}")
            continue
        
        item_id, images = result
        image_map[item_id] = images
    
    return image_map
