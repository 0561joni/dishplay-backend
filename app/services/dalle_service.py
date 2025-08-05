# app/services/dalle_service.py
import httpx
import aiohttp
import logging
import os
import asyncio
from typing import List, Optional, Dict, Tuple
from openai import AsyncOpenAI
from slugify import slugify
from app.core.supabase_client import get_supabase_client
import time
from datetime import datetime
import hashlib

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Supabase storage bucket name
MENU_IMAGES_BUCKET = os.getenv("SUPABASE_BUCKET_MENU_IMAGES", "menu-images")

# Rate limits
DALLE3_MAX_PER_MIN = 7  # Use DALL-E 3 for the first 7 images
DALLE2_MAX_PER_MIN = 50

# Retry configuration
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 2.0  # seconds - start with 2s for Cloudflare rate limits
CLOUDFLARE_RETRY_DELAY = 10.0  # seconds - longer delay for Cloudflare 1015 errors

# Global semaphore to serialize API requests
api_semaphore = asyncio.Semaphore(1)

class RateLimiter:
    """Simple rate limiter for API calls"""
    def __init__(self, max_calls: int, time_window: int = 60):
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = []
        self.lock = asyncio.Lock()
    
    async def wait_if_needed(self):
        """Wait if rate limit would be exceeded"""
        async with self.lock:
            now = time.time()
            # Remove old calls outside the time window
            self.calls = [call_time for call_time in self.calls if now - call_time < self.time_window]
            
            if len(self.calls) >= self.max_calls:
                # Wait until the oldest call is outside the time window
                sleep_time = self.time_window - (now - self.calls[0]) + 0.1
                logger.info(f"Rate limit reached, waiting {sleep_time:.1f} seconds")
                await asyncio.sleep(sleep_time)
                # Remove the old call
                self.calls.pop(0)
            
            # Record this call
            self.calls.append(now)

# Initialize rate limiters
dalle3_limiter = RateLimiter(DALLE3_MAX_PER_MIN)
dalle2_limiter = RateLimiter(DALLE2_MAX_PER_MIN)

async def download_image_with_retry(url: str, max_retries: int = MAX_RETRIES) -> bytes:
    """Download image from URL with retry logic"""
    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.read()
                    else:
                        logger.error(f"Failed to download image: HTTP {response.status}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(INITIAL_RETRY_DELAY * (2 ** attempt))
                            continue
                        raise Exception(f"Failed to download image: HTTP {response.status}")
        except Exception as e:
            logger.error(f"Error downloading image (attempt {attempt + 1}/{max_retries}): {str(e)}")
            if attempt < max_retries - 1:
                await asyncio.sleep(INITIAL_RETRY_DELAY * (2 ** attempt))
                continue
            raise

async def upload_to_supabase_storage(image_data: bytes, filename: str) -> Optional[str]:
    """Upload image to Supabase storage and return public URL"""
    try:
        supabase = get_supabase_client()
        
        # Upload to storage
        file_path = f"generated/{filename}"
        
        # Upload the image
        response = supabase.storage.from_(MENU_IMAGES_BUCKET).upload(
            file=image_data,
            path=file_path,
            file_options={
                "content-type": "image/jpeg",
                "upsert": "true"  # Must be string, not boolean
            }
        )
        
        # Get public URL
        public_url = supabase.storage.from_(MENU_IMAGES_BUCKET).get_public_url(file_path)
        
        logger.info(f"Successfully uploaded image to Supabase: {filename}")
        logger.info(f"Public URL: {public_url}")
        return public_url
        
    except Exception as e:
        logger.error(f"Error uploading image to Supabase: {str(e)}")
        return None

def generate_filename(item_name: str, description: Optional[str] = None) -> str:
    """Generate a unique filename based on item name and description"""
    base_name = slugify(item_name)
    
    if description:
        # Create a short hash of the description to make filename unique
        desc_hash = hashlib.md5(description.encode()).hexdigest()[:8]
        return f"{base_name}-{desc_hash}.jpg"
    else:
        return f"{base_name}.jpg"

async def check_existing_image(item_name: str, description: Optional[str] = None) -> Optional[str]:
    """Check if image already exists in Supabase storage"""
    try:
        supabase = get_supabase_client()
        filename = generate_filename(item_name, description)
        file_path = f"generated/{filename}"
        
        # List files in the generated directory
        existing_files = supabase.storage.from_(MENU_IMAGES_BUCKET).list(path="generated/")
        
        if any(file['name'] == filename for file in existing_files):
            logger.info(f"Image already exists for '{item_name}', returning cached URL")
            public_url = supabase.storage.from_(MENU_IMAGES_BUCKET).get_public_url(file_path)
            logger.info(f"Cached public URL: {public_url}")
            return public_url
            
    except Exception as e:
        logger.debug(f"Error checking existing image: {e}")
    
    return None

async def generate_with_dalle3(item_name: str, description: Optional[str] = None) -> Optional[Tuple[str, str]]:
    """Generate image using DALL-E 3 with retry logic"""
    prompt = f"High-resolution, photorealistic image of {item_name}, plated on a clean white plate, viewed at a 45-degree angle under natural lighting, realistic background, food magazine style"
    
    if description:
        prompt += f". The dish contains: {description}"
    
    # Serialize API requests using semaphore
    async with api_semaphore:
        # Wait for rate limit
        await dalle3_limiter.wait_if_needed()
        
        # Add small delay between requests to avoid bursts
        await asyncio.sleep(0.5)
    
    for attempt in range(MAX_RETRIES):
        try:
            logger.info(f"Generating image with DALL-E 3 for: {item_name} (attempt {attempt + 1})")
            
            response = await client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1024x1024",
                quality="standard",
                n=1
            )
            
            if response.data and len(response.data) > 0:
                return response.data[0].url, "dalle-3"
            
        except Exception as e:
            error_str = str(e)
            logger.error(f"Error generating with DALL-E 3 (attempt {attempt + 1}): {error_str}")
            
            # Check for Cloudflare error 1015 (rate limit)
            is_cloudflare_error = "1015" in error_str or "cloudflare" in error_str.lower() or "rate limit" in error_str.lower()
            
            if attempt < MAX_RETRIES - 1:
                if is_cloudflare_error:
                    # Use longer delay for Cloudflare rate limits: 10, 20, 30 seconds
                    backoff_time = CLOUDFLARE_RETRY_DELAY * (attempt + 1)
                    logger.info(f"Cloudflare rate limit detected, waiting {backoff_time}s before retry")
                else:
                    # Use exponential backoff for other errors: 2, 4, 8 seconds
                    backoff_time = INITIAL_RETRY_DELAY * (2 ** attempt)
                await asyncio.sleep(backoff_time)
                continue
            
    return None

async def generate_with_dalle2(item_name: str, description: Optional[str] = None) -> Optional[Tuple[str, str]]:
    """Generate image using DALL-E 2 with retry logic"""
    # DALL-E 2 has slightly different requirements, adjust prompt if needed
    prompt = f"A photorealistic image of {item_name}, professional food photography, clean presentation"
    
    if description:
        # DALL-E 2 works better with shorter prompts
        prompt = f"{item_name}, {description[:50]}, food photography"
    
    # Serialize API requests using semaphore
    async with api_semaphore:
        # Wait for rate limit
        await dalle2_limiter.wait_if_needed()
        
        # Add small delay between requests to avoid bursts
        await asyncio.sleep(0.5)
    
    for attempt in range(MAX_RETRIES):
        try:
            logger.info(f"Generating image with DALL-E 2 for: {item_name} (attempt {attempt + 1})")
            
            response = await client.images.generate(
                model="dall-e-2",
                prompt=prompt,
                size="1024x1024",
                n=1
            )
            
            if response.data and len(response.data) > 0:
                return response.data[0].url, "dalle-2"
            
        except Exception as e:
            error_str = str(e)
            logger.error(f"Error generating with DALL-E 2 (attempt {attempt + 1}): {error_str}")
            
            # Check for Cloudflare error 1015 (rate limit)
            is_cloudflare_error = "1015" in error_str or "cloudflare" in error_str.lower() or "rate limit" in error_str.lower()
            
            if attempt < MAX_RETRIES - 1:
                if is_cloudflare_error:
                    # Use longer delay for Cloudflare rate limits: 10, 20, 30 seconds
                    backoff_time = CLOUDFLARE_RETRY_DELAY * (attempt + 1)
                    logger.info(f"Cloudflare rate limit detected, waiting {backoff_time}s before retry")
                else:
                    # Use exponential backoff for other errors: 2, 4, 8 seconds
                    backoff_time = INITIAL_RETRY_DELAY * (2 ** attempt)
                await asyncio.sleep(backoff_time)
                continue
            
    return None

async def generate_and_store_image(item_name: str, description: Optional[str] = None, use_dalle3: bool = True) -> Optional[Tuple[str, str]]:
    """Generate image and store in Supabase, returns (url, model_used)"""
    
    # Check if image already exists
    existing_url = await check_existing_image(item_name, description)
    if existing_url:
        return existing_url, "cached"
    
    # Generate with appropriate model
    generation_result = None
    if use_dalle3:
        generation_result = await generate_with_dalle3(item_name, description)
    else:
        generation_result = await generate_with_dalle2(item_name, description)
    
    if not generation_result:
        logger.error(f"Failed to generate image for '{item_name}'")
        return None
    
    temp_url, model_used = generation_result
    
    try:
        # Download the image
        logger.info(f"Downloading generated image for '{item_name}'")
        image_data = await download_image_with_retry(temp_url)
        
        # Upload to Supabase with unique filename
        filename = generate_filename(item_name, description)
        permanent_url = await upload_to_supabase_storage(image_data, filename)
        
        if permanent_url:
            logger.info(f"Successfully stored image for '{item_name}' using {model_used}")
            return permanent_url, model_used
        
    except Exception as e:
        logger.error(f"Error processing image for '{item_name}': {str(e)}")
    
    return None

async def generate_images_for_item(item_name: str, description: Optional[str] = None, limit: int = 1) -> List[str]:
    """Generate image(s) for a menu item - for backward compatibility"""
    
    # Only generate 1 image per item
    limit = 1
    
    result = await generate_and_store_image(item_name, description, use_dalle3=True)
    
    if result:
        url, _ = result
        return [url]
    else:
        return []

async def generate_images_batch(items: List[Dict[str, str]], limit_per_item: int = 1) -> Dict[str, List[Tuple[str, str]]]:
    """
    Generate images for multiple menu items with intelligent batching
    Returns dict mapping item_id to list of (url, model_used) tuples
    """
    
    # Check which items need generation
    items_to_generate = []
    results = {}
    
    for item in items:
        item_id = item['id']
        item_name = item['name']
        description = item.get('description')
        
        # Check cache first with description
        existing_url = await check_existing_image(item_name, description)
        if existing_url:
            results[item_id] = [(existing_url, "cached")]
            logger.info(f"Using cached image for '{item_name}'")
        else:
            items_to_generate.append(item)
    
    if not items_to_generate:
        logger.info("All images found in cache")
        return results
    
    # Split items between DALL-E 3 and DALL-E 2
    dalle3_items = items_to_generate[:DALLE3_MAX_PER_MIN]
    dalle2_items = items_to_generate[DALLE3_MAX_PER_MIN:]
    
    logger.info(f"Generating {len(dalle3_items)} images with DALL-E 3 and {len(dalle2_items)} with DALL-E 2")
    
    # Create tasks for all generations
    tasks = []
    
    # DALL-E 3 tasks
    for item in dalle3_items:
        task = generate_and_store_image(
            item['name'], 
            item.get('description'),
            use_dalle3=True
        )
        tasks.append((item['id'], task))
    
    # DALL-E 2 tasks
    for item in dalle2_items:
        task = generate_and_store_image(
            item['name'], 
            item.get('description'),
            use_dalle3=False
        )
        tasks.append((item['id'], task))
    
    # Execute tasks sequentially to avoid overwhelming the API
    generation_results = []
    for item_id, task in tasks:
        try:
            result = await task
            generation_results.append(result)
        except Exception as e:
            logger.error(f"Error generating image for item {item_id}: {e}")
            generation_results.append(e)
    
    # Process results
    for i, (item_id, _) in enumerate(tasks):
        result = generation_results[i]
        
        if isinstance(result, Exception):
            logger.error(f"Error generating image for item {item_id}: {result}")
            results[item_id] = []
        elif result:
            url, model_used = result
            results[item_id] = [(url, model_used)]
        else:
            results[item_id] = []
    
    return results

def get_fallback_image() -> str:
    """Return a fallback image URL when generation fails"""
    return "https://via.placeholder.com/1024x1024.png?text=Image+Not+Available"