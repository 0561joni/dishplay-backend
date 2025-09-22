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
from app.core.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

# Supabase Storage bucket for cached images
CACHE_BUCKET = "menu-images-cache"

def _extract_data(response):
    """Safely extract data payload from Supabase responses"""
    if response is None:
        return []
    data = getattr(response, "data", None)
    if data is None and isinstance(response, dict):
        data = response.get("data")
    return data or []


def _extract_error(response):
    """Extract error payload from Supabase responses"""
    if response is None:
        return None
    error = getattr(response, "error", None)
    if error is None and isinstance(response, dict):
        error = response.get("error")
    return error


async def _upload_to_storage(bucket: str, path: str, data: bytes, options: Dict[str, str]):
    """Upload bytes to Supabase storage in a background thread"""
    supabase = get_supabase_client()

    def _upload():
        storage = supabase.storage.from_(bucket)
        buffer = BytesIO(data)
        buffer.seek(0)
        return storage.upload(path, buffer, file_options=options)

    return await asyncio.to_thread(_upload)


async def _get_public_url(bucket: str, path: str) -> Optional[str]:
    """Retrieve public URL for a storage object"""
    supabase = get_supabase_client()

    def _get():
        return supabase.storage.from_(bucket).get_public_url(path)

    response = await asyncio.to_thread(_get)

    if isinstance(response, str):
        return response

    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data.get("publicUrl") or data.get("public_url")

    if isinstance(response, dict):
        data = response.get("data")
        if isinstance(data, dict):
            return data.get("publicUrl") or data.get("public_url")

    return None


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
    """Search Supabase cache for relevant images"""
    try:
        normalized_name = normalize_item_name(item_name)
        category = get_item_category(item_name)

        response = await async_supabase_client.table_select(
            "cached_food_images",
            "*",
            eq={"normalized_name": normalized_name, "is_active": True},
            order={"created_at": True},
            limit=limit
        )
        error = _extract_error(response)
        if error:
            logger.error(f"Cache lookup failed for '{item_name}': {error}")
            records: List[Dict] = []
        else:
            records = _extract_data(response)

        cached_urls: List[str] = [item.get("storage_url") for item in records if item.get("storage_url")]
        cached_urls = [url for url in cached_urls if url][:limit]

        if len(cached_urls) >= limit:
            logger.info(f"Found {len(cached_urls)} exact cached images for '{item_name}'")
            return cached_urls

        remaining = max(0, limit - len(cached_urls))

        if remaining > 0 and category != "general":
            category_response = await async_supabase_client.table_select(
                "cached_food_images",
                "*",
                eq={"category": category, "is_active": True},
                limit=remaining * 5
            )
            category_error = _extract_error(category_response)
            if category_error:
                logger.error(f"Category cache lookup failed for '{item_name}': {category_error}")
                category_records = []
            else:
                category_records = _extract_data(category_response)

            scored_matches: List[Tuple[float, str]] = []
            search_words = set(normalized_name.split())

            for item in category_records:
                storage_url = item.get("storage_url")
                normalized_cached = item.get("normalized_name", "")
                if not storage_url or storage_url in cached_urls:
                    continue

                item_words = set(normalized_cached.split())
                union = item_words.union(search_words)
                similarity = len(item_words.intersection(search_words)) / len(union) if union else 0

                if similarity > 0.3:
                    scored_matches.append((similarity, storage_url))

            scored_matches.sort(reverse=True)
            for _, url in scored_matches[:remaining]:
                cached_urls.append(url)

            if scored_matches:
                logger.info(f"Found {min(len(scored_matches), remaining)} similar cached images for '{item_name}' in category '{category}'")

        return cached_urls[:limit]

    except Exception as e:
        logger.error(f"Error searching cached images: {str(e)}")
        return []



async def download_and_store_image(image_url: str, item_name: str, 
                                  item_description: str = None) -> Optional[str]:
    """Download image from URL and store in Supabase Storage"""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            async with session.get(image_url, headers=headers, timeout=10) as response:
                if response.status != 200:
                    logger.error(f"Failed to download image: {response.status}")
                    return None
                image_data = await response.read()

        optimized_data = image_data
        image_width: Optional[int] = None
        image_height: Optional[int] = None

        try:
            img = Image.open(BytesIO(image_data))

            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = background
            elif img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')

            if img.width > 1920:
                ratio = 1920 / img.width
                new_height = int(img.height * ratio)
                img = img.resize((1920, new_height), Image.Resampling.LANCZOS)

            output = BytesIO()
            img.save(output, format='JPEG', quality=85, optimize=True)
            optimized_data = output.getvalue()
            image_width, image_height = img.size
            img.close()
        except Exception as e:
            logger.error(f"Error processing image: {str(e)}")
            try:
                with Image.open(BytesIO(image_data)) as original_img:
                    image_width, image_height = original_img.size
            except Exception:
                image_width = image_height = None

        content_hash = hashlib.md5(optimized_data).hexdigest()[:12]
        normalized_name = normalize_item_name(item_name)
        safe_name = re.sub(r'[^\w\s-]', '', normalized_name).replace(' ', '-')[:30] or 'menu-item'
        filename = f"{safe_name}_{content_hash}.jpg"
        storage_path = f"cached/{get_item_category(item_name)}/{filename}"

        upload_response = await _upload_to_storage(
            CACHE_BUCKET,
            storage_path,
            optimized_data,
            {
                'content-type': 'image/jpeg',
                'cache-control': 'public, max-age=31536000',
                'upsert': 'true'
            }
        )

        upload_error = _extract_error(upload_response)
        if upload_error:
            message = str(upload_error)
            if 'exists' not in message.lower():
                logger.error(f"Failed to upload image to Supabase Storage: {message}")
                return None

        storage_url = await _get_public_url(CACHE_BUCKET, storage_path)
        if not storage_url:
            logger.error("Failed to obtain public URL for cached image")
            return None

        metadata = {
            'storage_path': storage_path,
            'storage_url': storage_url,
            'original_url': image_url,
            'item_name': item_name,
            'normalized_name': normalized_name,
            'category': get_item_category(item_name),
            'description': item_description,
            'file_size': len(optimized_data),
            'image_width': image_width,
            'image_height': image_height,
            'created_at': datetime.utcnow().isoformat(),
            'is_active': True
        }

        insert_response = await async_supabase_client.table_insert("cached_food_images", metadata)
        insert_error = _extract_error(insert_response)
        if insert_error:
            logger.error(f"Failed to record cached image metadata: {insert_error}")

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
