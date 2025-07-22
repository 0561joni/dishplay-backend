# app/routers/translation.py
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, List
import logging
from pydantic import BaseModel

from app.core.auth import get_current_user
from app.services.translation_service import translate_menu_items

router = APIRouter()
logger = logging.getLogger(__name__)

class TranslateMenuRequest(BaseModel):
    items: List[Dict]
    target_language: str
    source_language: str = "auto"

class TranslateMenuResponse(BaseModel):
    success: bool
    items: List[Dict]
    target_language: str

@router.post("/translate-menu", response_model=TranslateMenuResponse)
async def translate_menu(
    request: TranslateMenuRequest,
    current_user: Dict = Depends(get_current_user)
):
    """Translate menu items to the target language"""
    
    try:
        # Validate target language
        supported_languages = ["en", "fr", "de", "es", "it", "pt", "ja", "ko", "zh", "ar", "hi", "ru"]
        if request.target_language not in supported_languages:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported language: {request.target_language}. Supported: {', '.join(supported_languages)}"
            )
        
        # Translate items
        translated_items = await translate_menu_items(
            items=request.items,
            target_language=request.target_language,
            source_language=request.source_language
        )
        
        return TranslateMenuResponse(
            success=True,
            items=translated_items,
            target_language=request.target_language
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Translation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to translate menu items"
        )