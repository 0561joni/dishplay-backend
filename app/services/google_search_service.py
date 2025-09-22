# app/services/google_search_service.py
from googleapiclient.discovery import build
import os
import re
import logging
import asyncio
import aiohttp
from typing import List, Optional, Dict, Tuple, Set
from urllib.parse import urlparse
from io import BytesIO
from PIL import Image

from app.services.image_cache_service import (
    search_cached_images, 
    download_and_store_image,
    cache_images_batch
)

logger = logging.getLogger(__name__)

# Google API credentials from environment variables
GOOGLE_CSE_API_KEY = os.getenv("GOOGLE_CSE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")

# High-quality food sites for better image results
FOOD_DOMAINS = [
    "wolt.com",  # Food delivery platform with restaurant photos - prioritized
    "seriouseats.com", "bonappetit.com", "epicurious.com", "bbcgoodfood.com",
    "allrecipes.com", "foodnetwork.com", "tasteatlas.com", "justonecookbook.com",
    "thespruceeats.com", "foodgawker.com", "delish.com", "food52.com",
    "thekitchn.com", "simplyrecipes.com", "cookinglight.com", "eatingwell.com",
    "foodandwine.com", "saveur.com", "finecooking.com", "myrecipes.com",
    "ubereats.com", "doordash.com", "grubhub.com"  # Other delivery platforms
]

# User agent for fetching images
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# Terms to exclude for savory dishes
NEGATIVE_SWEET_TERMS = {
    "dessert", "tart", "pie", "cake", "brownie", "cookie", "pudding", 
    "fruit", "sweet", "mousse", "cheesecake", "galette", "cobbler", 
    "pastry", "cupcake", "donut", "muffin"
}

# Generic negative terms to avoid stock photos and non-food items
NEGATIVE_GENERIC_TERMS = {
    "logo", "vector", "illustration", "clipart", "packaging",
    "stock", "getty", "shutterstock", "alamy", "cartoon", "drawing",
    "menu", "text", "writing", "sign", "board", "blackboard",
    "face", "person", "people", "chef", "waiter", "customer",
    "restaurant interior", "kitchen", "dining room", "table setting",
    "cutlery", "napkin", "tablecloth", "candle", "flower", "vase",
    "book", "magazine", "flyer", "brochure", "poster", "advertisement",
    "watch", "wristwatch", "smartwatch", "chronograph", "bracelet", "strap",
    "clock", "timepiece", "jewelry", "jewelery", "necklace", "earring", "earrings",
    "handbag", "purse", "backpack", "wallet", "shoe", "sneaker", "boot",
    "clothing", "apparel", "outfit", "garment", "fashion", "runway",
    "phone", "smartphone", "tablet", "laptop", "computer", "keyboard"
}

# Terms that often indicate non-food product imagery
NEGATIVE_OBJECT_TERMS = {
    "watch", "wristwatch", "smartwatch", "chronograph", "bracelet", "strap",
    "clock", "timepiece", "jewelry", "jewelery", "necklace", "earring", "earrings",
    "handbag", "purse", "backpack", "wallet", "shoe", "sneaker", "boot",
    "clothing", "apparel", "outfit", "garment", "fashion", "runway",
    "phone", "smartphone", "tablet", "laptop", "computer", "keyboard"
}

def normalize_menu_item(raw_name: str) -> Tuple[str, List[str]]:
    """Normalize menu item name and extract modifiers for better search"""
    # Clean up the text
    s = raw_name.strip().lower().replace("_", " ").replace("-", " ")
    
    # Remove measurements and prices
    s = re.sub(r"\b\d+(?:\.\d+)?\s?(?:g|kg|oz|ml|l|cm|mm|in|inch|€|\$|£)\b", " ", s)
    s = re.sub(r"[(),/{}]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    
    tokens = s.split()
    
    # Identify core item (simplified logic)
    core = tokens[0] if tokens else "food"
    
    # Handle special cases
    if "burger" in tokens or "cheeseburger" in tokens or "hamburger" in tokens:
        if "cheese" in tokens or "cheeseburger" in tokens:
            core = "cheeseburger"
        elif "hamburger" in tokens:
            core = "hamburger"
        else:
            core = "burger"
    elif "pizza" in tokens:
        core = "pizza"
    elif "pasta" in tokens or "spaghetti" in tokens or "penne" in tokens:
        core = "pasta"
    elif "salad" in tokens:
        core = "salad"
    elif "soup" in tokens:
        core = "soup"
    elif "sandwich" in tokens:
        core = "sandwich"
    
    # Extract modifiers (descriptive words)
    stop_words = {core, "with", "and", "the", "a", "an", "of", "in", "on"}
    modifiers = [t for t in tokens if t not in stop_words]
    
    # Prioritize important food descriptors
    priority = {
        "beef": 3, "chicken": 3, "pork": 3, "fish": 3, "seafood": 3,
        "grilled": 2, "fried": 2, "baked": 2, "roasted": 2, "steamed": 2,
        "cheese": 2, "tomato": 1, "onion": 1, "lettuce": 1, "mushroom": 1
    }
    modifiers = sorted(modifiers, key=lambda t: priority.get(t, 0), reverse=True)[:3]
    
    return core, modifiers

def build_search_query(core: str, modifiers: List[str], description: str = None, 
                       add_context: bool = True, use_negatives: bool = True) -> str:
    """Build optimized search query for Google CSE"""
    parts = [core]
    
    # Add modifiers
    if modifiers:
        parts.extend(modifiers[:2])  # Limit to 2 modifiers to avoid over-specification
    
    # Add description keywords if available
    if description:
        # Extract key words from description
        desc_lower = description.lower()
        for word in ["grilled", "fried", "baked", "roasted", "fresh", "creamy", "spicy"]:
            if word in desc_lower and word not in parts:
                parts.append(word)
                break
    
    # Add context for better food photos
    if add_context:
        parts.extend(['"restaurant"', '"plated"', '"food photography"', 'dish'])
    
    # Add negative terms to exclude unwanted results
    if use_negatives:
        # Check if item is likely savory
        is_savory = not any(sweet in core for sweet in ["cake", "dessert", "ice cream", "chocolate", "cookie", "brownie"])

        if is_savory:
            # Exclude dessert terms for savory items
            for term in ["dessert", "cake", "sweet"]:
                parts.append(f'-{term}')

        # Priority negative terms - always exclude these
        priority_negatives = [
            "-menu", "-text", "-face", "-person", "-chef",
            "-logo", "-cartoon", "-illustration"
        ]

        negative_tokens = list(priority_negatives)
        for generic_term in sorted(NEGATIVE_GENERIC_TERMS.union(NEGATIVE_OBJECT_TERMS)):
            sanitized = generic_term.strip()
            if not sanitized:
                continue
            token = f'-"{sanitized}"' if " " in sanitized else f'-{sanitized}'
            if token not in negative_tokens:
                negative_tokens.append(token)

        parts.extend(negative_tokens)
    
    return " ".join(parts)

async def cse_image_search(query: str, domain: str = None, num: int = 3, 
                          img_type: str = "photo", safe: str = "active") -> List[Dict]:
    """Search images using Google Custom Search API"""
    if not GOOGLE_CSE_API_KEY or not GOOGLE_CSE_ID:
        logger.error("Google CSE credentials not configured")
        return []
    
    try:
        # Build service synchronously (googleapiclient doesn't support async)
        service = build("customsearch", "v1", developerKey=GOOGLE_CSE_API_KEY)
        
        params = {
            "q": query,
            "cx": GOOGLE_CSE_ID,
            "searchType": "image",
            "num": min(10, num),
            "safe": safe,
            "imgType": img_type,
            "imgSize": "LARGE"
        }
        
        # Add domain restriction if specified
        if domain:
            params["siteSearch"] = domain
            params["siteSearchFilter"] = "i"
        
        # Execute search in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: service.cse().list(**params).execute()
        )
        
        return result.get("items", [])
        
    except Exception as e:
        logger.error(f"CSE search error for query '{query}': {str(e)}")
        return []

def is_relevant_image(item: Dict, core_keywords: Set[str], is_savory: bool = True) -> bool:
    """Check if image result is relevant to the menu item"""
    title = (item.get("title") or "").lower()
    snippet = (item.get("snippet") or "").lower()
    link = (item.get("link") or "").lower()
    context_link = (item.get("image", {}).get("contextLink", "")).lower()
    
    # Combine all text for checking
    all_text = f"{title} {snippet} {link} {context_link}"
    
    # Must contain at least one core keyword
    if not any(keyword in all_text for keyword in core_keywords):
        return False
    
    # For savory items, avoid dessert images
    if is_savory:
        if any(sweet_term in all_text for sweet_term in NEGATIVE_SWEET_TERMS):
            return False
    
    if any(term in all_text for term in NEGATIVE_OBJECT_TERMS):
        return False

    # Avoid obvious non-food content
    unwanted_terms = [
        "stock photo", "clipart", "vector", "menu", "price list",
        "restaurant sign", "chef portrait", "kitchen staff", "dining room",
        "table setting", "cutlery", "advertisement", "flyer", "brochure"
    ]
    if any(term in all_text for term in unwanted_terms):
        return False
    
    # Additional check for faces/people in URLs or titles
    if any(term in all_text for term in ["face", "person", "people", "chef", "waiter"]):
        return False
    
    return True

def canonical_image_url(url: str) -> str:
    """Create canonical URL for deduplication"""
    try:
        parsed = urlparse(url)
        path = parsed.path.lower()
        return f"{parsed.netloc.lower()}{path}"
    except:
        return url

async def fetch_image_with_fallback(url: str, thumbnail_url: str = None) -> Optional[bytes]:
    """Fetch image bytes with fallback to thumbnail"""
    headers_options = [
        {"User-Agent": USER_AGENT, "Referer": f"https://{urlparse(url).netloc}/"},
        {"User-Agent": USER_AGENT, "Referer": "https://www.google.com/"},
        {"User-Agent": USER_AGENT}
    ]
    
    async with aiohttp.ClientSession() as session:
        # Try main URL with different headers
        for headers in headers_options:
            try:
                async with session.get(url, headers=headers, timeout=10) as response:
                    if response.status == 200:
                        return await response.read()
            except:
                continue
        
        # Fallback to thumbnail if available
        if thumbnail_url:
            try:
                async with session.get(
                    thumbnail_url, 
                    headers={"User-Agent": USER_AGENT}, 
                    timeout=10
                ) as response:
                    if response.status == 200:
                        return await response.read()
            except:
                pass
    
    return None

async def validate_image_bytes(image_bytes: bytes) -> bool:
    """Validate that bytes represent a valid image"""
    try:
        img = Image.open(BytesIO(image_bytes))
        # Check minimum dimensions
        width, height = img.size
        if width < 200 or height < 200:
            return False
        # Check aspect ratio (avoid extreme ratios)
        aspect_ratio = width / height
        if aspect_ratio < 0.3 or aspect_ratio > 3.0:
            return False
        return True
    except:
        return False

async def search_images_for_item(name: str, description: str = None, 
                                limit: int = 3, use_cache: bool = True) -> List[str]:
    """Search for high-quality food images for a menu item"""
    
    # First, check cache if enabled
    if use_cache:
        cached_images = await search_cached_images(name, description, limit)
        if cached_images and len(cached_images) >= limit:
            logger.info(f"Using {len(cached_images)} cached images for '{name}'")
            return cached_images
        
        # If we have some cached images but not enough, reduce the search limit
        if cached_images:
            logger.info(f"Found {len(cached_images)} cached images, searching for {limit - len(cached_images)} more")
            search_limit = limit - len(cached_images)
        else:
            cached_images = []
            search_limit = limit
    else:
        cached_images = []
        search_limit = limit
    
    if not GOOGLE_CSE_API_KEY or not GOOGLE_CSE_ID:
        logger.error("Google CSE credentials not configured")
        return cached_images  # Return what we have from cache
    
    # Normalize the menu item name
    core, modifiers = normalize_menu_item(name)
    logger.info(f"Searching images for: {name} (core: {core}, modifiers: {modifiers})")
    
    # Determine if item is savory
    is_savory = not any(sweet in core for sweet in ["cake", "dessert", "ice", "chocolate", "cookie", "brownie"])
    
    # Create keyword set for relevance checking
    core_keywords = {core}
    if "burger" in core:
        core_keywords.update(["burger", "hamburger", "cheeseburger"])
    core_keywords.update(modifiers[:2])  # Add top modifiers
    
    # Tracking for deduplication
    seen_images = set()
    seen_pages = set()
    results = []
    
    # Strategy 1: Search with domain restrictions in a single query
    # Build site restriction for multiple domains
    site_restrict = " OR ".join([f"site:{domain}" for domain in FOOD_DOMAINS[:5]])  # Top 5 domains
    strict_query = f"{build_search_query(core, modifiers, description, add_context=True, use_negatives=True)} ({site_restrict})"
    
    # Single API call to search across multiple domains
    items = await cse_image_search(strict_query, domain=None, num=min(limit * 2, 10))  # Get extra to filter
    
    for item in items:
        if len(results) >= limit:
            break
            
        link = item.get("link", "")
        context_link = item.get("image", {}).get("contextLink", "")
        
        # Skip duplicates
        canonical_url = canonical_image_url(link)
        if canonical_url in seen_images or context_link in seen_pages:
            continue
        
        # Check relevance
        if not is_relevant_image(item, core_keywords, is_savory):
            continue
        
        # Mark as seen and add to results
        seen_images.add(canonical_url)
        seen_pages.add(context_link)
        results.append(link)
        logger.debug(f"Found image: {link}")
    
    # Strategy 2: If not enough results, try broader search (only if really needed)
    if len(results) < limit:
        remaining_needed = limit - len(results)
        looser_query = build_search_query(core, modifiers[:1], description, add_context=False, use_negatives=False)
        
        # Search without domain restriction - only get what we need
        items = await cse_image_search(looser_query, num=min(remaining_needed * 2, 10))
        
        for item in items:
            if len(results) >= limit:
                break
                
            link = item.get("link", "")
            context_link = item.get("image", {}).get("contextLink", "")
            
            # Skip duplicates
            canonical_url = canonical_image_url(link)
            if canonical_url in seen_images or context_link in seen_pages:
                continue
            
            # Check relevance (less strict)
            if not is_relevant_image(item, {core}, is_savory):
                continue
            
            # Prefer images from known food sites
            display_link = item.get("displayLink", "").lower()
            if not any(food_site in display_link for food_site in FOOD_DOMAINS):
                # For non-food sites, be more strict about relevance
                if not all(k in item.get("title", "").lower() for k in [core]):
                    continue
            
            seen_images.add(canonical_url)
            seen_pages.add(context_link)
            results.append(link)
            logger.debug(f"Found image (broader search): {link}")
    
    logger.info(f"Found {len(results)} new images for '{name}'")
    
    # Cache the newly found images asynchronously (don't wait)
    if results and use_cache:
        # Fire and forget - cache in background
        asyncio.create_task(cache_new_images(results[:search_limit], name, description))
    
    # Combine cached images with new results
    final_results = cached_images + results[:search_limit]
    
    logger.info(f"Returning {len(final_results)} total images for '{name}' ({len(cached_images)} cached, {len(results[:search_limit])} new)")
    return final_results[:limit]  # Ensure we don't exceed the limit


async def cache_new_images(image_urls: List[str], item_name: str, item_description: str = None):
    """Cache newly found images in the background"""
    try:
        for url in image_urls:
            await download_and_store_image(url, item_name, item_description)
    except Exception as e:
        logger.error(f"Error caching images: {str(e)}")
        # Don't fail the main request if caching fails

async def search_images_batch(items: List[Dict[str, str]], limit_per_item: int = 2) -> Dict[str, List[Tuple[str, str]]]:
    """Search images for multiple menu items concurrently"""
    
    async def search_with_metadata(item_id: str, name: str, description: str):
        """Search and return with metadata"""
        image_urls = await search_images_for_item(name, description, limit_per_item)
        
        # Return URLs with source metadata
        results = []
        for url in image_urls:
            results.append((url, "google_cse"))  # Mark source as Google CSE
        
        # If no results, add empty list
        if not results:
            logger.warning(f"No images found for item: {name}")
        
        return (item_id, results)
    
    # Create tasks for concurrent execution
    tasks = []
    for item in items:
        tasks.append(search_with_metadata(
            item['id'],
            item['name'],
            item.get('description')
        ))
    
    # Execute all searches concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Build result dictionary
    image_map = {}
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Error in batch image search: {result}")
            continue
        
        item_id, images = result
        image_map[item_id] = images
    
    return image_map

