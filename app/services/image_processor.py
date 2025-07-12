# app/services/image_processor.py
from PIL import Image
import io
import base64
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

# Maximum dimensions for image optimization
MAX_WIDTH = 1920
MAX_HEIGHT = 1080
# JPEG quality for optimization
JPEG_QUALITY = 85

async def process_and_optimize_image(image_bytes: bytes) -> str:
    """
    Process and optimize image for OpenAI API
    Returns base64 encoded image string
    """
    try:
        # Open image
        image = Image.open(io.BytesIO(image_bytes))
        
        # Convert RGBA to RGB if necessary
        if image.mode in ('RGBA', 'LA', 'P'):
            # Create a white background
            background = Image.new('RGB', image.size, (255, 255, 255))
            if image.mode == 'P':
                image = image.convert('RGBA')
            background.paste(image, mask=image.split()[-1] if image.mode in ('RGBA', 'LA') else None)
            image = background
        elif image.mode not in ('RGB', 'L'):
            image = image.convert('RGB')
        
        # Get current dimensions
        width, height = image.size
        logger.info(f"Original image size: {width}x{height}")
        
        # Calculate new dimensions if needed
        if width > MAX_WIDTH or height > MAX_HEIGHT:
            # Calculate scaling factor
            scale = min(MAX_WIDTH / width, MAX_HEIGHT / height)
            new_width = int(width * scale)
            new_height = int(height * scale)
            
            # Resize image
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            logger.info(f"Resized image to: {new_width}x{new_height}")
        
        # Convert to JPEG for optimization
        output_buffer = io.BytesIO()
        image.save(output_buffer, format='JPEG', quality=JPEG_QUALITY, optimize=True)
        output_buffer.seek(0)
        
        # Convert to base64
        base64_image = base64.b64encode(output_buffer.getvalue()).decode('utf-8')
        
        logger.info(f"Optimized image size: {len(base64_image)} bytes (base64)")
        
        return base64_image
        
    except Exception as e:
        logger.error(f"Error processing image: {str(e)}")
        raise Exception(f"Failed to process image: {str(e)}")

def validate_image_file(file_bytes: bytes) -> bool:
    """Validate if the file is a valid image"""
    try:
        image = Image.open(io.BytesIO(file_bytes))
        image.verify()
        return True
    except:
        return False
