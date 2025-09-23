# app/services/openai_service.py
import openai
import json
import logging
import os
from typing import Any, Dict, List, Optional
import re
from app.utils.currency_detector import detect_currency_comprehensive
from app.services.translation_service import detect_language, translate_to_english_for_search

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def extract_menu_items(base64_image: str) -> Dict[str, Any]:
    """Extract menu items and metadata from an image using GPT-4 Vision."""

    prompt = """You are a menu extraction expert. Analyze this menu image and extract all menu items with their details.

For each menu item, extract:
1. name: The name of the dish (required)
2. description: A brief description if available (optional)
3. price: The numerical price without currency symbols (optional, as float)
4. original_price_text: The original price text as it appears on the menu (optional)

IMPORTANT - Handling dishes with multiple options:
Many dishes come with different protein or ingredient options (like fish, tofu, chicken, beef, etc.).
When you see a dish with multiple options:
- Create a SEPARATE ITEM for each option
- Format the name as: "Main Dish Name - Option"
- Example: If "Pad Thai" has options for chicken, tofu, and shrimp:
  - "Pad Thai - Chicken" (with chicken price)
  - "Pad Thai - Tofu" (with tofu price)
  - "Pad Thai - Shrimp" (with shrimp price)
- Include option-specific details in the description
- Options can be marked with letters (A, B, C), numbers (1, 2, 3), bullets, or just listed - handle all formats

Also extract:
- menu_title: Either the visible menu/restaurant title OR a descriptive name you create that fits the menu if none is visible
- restaurant_name: Restaurant name if visible
- currency_info: Any currency symbols, codes, or hints you can identify
- location_info: Any address, city, country information if visible

Return the data as a JSON object with this structure:
{
    "menu_title": "Always provide a meaningful menu title",
    "restaurant_name": "Restaurant Name if found",
    "currency_info": {
        "symbols_found": ["$", "USD"],
        "location_hints": ["New York", "USA"],
        "price_format": "12.99"
    },
    "items": [
        {
            "name": "Dish Name - Option",
            "description": "Description including option details",
            "price": 12.99,
            "original_price_text": "$12.99"
        }
    ]
}

Important:
- Extract ALL visible menu items including ALL variations/options as separate items
- Each option of a dish should be its own item with its own price
- Ensure menu_title is NEVER empty. Create a descriptive title if no name is visible (e.g., "Brunch Specials Menu")
- For prices, extract only the number (e.g., 12.99 not $12.99) but preserve original text
- Include any currency symbols you see (e.g., $, EUR, GBP, JPY, INR)
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
            temperature=0.3,
            response_format={"type": "json_object"}
        )

        # Parse the response
        content = response.choices[0].message.content
        logger.info(f"OpenAI raw response: {content[:200]}...")

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse JSON from OpenAI response: {content}")
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                raise ValueError("No valid JSON found in response")

        # Extract structured data
        items = data.get("items", [])
        restaurant_name_raw = data.get("restaurant_name")
        menu_title_raw = data.get("menu_title") or data.get("menuTitle") or data.get("title")
        currency_info = data.get("currency_info", {})

        restaurant_name = clean_title_candidate(restaurant_name_raw)
        menu_title = None
        for candidate in (menu_title_raw, restaurant_name_raw):
            menu_title = clean_title_candidate(candidate)
            if menu_title:
                break
        if not menu_title:
            menu_title = generate_fallback_title(items)
        if not restaurant_name:
            restaurant_name = menu_title

        # Detect currency using comprehensive method
        symbols_found = currency_info.get("symbols_found", [])
        location_hints = currency_info.get("location_hints", [])
        price_texts = [item.get("original_price_text", "") for item in items if item.get("original_price_text")]

        detected_currency = detect_currency_comprehensive(
            restaurant_name=restaurant_name or menu_title,
            location_text=" ".join(location_hints) if location_hints else None,
            price_strings=price_texts + symbols_found
        )

        logger.info(f"Detected currency: {detected_currency}")

        # Detect language from menu content
        sample_parts = []
        if menu_title:
            sample_parts.append(menu_title)
        sample_parts.extend(item.get("name", "") for item in items[:5])
        sample_text = " ".join(part for part in sample_parts if part).strip()

        detected_language = await detect_language(sample_text or menu_title or "")
        logger.info(f"Detected language: {detected_language}")

        # Validate and clean items
        cleaned_items = []
        for item in items:
            if not item.get("name"):
                continue

            cleaned_item = {
                "name": clean_text(item["name"]),
                "menu_title": menu_title,
                "title": menu_title,
                "restaurant_name": restaurant_name,
                "currency": detected_currency,
                "original_language": detected_language
            }

            if item.get("description"):
                cleaned_item["description"] = clean_text(item["description"])

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
                cleaned_item["name_en"] = cleaned_item["name"]
                cleaned_item["search_terms"] = ""

            if item.get("price") is not None:
                try:
                    price = float(str(item["price"]).replace("$", "").replace(",", "").strip())
                    if price > 0:
                        cleaned_item["price"] = round(price, 2)
                except (ValueError, TypeError):
                    logger.warning(f"Invalid price format for item {item.get('name')}: {item.get('price')}")

            cleaned_items.append(cleaned_item)

        logger.info(
            f"Extracted {len(cleaned_items)} menu items in {detected_language} with title '{menu_title}'"
        )
        return {
            "items": cleaned_items,
            "title": menu_title,
            "menu_title": menu_title,
            "restaurant_name": restaurant_name,
            "currency": detected_currency,
            "language": detected_language
        }

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


def clean_title_candidate(value: Optional[str]) -> Optional[str]:
    """Normalize potential menu title values."""
    if not value or not isinstance(value, str):
        return None
    cleaned = clean_text(value)
    return cleaned if cleaned else None

def generate_fallback_title(items: List[Dict]) -> str:
    """Create a descriptive menu title when none is detected."""
    candidate_names: List[str] = []
    for item in items:
        name = item.get("name")
        if not name:
            continue
        cleaned_name = clean_text(name)
        if cleaned_name:
            candidate_names.append(cleaned_name)
        if len(candidate_names) >= 5:
            break

    unique_names: List[str] = []
    for name in candidate_names:
        if name not in unique_names:
            unique_names.append(name)
        if len(unique_names) >= 2:
            break

    if not unique_names:
        return "Uploaded Menu"

    if len(unique_names) == 1:
        single = unique_names[0]
        if single.lower().endswith("menu"):
            return single
        return f"{single} Menu"

    title = f"{unique_names[0]} & {unique_names[1]}"
    if len(title) > 60:
        return f"{unique_names[0]} Menu"
    return title
