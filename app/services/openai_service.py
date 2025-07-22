# app/services/openai_service.py
import openai
import json
import logging
import os
from typing import List, Dict, Optional
import re
from app.utils.currency_detector import detect_currency_comprehensive
from app.services.translation_service import detect_language, translate_to_english_for_search

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
4. original_price_text: The original price text as it appears on the menu (optional)

Also extract:
- restaurant_name: Restaurant name if visible
- currency_info: Any currency symbols, codes, or hints you can identify
- location_info: Any address, city, country information if visible

Return the data as a JSON object with this structure:
{
    "restaurant_name": "Restaurant Name if found",
    "currency_info": {
        "symbols_found": ["$", "USD"],
        "location_hints": ["New York", "USA"],
        "price_format": "12.99"
    },
    "items": [
        {
            "name": "Dish Name",
            "description": "Description if available",
            "price": 12.99,
            "original_price_text": "$12.99"
        }
    ]
}

Important:
- Extract ALL visible menu items
- For prices, extract only the number (e.g., 12.99 not $12.99) but preserve original text
- Include any currency symbols you see (e.g., $, €, £, ¥, ₹)
- Note any location information that might indicate currency region
- If no price is visible, omit both price and original_price_text fields
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
        
        # Extract items and currency info
        items = data.get("items", [])
        restaurant_name = data.get("restaurant_name")
        currency_info = data.get("currency_info", {})
        
        # Detect currency using comprehensive method
        symbols_found = currency_info.get("symbols_found", [])
        location_hints = currency_info.get("location_hints", [])
        price_texts = [item.get("original_price_text", "") for item in items if item.get("original_price_text")]
        
        detected_currency = detect_currency_comprehensive(
            restaurant_name=restaurant_name,
            location_text=" ".join(location_hints) if location_hints else None,
            price_strings=price_texts + symbols_found
        )
        
        logger.info(f"Detected currency: {detected_currency}")
        
        # Detect language from menu content
        sample_text = " ".join([item.get("name", "") for item in items[:5]])  # Use first 5 items
        if restaurant_name:
            sample_text = f"{restaurant_name} {sample_text}"
        
        detected_language = await detect_language(sample_text)
        logger.info(f"Detected language: {detected_language}")
        
        # Validate and clean items
        cleaned_items = []
        for item in items:
            if not item.get("name"):
                continue
            
            cleaned_item = {
                "name": clean_text(item["name"]),
                "restaurant_name": restaurant_name,
                "currency": detected_currency,
                "original_language": detected_language
            }
            
            if item.get("description"):
                cleaned_item["description"] = clean_text(item["description"])
            
            # Add English translations for search if not already in English
            if detected_language != "en":
                english_data = await translate_to_english_for_search(
                    cleaned_item["name"],
                    cleaned_item.get("description")
                )
                cleaned_item["name_en"] = english_data["name"]
                cleaned_item["search_terms"] = english_data["search_terms"]
                if english_data.get("description"):
                    cleaned_item["description_en"] = english_data["description"]
            else:
                # Already in English
                cleaned_item["name_en"] = cleaned_item["name"]
                cleaned_item["search_terms"] = ""
            
            if item.get("price") is not None:
                try:
                    # Ensure price is a float
                    price = float(str(item["price"]).replace("$", "").replace(",", "").strip())
                    if price > 0:
                        cleaned_item["price"] = round(price, 2)
                except (ValueError, TypeError):
                    logger.warning(f"Invalid price format for item {item.get('name')}: {item.get('price')}")
            
            cleaned_items.append(cleaned_item)
        
        logger.info(f"Extracted {len(cleaned_items)} menu items in {detected_language}")
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
