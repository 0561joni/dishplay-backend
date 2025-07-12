# app/services/openai_service.py
import openai
import json
import logging
import os
from typing import List, Dict, Optional
import re

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def extract_menu_items(base64_image: str) -> List[Dict]:
    """Extract menu items from image using GPT-4 Vision"""
    
    prompt = """You are a menu extraction expert. Analyze this menu image and extract all menu items with their details.

For each menu item, extract:
1. name: The name of the dish (required)
2. description: A brief description if available (optional)
3. price: The numerical price without currency symbols (optional, as float)

Also try to identify the restaurant name if visible.

Return the data as a JSON object with this structure:
{
    "restaurant_name": "Restaurant Name if found",
    "items": [
        {
            "name": "Dish Name",
            "description": "Description if available",
            "price": 12.99
        }
    ]
}

Important:
- Extract ALL visible menu items
- For prices, extract only the number (e.g., 12.99 not $12.99)
- If no price is visible, omit the price field
- If no description is available, omit the description field
- Ensure names are properly capitalized
- Remove any special characters or formatting from item names
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            max_tokens=4096,
            temperature=0.3,  # Lower temperature for more consistent extraction
            response_format={"type": "json_object"}
        )
        
        # Parse the response
        content = response.choices[0].message.content
        logger.info(f"OpenAI raw response: {content[:200]}...")
        
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse JSON from OpenAI response: {content}")
            # Try to extract JSON from the response
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                raise ValueError("No valid JSON found in response")
        
        # Extract items
        items = data.get("items", [])
        restaurant_name = data.get("restaurant_name")
        
        # Validate and clean items
        cleaned_items = []
        for item in items:
            if not item.get("name"):
                continue
            
            cleaned_item = {
                "name": clean_text(item["name"]),
                "restaurant_name": restaurant_name
            }
            
            if item.get("description"):
                cleaned_item["description"] = clean_text(item["description"])
            
            if item.get("price") is not None:
                try:
                    # Ensure price is a float
                    price = float(str(item["price"]).replace("$", "").replace(",", "").strip())
                    if price > 0:
                        cleaned_item["price"] = round(price, 2)
                except (ValueError, TypeError):
                    logger.warning(f"Invalid price format for item {item.get('name')}: {item.get('price')}")
            
            cleaned_items.append(cleaned_item)
        
        logger.info(f"Extracted {len(cleaned_items)} menu items")
        return cleaned_items
        
    except Exception as e:
        logger.error(f"OpenAI extraction error: {str(e)}")
        raise Exception(f"Failed to extract menu items: {str(e)}")

def clean_text(text: str) -> str:
    """Clean and normalize text"""
    if not text:
        return ""
    
    # Remove extra whitespace
    text = " ".join(text.split())
    
    # Remove special characters but keep basic punctuation
    text = re.sub(r'[^\w\s\-.,!?\'"]', '', text)
    
    # Trim
    text = text.strip()
    
    # Capitalize properly (title case for names)
    if len(text) <= 50:  # Likely a dish name
        text = text.title()
    
    return text
