# app/services/dalle_service.py
import httpx
import logging
import os
from typing import List, Optional, Dict
import asyncio
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def generate_image_for_item(item_name: str, description: Optional[str] = None) -> Optional[str]:
    """Generate a single image for a menu item using DALL-E 3"""
    
    try:
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
        
        # Extract the image URL
        if response.data and len(response.data) > 0:
            image_url = response.data[0].url
            logger.info(f"Successfully generated image for '{item_name}'")
            return image_url
        else:
            logger.warning(f"No image data returned for '{item_name}'")
            return None
            
    except Exception as e:
        logger.error(f"Error generating image for '{item_name}': {str(e)}")
        return None

async def generate_images_for_item(item_name: str, description: Optional[str] = None, limit: int = 1) -> List[str]:
    """Generate image(s) for a menu item using DALL-E 3
    
    Note: DALL-E 3 only supports specific sizes: 1024x1024, 1024x1792, or 1792x1024
    We use 1024x1024 as the smallest available option.
    """
    
    # Only generate 1 image per item
    limit = 1
    
    if limit <= 0:
        return []
    
    images = []
    
    try:
        # Create a structured prompt for consistent, high-quality food images
        prompt = f"High-resolution, photorealistic image of {item_name}, plated on a clean white plate, viewed at a 45-degree angle under natural lighting, realistic background, food magazine style"
        
        # Add description context if available
        if description:
            prompt += f". The dish contains: {description}"
        
        logger.debug(f"DALL-E prompt: {prompt}")
        
        # Generate image
        # Note: DALL-E 3 only supports specific sizes, using 1024x1024 as the smallest
        response = await client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",  # Smallest available size for DALL-E 3
            quality="standard",  # Use standard quality to reduce costs
            n=1
        )
        
        # Extract the image URL
        if response.data and len(response.data) > 0:
            image_url = response.data[0].url
            images.append(image_url)
            logger.info(f"Generated image for '{item_name}'")
        
    except Exception as e:
        logger.error(f"Error generating image for '{item_name}': {str(e)}")
    
    return images

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