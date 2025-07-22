# app/services/translation_service.py
import openai
import json
import logging
import os
from typing import Dict, List, Optional
import asyncio

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def translate_menu_items(items: List[Dict], target_language: str, source_language: str = "auto") -> List[Dict]:
    """Translate menu items to target language using OpenAI"""
    
    if not items or target_language == "en":
        # No translation needed if target is English
        return items
    
    # Language mapping for OpenAI
    language_map = {
        "en": "English",
        "fr": "French",
        "de": "German",
        "es": "Spanish",
        "it": "Italian",
        "pt": "Portuguese",
        "ja": "Japanese",
        "ko": "Korean",
        "zh": "Chinese",
        "ar": "Arabic",
        "hi": "Hindi",
        "ru": "Russian"
    }
    
    target_lang_name = language_map.get(target_language, target_language)
    
    # Prepare items for translation (only name and description)
    items_to_translate = []
    for item in items:
        translation_item = {
            "id": item.get("id"),
            "name": item.get("name"),
            "description": item.get("description")
        }
        items_to_translate.append(translation_item)
    
    prompt = f"""You are a professional menu translator. Translate the following menu items to {target_lang_name}.

Important rules:
1. Maintain the exact same JSON structure
2. Only translate the 'name' and 'description' fields
3. Keep the 'id' field unchanged
4. Preserve any culinary terms that are commonly used in the original language
5. Make the translations sound natural and appetizing in the target language
6. If description is null or empty, keep it as null

Menu items to translate:
{json.dumps(items_to_translate, ensure_ascii=False)}

Return the translated items as a JSON array with the same structure."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a professional translator specializing in restaurant menus and culinary terms."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content
        translated_data = json.loads(content)
        
        # Get the items array from the response
        translated_items = translated_data.get("items", translated_data) if isinstance(translated_data, dict) else translated_data
        
        # Merge translations back with original items
        translated_map = {item["id"]: item for item in translated_items if "id" in item}
        
        result_items = []
        for original_item in items:
            item_id = original_item.get("id")
            if item_id and item_id in translated_map:
                # Merge translated fields with original item
                translated_item = original_item.copy()
                translated_item["name"] = translated_map[item_id].get("name", original_item["name"])
                if "description" in translated_map[item_id]:
                    translated_item["description"] = translated_map[item_id]["description"]
                result_items.append(translated_item)
            else:
                # Keep original if translation not found
                result_items.append(original_item)
        
        logger.info(f"Successfully translated {len(result_items)} menu items to {target_language}")
        return result_items
        
    except Exception as e:
        logger.error(f"Translation error: {str(e)}")
        # Return original items if translation fails
        return items

async def translate_to_english_for_search(item_name: str, item_description: Optional[str] = None) -> Dict[str, str]:
    """Translate menu item to English for Google search"""
    
    prompt = f"""Translate this menu item to English for searching food images.

Item name: {item_name}
Description: {item_description or ""}

Return a JSON object with:
1. "name": The English translation of the dish name
2. "search_terms": Additional English search terms that would help find images of this dish
3. "description": English translation of the description (if provided)

Example:
Input: "Poulet Rôti", "Poulet fermier aux herbes"
Output: {{"name": "Roast Chicken", "search_terms": "roasted chicken herbs french", "description": "Farm chicken with herbs"}}"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content
        result = json.loads(content)
        
        return {
            "name": result.get("name", item_name),
            "search_terms": result.get("search_terms", ""),
            "description": result.get("description", item_description)
        }
        
    except Exception as e:
        logger.error(f"Error translating to English: {str(e)}")
        # Return original if translation fails
        return {
            "name": item_name,
            "search_terms": "",
            "description": item_description
        }

async def detect_language(text: str) -> str:
    """Detect the language of the given text"""
    
    if not text:
        return "en"
    
    prompt = f"""Detect the language of this text and return only the ISO 639-1 language code (e.g., 'en', 'fr', 'es', 'de', 'it', 'ja', 'ko', 'zh').

Text: {text}

Return only the 2-letter language code."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0,
            max_tokens=10
        )
        
        language_code = response.choices[0].message.content.strip().lower()
        
        # Validate it's a 2-letter code
        if len(language_code) == 2 and language_code.isalpha():
            return language_code
        else:
            return "en"  # Default to English if invalid
            
    except Exception as e:
        logger.error(f"Error detecting language: {str(e)}")
        return "en"  # Default to English on error