# app/routers/menu.py
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from typing import Dict, List, Optional
import logging
import asyncio
from datetime import datetime
import uuid
import os

from app.core.auth import get_current_user, verify_user_credits, deduct_user_credits
from app.services.image_processor import process_and_optimize_image, validate_image_file
from app.services.openai_service import extract_menu_items
from app.services.google_search_service import search_images_for_item
from app.core.async_supabase import async_supabase_client
from app.models.menu import MenuResponse, MenuItem

router = APIRouter()
logger = logging.getLogger(__name__)

# Maximum file size: 10MB
MAX_FILE_SIZE = 10 * 1024 * 1024

# Test mode flag - set via environment variable
TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"

def get_mock_menu_items():
    """Return mock menu items for testing"""
    return [
        {
            "name": "Margherita Pizza",
            "description": "Fresh tomatoes, mozzarella, basil",
            "price": 12.99,
            "currency": "USD"
        },
        {
            "name": "Caesar Salad", 
            "description": "Romaine lettuce, parmesan, croutons",
            "price": 8.50,
            "currency": "USD"
        },
        {
            "name": "Grilled Salmon",
            "description": "Atlantic salmon with lemon herbs", 
            "price": 18.75,
            "currency": "USD"
        },
        {
            "name": "Chocolate Cake",
            "description": "Rich chocolate cake with vanilla ice cream",
            "price": 6.25,
            "currency": "USD"
        }
    ]

def get_mock_images():
    """Return mock image URLs for testing"""
    return [
        "https://images.unsplash.com/photo-1565299624946-b28f40a0ca4b?w=400",
        "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=400"
    ]

@router.post("/upload", response_model=MenuResponse)
async def upload_menu(
    menu: UploadFile = File(...),
    current_user: Dict = Depends(get_current_user)
):
    """Upload and process a menu image"""
    
    start_time = datetime.utcnow()
    logger.info(f"Starting menu upload for user {current_user['id']}")
    
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
    
    # Validate image file format
    if not validate_image_file(contents):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image file. Please upload a valid image format (JPEG, PNG, GIF, etc.)."
        )
    
    # Verify user has credits
    await verify_user_credits(current_user, required_credits=1)
    
    # Create menu record
    menu_id = str(uuid.uuid4())
    try:
        menu_response = await async_supabase_client.table_insert("menus", {
            "id": menu_id,
            "user_id": current_user["id"],
            "status": "processing",
            "processed_at": datetime.utcnow().isoformat()
        })
        
        logger.info(f"Created menu record {menu_id} for user {current_user['id']}")
    except Exception as e:
        logger.error(f"Failed to create menu record: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create menu record"
        )
    
    try:
        if TEST_MODE:
            # Test mode: use mock data
            logger.info(f"TEST MODE: Using mock data for menu {menu_id}")
            extracted_items = get_mock_menu_items()
        else:
            # Normal mode: process image and extract items
            logger.info(f"Processing image for menu {menu_id}")
            process_start = datetime.utcnow()
            base64_image = await process_and_optimize_image(contents)
            process_time = (datetime.utcnow() - process_start).total_seconds()
            logger.info(f"Image processing completed in {process_time:.2f}s")
            
            # Extract menu items using OpenAI
            logger.info(f"Extracting menu items for menu {menu_id}")
            extraction_start = datetime.utcnow()
            extracted_items = await extract_menu_items(base64_image)
            extraction_time = (datetime.utcnow() - extraction_start).total_seconds()
            logger.info(f"Menu extraction completed in {extraction_time:.2f}s, found {len(extracted_items) if extracted_items else 0} items")
        
        if not extracted_items:
            # Update menu status to failed
            await async_supabase_client.table_update("menus", {
                "status": "failed"
            }, eq={"id": menu_id})
            
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Could not extract any menu items from the image"
            )
        
        # Process each menu item
        menu_items = []
        menu_item_records = []
        
        # First, create all menu item records
        for index, item in enumerate(extracted_items):
            menu_item_id = str(uuid.uuid4())
            menu_item_data = {
                "id": menu_item_id,
                "menu_id": menu_id,
                "item_name": item["name"],
                "description": item.get("description"),
                "price": item.get("price"),
                "currency": item.get("currency", "USD"),  # Use detected currency or default to USD
                "order_index": index
            }
            menu_item_records.append((menu_item_id, menu_item_data, item))
        
        # Insert all menu items at once
        menu_items_to_insert = [record[1] for record in menu_item_records]
        await async_supabase_client.table_insert("menu_items", menu_items_to_insert)
        
        if TEST_MODE:
            # Test mode: use mock images
            logger.info(f"TEST MODE: Using mock images for {len(menu_item_records)} items")
            mock_images = get_mock_images()
            image_results = [mock_images for _ in menu_item_records]
        else:
            # Normal mode: search for images
            # Prepare all image search tasks
            image_search_tasks = []
            for menu_item_id, menu_item_data, item in menu_item_records:
                search_query = f"{item['name']} dish food"
                if item.get("description"):
                    search_query += f" {item['description'][:50]}"  # Add partial description
                
                # Create coroutine for image search
                task = search_images_for_item(search_query, limit=2)
                image_search_tasks.append((menu_item_id, item, task))
            
            # Execute all image searches in parallel
            logger.info(f"Starting parallel image search for {len(image_search_tasks)} items")
            search_start = datetime.utcnow()
            image_results = await asyncio.gather(
                *[task for _, _, task in image_search_tasks],
                return_exceptions=True  # Don't fail if one search fails
            )
            search_time = (datetime.utcnow() - search_start).total_seconds()
            logger.info(f"Parallel image search completed in {search_time:.2f}s")
        
        # Process results and prepare image records
        all_image_records = []
        
        if TEST_MODE:
            # For test mode, iterate over menu_item_records
            items_to_process = [(record[0], record[2]) for record in menu_item_records]
        else:
            # For normal mode, use image_search_tasks
            items_to_process = [(task[0], task[1]) for task in image_search_tasks]
        
        for i, (menu_item_id, item) in enumerate(items_to_process):
            image_urls = []
            
            # Handle results or exceptions
            if isinstance(image_results[i], Exception):
                logger.warning(f"Image search failed for item '{item['name']}': {str(image_results[i])}")
            elif image_results[i]:
                image_urls = image_results[i]
                
                # Prepare image records for batch insert
                for j, image_url in enumerate(image_urls):
                    all_image_records.append({
                        "menu_item_id": menu_item_id,
                        "image_url": image_url,
                        "source": "google_cse",
                        "is_primary": j == 0
                    })
            
            # Add to response
            menu_items.append({
                "id": menu_item_id,
                "name": item["name"],
                "description": item.get("description"),
                "price": item.get("price"),
                "images": image_urls
            })
        
        # Batch insert all image records
        if all_image_records:
            await async_supabase_client.table_insert("item_images", all_image_records)
        
        # Update menu status to completed
        await async_supabase_client.table_update("menus", {
            "status": "completed"
        }, eq={"id": menu_id})
        
        # Deduct credits
        await deduct_user_credits(current_user["id"], credits=1)
        
        total_time = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"Successfully processed menu {menu_id} with {len(menu_items)} items in {total_time:.2f}s")
        
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
        total_time = (datetime.utcnow() - start_time).total_seconds()
        logger.error(f"Error processing menu {menu_id} after {total_time:.2f}s: {str(e)}", exc_info=True)
        
        # Update menu status to failed
        try:
            await async_supabase_client.table_update("menus", {
                "status": "failed"
            }, eq={"id": menu_id})
        except Exception as update_error:
            logger.error(f"Failed to update menu status to 'failed' for menu {menu_id}: {str(update_error)}")
        
        # Provide more specific error messages based on the error type
        if "timeout" in str(e).lower():
            detail = "Request timed out. Please try uploading a smaller image or try again later."
        elif "connection" in str(e).lower():
            detail = "Connection error. Please check your internet connection and try again."
        else:
            detail = "Failed to process menu. Please try again."
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail
        )

@router.get("/{menu_id}")
async def get_menu(
    menu_id: str,
    current_user: Dict = Depends(get_current_user)
):
    """Get a specific menu with all its items"""
    try:
        # Get menu with items and images
        menu_response = await async_supabase_client.table_select(
            "menus",
            "*, menu_items(*, item_images(*))",
            eq={"id": menu_id, "user_id": current_user["id"]},
            single=True
        )
        
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
        menus_response = await async_supabase_client.table_select(
            "menus",
            "*, menu_items(count)",
            eq={"user_id": current_user["id"]},
            order={"processed_at": True}
        )
        
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
