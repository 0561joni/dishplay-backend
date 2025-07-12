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
        if