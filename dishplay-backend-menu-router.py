# app/routers/menu.py
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from typing import Dict, List, Optional
import logging
import asyncio
from datetime import datetime
import uuid

from app.core.auth import get_current_user, verify_user_credits, deduct_user_credits
from app.services.image_processor import process_and_optimize_image
from app.services.openai_service import extract_menu_items
from app.services.google_search_service import search_images_for_item
from app.core.supabase_client import supabase_client
from app.models.menu import MenuResponse, MenuItem

router = APIRouter()
logger = logging.getLogger(__name__)

# Maximum file size: 10MB
MAX_FILE_SIZE = 10 * 1024 * 1024

@router.post("/upload", response_model=MenuResponse)
async def upload_menu(
    menu: UploadFile = File(...),
    current_user: Dict = Depends(get_current_user)
):
    """Upload and process a menu image"""
    
    # Validate file type
    if not menu.content_type or not menu.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Please upload an image file."
        )
    
    # Check file size
    contents = await menu.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large. Maximum size is 10MB."
        )
    
    # Verify user has credits
    await verify_user_credits(current_user, required_credits=1)
    
    # Create menu record
    menu_id = str(uuid.uuid4())
    try:
        menu_response = supabase_client.table("menus").insert({
            "id": menu_id,
            "user_id": current_user["id"],
            "status": "processing",
            "processed_at": datetime.utcnow().isoformat()
        }).execute()
        
        logger.info(f"Created menu record {menu_id} for user {current_user['id']}")
    except Exception as e:
        logger.error(f"Failed to create menu record: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create menu record"
        )
    
    try:
        # Process and optimize image
        logger.info(f"Processing image for menu {menu_id}")
        base64_image = await process_and_optimize_image(contents)
        
        # Extract menu items using OpenAI
        logger.info(f"Extracting menu items for menu {menu_id}")
        extracted_items = await extract_menu_items(base64_image)
        
        if not extracted_items:
            # Update menu status to failed
            supabase_client.table("menus").update({
                "status": "failed"
            }).eq("id", menu_id).execute()
            
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Could not extract any menu items from the image"
            )
        
        # Process each menu item
        menu_items = []
        for index, item in enumerate(extracted_items):
            # Create menu item record
            menu_item_id = str(uuid.uuid4())
            
            menu_item_data = {
                "id": menu_item_id,
                "menu_id": menu_id,
                "item_name": item["name"],
                "description": item.get("description"),
                "price": item.get("price"),
                "currency": "USD",  # Default to USD
                "order_index": index
            }
            
            # Insert menu item
            item_response = supabase_client.table("menu_items").insert(menu_item_data).execute()
            
            # Search for images concurrently
            search_query = f"{item['name']} food"
            if item.get("description"):
                search_query += f" {item['description'][:50]}"  # Add partial description
            
            # Get images for the item
            image_urls = await search_images_for_item(search_query, limit=2)
            
            # Store image URLs
            if image_urls:
                image_records = []
                for i, image_url in enumerate(image_urls):
                    image_records.append({
                        "menu_item_id": menu_item_id,
                        "image_url": image_url,
                        "source": "google_cse",
                        "is_primary": i == 0
                    })
                
                if image_records:
                    supabase_client.table("item_images").insert(image_records).execute()
            
            # Add to response
            menu_items.append({
                "id": menu_item_id,
                "name": item["name"],
                "description": item.get("description"),
                "price": item.get("price"),
                "images": image_urls
            })
        
        # Update menu status to completed
        supabase_client.table("menus").update({
            "status": "completed"
        }).eq("id", menu_id).execute()
        
        # Deduct credits
        await deduct_user_credits(current_user["id"], credits=1)
        
        logger.info(f"Successfully processed menu {menu_id} with {len(menu_items)} items")
        
        # Get restaurant name from the extraction if available
        restaurant_name = extracted_items[0].get("restaurant_name", "Uploaded Menu") if extracted_items else "Uploaded Menu"
        
        return MenuResponse(
            success=True,
            message="Menu processed successfully",
            menu_id=menu_id,
            restaurantName=restaurant_name,
            items=menu_items,
            credits_remaining=current_user["credits"] - 1
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing menu {menu_id}: {str(e)}")
        
        # Update menu status to failed
        try:
            supabase_client.table("menus").update({
                "status": "failed"
            }).eq("id", menu_id).execute()
        except:
            pass
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process menu. Please try again."
        )

@router.get("/{menu_id}")
async def get_menu(
    menu_id: str,
    current_user: Dict = Depends(get_current_user)
):
    """Get a specific menu with all its items"""
    try:
        # Get menu with items and images
        menu_response = supabase_client.table("menus").select(
            "*, menu_items(*, item_images(*))"
        ).eq("id", menu_id).eq("user_id", current_user["id"]).single().execute()
        
        if not menu_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Menu not found"
            )
        
        menu_data = menu_response.data
        
        # Transform the data
        items = []
        for item in menu_data.get("menu_items", []):
            images = [img["image_url"] for img in item.get("item_images", [])]
            items.append({
                "id": item["id"],
                "name": item["item_name"],
                "description": item["description"],
                "price": item["price"],
                "images": images
            })
        
        return {
            "id": menu_data["id"],
            "status": menu_data["status"],
            "processed_at": menu_data["processed_at"],
            "items": items
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching menu {menu_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch menu"
        )

@router.get("/user/all")
async def get_user_menus(
    current_user: Dict = Depends(get_current_user)
):
    """Get all menus for the current user"""
    try:
        menus_response = supabase_client.table("menus").select(
            "*, menu_items(count)"
        ).eq("user_id", current_user["id"]).order("processed_at", desc=True).execute()
        
        menus = []
        for menu in menus_response.data:
            item_count = menu.get("menu_items", [{}])[0].get("count", 0) if menu.get("menu_items") else 0
            menus.append({
                "id": menu["id"],
                "status": menu["status"],
                "processed_at": menu["processed_at"],
                "item_count": item_count
            })
        
        return {"menus": menus}
        
    except Exception as e:
        logger.error(f"Error fetching user menus: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch menus"
        )