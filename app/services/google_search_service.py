# app/services/google_search_service.py
import httpx
import logging
import os
import re
from typing import List, Optional, Dict
import asyncio
from urllib.parse import quote

logger = logging.getLogger(__name__)

GOOGLE_CSE_API_KEY = os.getenv("GOOGLE_CSE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
GOOGLE_SEARCH_URL = "https://www.googleapis.com/customsearch/v1"

# Allowed image hosting sites for food photos
ALLOWED_SITES = [
    "pixabay.com",
    "unsplash.com", 
    "pexels.com",
    "burst.shopify.com",
    "freefoodphotos.com",
    "stocksnap.io",
    "foodiesfeed.com",
    "picjumbo.com",
    "kaboompics.com",
    "gratisography.com"
]

def extract_first_sentence(text: str) -> str:
    """Extract the first sentence from a text description"""
    if not text or not text.strip():
        return ""
    
    # Clean up the text
    text = text.strip()
    
    # Split by common sentence endings
    sentence_endings = r'[.!?](?:\s|$)'
    sentences = re.split(sentence_endings, text)
    
    if sentences and sentences[0]:
        first_sentence = sentences[0].strip()
        # Limit length to avoid overly long queries (max 100 chars)
        if len(first_sentence) > 100:
            first_sentence = first_sentence[:100].rsplit(' ', 1)[0]  # Break at word boundary
        return first_sentence
    
    # Fallback to first 50 characters if no sentence structure found
    return text[:50].rsplit(' ', 1)[0] if len(text) > 50 else text

async def search_images_for_item(query: str, limit: int = 2) -> List[str]:
    """Search for images using Google Custom Search API"""
    
    if not GOOGLE_CSE_API_KEY or not GOOGLE_CSE_ID:
        logger.error("Google CSE credentials not configured")
        return []
    
    try:
        async with httpx.AsyncClient() as client:
            # Create site restriction query
            site_restrictions = " OR ".join([f"site:{site}" for site in ALLOWED_SITES])
            restricted_query = f"{query} ({site_restrictions})"
            
            params = {
                "key": GOOGLE_CSE_API_KEY,
                "cx": GOOGLE_CSE_ID,
                "q": restricted_query,
                "searchType": "image",
                "num": min(limit, 10),  # Google CSE allows max 10 results per request
                "safe": "active",
                "imgType": "photo",
                "imgSize": "large"
            }
            
            logger.info(f"Searching images for: {query}")
            logger.debug(f"Site-restricted query: {restricted_query}")
            
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
            
            # Log statistics about which sites were used
            if image_urls:
                site_counts = {}
                for url in image_urls:
                    for site in ALLOWED_SITES:
                        if site in url.lower():
                            site_counts[site] = site_counts.get(site, 0) + 1
                            break
                
                if site_counts:
                    logger.info(f"Found {len(image_urls)} images for '{query}' from sites: {site_counts}")
                else:
                    logger.info(f"Found {len(image_urls)} images for '{query}' (from CDNs)")
            else:
                logger.warning(f"No valid images found for query: {query}")
            
            return image_urls
            
    except httpx.TimeoutException:
        logger.error(f"Timeout searching images for: {query}")
        return []
    except Exception as e:
        logger.error(f"Error searching images for '{query}': {str(e)}")
        return []

def is_valid_image_url(url: str) -> bool:
    """Validate if URL is from allowed sites and is likely a valid image URL"""
    if not url or not url.startswith(("http://", "https://")):
        return False
    
    url_lower = url.lower()
    
    # First check if the URL is from one of our allowed sites
    is_from_allowed_site = any(allowed_site in url_lower for allowed_site in ALLOWED_SITES)
    
    if not is_from_allowed_site:
        # Also allow CDN URLs that might serve images for our allowed sites
        allowed_cdns = [
            "googleusercontent.com",  # Google's CDN
            "gstatic.com",           # Google's static content CDN
            "cloudinary.com",        # Cloudinary CDN
            "fastly.com",           # Fastly CDN
            "jsdelivr.net",         # jsDelivr CDN
            "amazonaws.com",        # AWS S3/CloudFront
            "cloudflare.com"        # Cloudflare CDN
        ]
        
        is_from_allowed_site = any(cdn in url_lower for cdn in allowed_cdns)
    
    if not is_from_allowed_site:
        logger.debug(f"Rejected URL from unauthorized site: {url}")
        return False
    
    # Check for common image extensions
    image_extensions = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")
    
    # Check if URL ends with image extension
    if any(url_lower.endswith(ext) for ext in image_extensions):
        return True
    
    # Check if URL contains image extension before query parameters
    for ext in image_extensions:
        if ext in url_lower.split("?")[0]:
            return True
    
    # For URLs from allowed sites, be more permissive about extensions
    # as they might use custom URL structures
    return True

async def search_images_batch(items: List[Dict[str, str]], limit_per_item: int = 2) -> Dict[str, List[str]]:
    """Search images for multiple items concurrently"""
    
    async def search_with_id(item_id: str, queries: List[str]):
        all_images = []
        images_per_query = max(1, limit_per_item // len(queries))  # Distribute limit across queries
        
        for query in queries:
            images = await search_images_for_item(query, images_per_query)
            all_images.extend(images)
            
            # Stop if we have enough images
            if len(all_images) >= limit_per_item:
                all_images = all_images[:limit_per_item]
                break
        
        return (item_id, all_images)
    
    tasks = []
    for item in items:
        # Create two different search queries for better variety
        base_name = item['name']
        
        # First query: "item name plated dish"
        query1 = f"{base_name} plated dish"
        
        # Second query: "item name food photography" with description
        query2 = f"{base_name} food photography"
        if item.get('description'):
            first_sentence = extract_first_sentence(item['description'])
            if first_sentence:
                query2 += f" {first_sentence}"
        
        queries = [query1, query2]
        tasks.append(search_with_id(item['id'], queries))
        
        logger.debug(f"Search queries for '{base_name}': {queries}")
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    image_map = {}
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Error in batch image search: {result}")
            continue
        
        item_id, images = result
        image_map[item_id] = images
    
    return image_map
