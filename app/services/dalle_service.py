# app/services/dalle_service.py
import httpx
import aiohttp
import logging
import os
from typing import List, Optional, Dict
import asyncio
from openai import AsyncOpenAI
from slugify import slugify
from app.core.supabase_client import get_supabase_client
import io

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Supabase storage bucket name
MENU_IMAGES_BUCKET = os.getenv("SUPABASE_BUCKET_MENU_IMAGES", "menu-images")

async def download_image(url: str) -> bytes:
    """Download image from URL and return bytes"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.read()
                else:
                    logger.error(f"Failed to download image: HTTP {response.status}")
                    raise Exception(f"Failed to download image: HTTP {response.status}")
    except Exception as e:
        logger.error(f"Error downloading image from {url}: {str(e)}")
        raise

async def upload_to_supabase_storage(image_data: bytes, filename: str) -> Optional[str]:
    """Upload image to Supabase storage and return public URL"""
    try:
        supabase = get_supabase_client()
        
        # Upload to storage
        file_path = f"generated/{filename}"
        
        # Check if file already exists
        try:
            existing_files = supabase.storage.from_(MENU_IMAGES_BUCKET).list(path="generated/")
            if any(file['name'] == filename for file in existing_files):
                logger.info(f"Image already exists in storage: {filename}")
                # Get public URL for existing file
                public_url = supabase.storage.from_(MENU_IMAGES_BUCKET).get_public_url(file_path)
                return public_url
        except Exception as e:
            logger.debug(f"Error checking existing files: {e}")
            # Continue with upload if check fails
        
        # Upload the image
        response = supabase.storage.from_(MENU_IMAGES_BUCKET).upload(
            file=image_data,
            path=file_path,
            file_options={
                "content-type": "image/jpeg",
                "upsert": True  # Overwrite if exists
            }
        )
        
        # Get public URL
        public_url = supabase.storage.from_(MENU_IMAGES_BUCKET).get_public_url(file_path)
        
        logger.info(f"Successfully uploaded image to Supabase: {filename}")
        return public_url
        
    except Exception as e:
        logger.error(f"Error uploading image to Supabase: {str(e)}")
        return None

async def generate_image_for_item(item_name: str, description: Optional[str] = None) -> Optional[str]:
    """Generate a single image for a menu item using DALL-E 3 and store in Supabase"""
    
    try:
        # Generate filename from item name
        filename = f"{slugify(item_name)}.jpg"
        
        # Check if image already exists in Supabase
        supabase = get_supabase_client()
        file_path = f"generated/{filename}"
        
        try:
            existing_files = supabase.storage.from_(MENU_IMAGES_BUCKET).list(path="generated/")
            if any(file['name'] == filename for file in existing_files):
                logger.info(f"Image already exists for '{item_name}', returning cached URL")
                public_url = supabase.storage.from_(MENU_IMAGES_BUCKET).get_public_url(file_path)
                return public_url
        except Exception as e:
            logger.debug(f"Error checking cache: {e}")
            # Continue with generation if cache check fails
        
        # Create a structured prompt for consistent, high-quality food images
        prompt = f"High-resolution, photorealistic image of {item_name}, plated on a clean white plate, viewed at a 45-degree angle under natural lighting, realistic background, food magazine style"
        
        # Add description context if available
        if description:
            prompt += f". The dish contains: {description}"
        
        logger.info(f"Generating image for: {item_name}")
        logger.debug(f"DALL-E prompt: {prompt}")
        
        # Generate image using DALL-E 3
        response = await client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1
        )
        
        # Extract the temporary image URL
        if not response.data or len(response.data) == 0:
            logger.warning(f"No image data returned for '{item_name}'")
            return None
        
        temp_url = response.data[0].url
        logger.info(f"Successfully generated image for '{item_name}', downloading...")
        
        # Download the image
        image_data = await download_image(temp_url)
        logger.info(f"Downloaded image for '{item_name}', uploading to Supabase...")
        
        # Upload to Supabase and get permanent URL
        permanent_url = await upload_to_supabase_storage(image_data, filename)
        
        if permanent_url:
            logger.info(f"Successfully stored image for '{item_name}' at: {permanent_url}")
            return permanent_url
        else:
            logger.error(f"Failed to upload image for '{item_name}'")
            return None
            
    except Exception as e:
        logger.error(f"Error generating image for '{item_name}': {str(e)}")
        return None

async def generate_images_for_item(item_name: str, description: Optional[str] = None, limit: int = 1) -> List[str]:
    """Generate image(s) for a menu item using DALL-E 3 and store in Supabase
    
    Note: DALL-E 3 only supports specific sizes: 1024x1024, 1024x1792, or 1792x1024
    We use 1024x1024 as the smallest available option.
    """
    
    # Only generate 1 image per item
    limit = 1
    
    if limit <= 0:
        return []
    
    # Generate and store the image
    image_url = await generate_image_for_item(item_name, description)
    
    if image_url:
        return [image_url]
    else:
        return []

async def generate_images_batch(items: List[Dict[str, str]], limit_per_item: int = 1) -> Dict[str, List[str]]:
    """Generate images for multiple menu items concurrently"""
    
    async def generate_with_id(item_id: str, item_name: str, description: Optional[str] = None):
        images = await generate_images_for_item(item_name, description, limit_per_item)
        return (item_id, images)
    
    # Create tasks for concurrent generation
    tasks = []
    for item in items:
        item_id = item['id']
        item_name = item['name']
        description = item.get('description')
        
        tasks.append(generate_with_id(item_id, item_name, description))
    
    # Execute all image generations concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Build the result map
    image_map = {}
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Error in batch image generation: {result}")
            continue
        
        item_id, images = result
        image_map[item_id] = images
    
    return image_map

def get_fallback_image() -> str:
    """Return a fallback image URL when generation fails"""
    # Using a generic food placeholder from a reliable source
    return "https://via.placeholder.com/1024x1024.png?text=Image+Not+Available"