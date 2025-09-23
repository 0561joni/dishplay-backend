# app/routers/menu.py
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, Query
from typing import Dict, List, Optional
import logging
import asyncio
from datetime import datetime
import uuid
import os
import json

from app.core.auth import get_current_user, verify_user_credits, deduct_user_credits
from app.services.image_processor import process_and_optimize_image, validate_image_file
from app.services.openai_service import extract_menu_items
from app.services.google_search_service import search_images_batch
from app.services.dalle_service import get_fallback_image
from app.core.async_supabase import async_supabase_client
from app.models.menu import MenuResponse, MenuItem
from app.services.progress_tracker import progress_tracker

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

def resolve_menu_title(extraction_result: Dict, items: List[Dict]) -> str:
    """Determine a human-friendly menu title from extraction data."""
    candidates = [
        extraction_result.get("title"),
        extraction_result.get("menu_title"),
        extraction_result.get("restaurant_name")
    ]

    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()

    item_names = [
        item.get("name")
        for item in items
        if isinstance(item, dict) and isinstance(item.get("name"), str) and item.get("name").strip()
    ]

    if item_names:
        primary = item_names[0].strip()
        secondary = next((name.strip() for name in item_names[1:] if name.strip()), None)
        if secondary:
            combined = f"{primary} & {secondary}"
            if len(combined) <= 60:
                return combined
        if not primary.lower().endswith("menu"):
            primary = f"{primary} Menu"
        return primary

    return "Uploaded Menu"

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
    
    # Start progress tracking (estimate 10 items initially)
    await progress_tracker.start_tracking(menu_id, estimated_items=10)
    
    menu_title = "Uploaded Menu"

    try:
        menu_response = await async_supabase_client.table_insert("menus", {
            "id": menu_id,
            "user_id": current_user["id"],
            "status": "processing",
            "title": "Uploaded Menu",
            "processed_at": datetime.utcnow().isoformat()
        })
        
        logger.info(f"Created menu record {menu_id} for user {current_user['id']}")
        await progress_tracker.update_progress(menu_id, "initializing", 5)
    except Exception as e:
        logger.error(f"Failed to create menu record: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create menu record"
        )
    
    try:
        extraction_result: Dict = {"items": []}
        if TEST_MODE:
            # Test mode: use mock data
            logger.info(f"TEST MODE: Using mock data for menu {menu_id}")
            extracted_items = get_mock_menu_items()
            extraction_result = {
                "items": extracted_items,
                "title": "Sample Menu",
                "menu_title": "Sample Menu",
                "restaurant_name": "Sample Menu"
            }
        else:
            # Normal mode: process image and extract items
            logger.info(f"Processing image for menu {menu_id}")
            await progress_tracker.update_progress(menu_id, "image_processing", 10)
            process_start = datetime.utcnow()
            base64_image = await process_and_optimize_image(contents)
            process_time = (datetime.utcnow() - process_start).total_seconds()
            logger.info(f"Image processing completed in {process_time:.2f}s")
            await progress_tracker.update_progress(menu_id, "image_processed", 20)

            # Extract menu items using OpenAI
            logger.info(f"Extracting menu items for menu {menu_id}")
            await progress_tracker.update_progress(menu_id, "extracting_menu", 25)
            extraction_start = datetime.utcnow()
            extraction_result = await extract_menu_items(base64_image)
            extraction_time = (datetime.utcnow() - extraction_start).total_seconds()
            extracted_items = extraction_result.get("items", [])
            logger.info(
                f"Menu extraction completed in {extraction_time:.2f}s, found {len(extracted_items) if extracted_items else 0} items"
            )

        extracted_items = extraction_result.get("items", [])

        menu_title = resolve_menu_title(extraction_result, extracted_items)
        logger.info(f"Resolved menu title for {menu_id}: {menu_title}")
        try:
            await async_supabase_client.table_update("menus", {"title": menu_title}, eq={"id": menu_id})
        except Exception as update_error:
            logger.warning(f"Failed to update menu title for {menu_id}: {update_error}")

        if extracted_items:
            await progress_tracker.update_progress(
                menu_id, "menu_extracted", 40,
                {"item_count": len(extracted_items), "menu_title": menu_title}
            )

        if not extracted_items:
            # Update menu status to failed
            await async_supabase_client.table_update("menus", {
                "status": "failed",
                "title": menu_title
            }, eq={"id": menu_id})
            
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Could not extract any menu items from the image"
            )
        
        # Process each menu item
        menu_items = []
        menu_item_records = []
        placeholder_items = []

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
            placeholder_items.append({
                "id": menu_item_id,
                "name": menu_item_data["item_name"],
                "description": menu_item_data["description"],
                "price": menu_item_data["price"],
                "currency": menu_item_data["currency"],
                "order_index": menu_item_data["order_index"],
            })

        # Insert all menu items at once
        menu_items_to_insert = [record[1] for record in menu_item_records]
        await progress_tracker.update_progress(
            menu_id,
            "saving_items",
            45,
            {
                "items_snapshot": placeholder_items,
                "menu_title": menu_title
            }
        )
        await async_supabase_client.table_insert("menu_items", menu_items_to_insert)
        await progress_tracker.update_progress(menu_id, "items_saved", 50)
        if TEST_MODE:
            # Test mode: use mock images
            logger.info(f"TEST MODE: Using mock images for {len(menu_item_records)} items")
            mock_images = get_mock_images()
            image_results = {record[0]: [(mock_images[0], "mock")] for record in menu_item_records}
        else:
            # Normal mode: generate images using batch processing
            items_for_generation = []
            for menu_item_id, menu_item_data, item in menu_item_records:
                item_name = item.get('name_en', item['name'])
                description = item.get('description_en') or item.get('description')

                items_for_generation.append({
                    'id': menu_item_id,
                    'name': item_name,
                    'description': description
                })

            logger.info(f"Starting batch image search for {len(items_for_generation)} items")
            await progress_tracker.update_progress(menu_id, "searching_images", 55)
            search_start = datetime.utcnow()

            image_results = await search_images_batch(items_for_generation, limit_per_item=3)

            search_time = (datetime.utcnow() - search_start).total_seconds()
            logger.info(f"Batch image search completed in {search_time:.2f}s")

        # Process results and prepare image records
        all_image_records = []
        total_menu_items = len(menu_item_records) or 1

        for index, (menu_item_id, menu_item_data, item) in enumerate(menu_item_records):
            image_urls = []
            item_results = image_results.get(menu_item_id, [])
            image_sources = []

            # Get results for this item
            if item_results:
                for j, (image_url, model_used) in enumerate(item_results):
                    if image_url:
                        image_urls.append(image_url)
                        image_sources.append({"url": image_url, "source": model_used})

                        # Always store the image association in the database
                        # Even for cached images, we need to associate them with this menu item
                        all_image_records.append({
                            "menu_item_id": menu_item_id,
                            "image_url": image_url,
                            "source": model_used,  # "google_cse" or "mock"
                            "is_primary": j == 0
                        })

            # If no images were generated, use fallback placeholder
            if not image_urls:
                logger.warning(f"No image generated for item '{item['name']}', using fallback")
                fallback_url = get_fallback_image()
                image_urls.append(fallback_url)
                image_sources.append({"url": fallback_url, "source": "fallback"})

                # Store fallback image in database
                all_image_records.append({
                    "menu_item_id": menu_item_id,
                    "image_url": fallback_url,
                    "source": "fallback",
                    "is_primary": True
                })

            # Add to response
            menu_items.append({
                "id": menu_item_id,
                "name": item["name"],
                "description": item.get("description"),
                "price": item.get("price"),
                "images": image_urls
            })

            progress_value = 55 + int(((index + 1) / total_menu_items) * 25)
            await progress_tracker.update_progress(
                menu_id,
                "searching_images",
                min(progress_value, 80),
                {
                    "item_image_update": {
                        "menu_item_id": menu_item_id,
                        "images": image_urls,
                        "primary_image": image_urls[0] if image_urls else None,
                        "status": "ready" if item_results else "fallback",
                        "sequence": str(uuid.uuid4()),
                        "sources": image_sources
                    }
                }
            )

        await progress_tracker.update_progress(menu_id, "images_found", 85)
        # Batch insert all image records
        if all_image_records:
            await progress_tracker.update_progress(menu_id, "saving_images", 90)
            await async_supabase_client.table_insert("item_images", all_image_records)
        
        # Update menu status to completed
        await progress_tracker.update_progress(menu_id, "finalizing", 95)
        await async_supabase_client.table_update("menus", {
            "status": "completed",
            "title": menu_title
        }, eq={"id": menu_id})
        
        # Deduct credits
        await deduct_user_credits(current_user["id"], credits=1)
        
        # Mark progress as complete
        await progress_tracker.complete_task(menu_id, success=True)
        
        total_time = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"Successfully processed menu {menu_id} with {len(menu_items)} items in {total_time:.2f}s")
        
        return MenuResponse(
            success=True,
            message="Menu processed successfully",
            menu_id=menu_id,
            title=menu_title,
            items=menu_items,
            credits_remaining=current_user["credits"] - 1
        )
        
    except HTTPException:
        await progress_tracker.complete_task(menu_id, success=False)
        raise
    except Exception as e:
        total_time = (datetime.utcnow() - start_time).total_seconds()
        logger.error(f"Error processing menu {menu_id} after {total_time:.2f}s: {str(e)}", exc_info=True)
        
        # Mark progress as failed
        await progress_tracker.complete_task(menu_id, success=False)
        
        # Update menu status to failed
        try:
            await async_supabase_client.table_update("menus", {
                "status": "failed",
                "title": menu_title
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
            item_images = item.get("item_images", [])
            images = [img["image_url"] for img in item_images]
            
            # Log image retrieval for debugging
            if item_images:
                logger.info(f"Retrieved {len(item_images)} image(s) for item '{item['item_name']}': {images}")
            else:
                logger.warning(f"No images found in database for item '{item['item_name']}'")
            
            items.append({
                "id": item["id"],
                "name": item["item_name"],
                "description": item["description"],
                "price": item["price"],
                "images": images
            })
        
        resolved_title = menu_data.get("title") or menu_data.get("name") or "Uploaded Menu"

        return {
            "id": menu_data["id"],
            "status": menu_data["status"],
            "processed_at": menu_data["processed_at"],
            "title": resolved_title,
            "name": resolved_title,
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
            title_value = menu.get("title") or menu.get("name") or "Uploaded Menu"
            menus.append({
                "id": menu["id"],
                "title": title_value,
                "name": title_value,
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

@router.get("/user/latest")
async def get_latest_user_menu(
    current_user: Dict = Depends(get_current_user),
    limit: int = Query(1, ge=1, le=10)
):
    """Get the most recently processed menu entries for the current user"""
    try:
        menus_response = await async_supabase_client.table_select(
            "menus",
            "id, status, processed_at, title",
            eq={"user_id": current_user["id"]},
            order={"processed_at": True},
            limit=limit
        )

        menu_records = getattr(menus_response, "data", None) or []
        simplified_records = []
        for record in menu_records:
            menu_id = record.get("id")
            if not menu_id:
                continue
            menu_title_value = (
                record.get("title")
                or record.get("restaurant_name")
                or record.get("name")
                or "Uploaded Menu"
            )
            simplified_records.append({
                "id": menu_id,
                "title": menu_title_value,
                "name": menu_title_value,
                "restaurant_name": menu_title_value,
                "status": record.get("status"),
                "processed_at": record.get("processed_at"),
            })

        response_payload = {
            "menus": simplified_records,
            "menu": simplified_records[0] if simplified_records else None
        }
        return response_payload

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching latest menu for user {current_user['id']}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch latest menu"
        )


@router.websocket("/ws/progress/{menu_id}")
async def websocket_progress(websocket: WebSocket, menu_id: str):
    """WebSocket endpoint for real-time progress updates"""
    await websocket.accept()
    logger.info(f"WebSocket connection established for menu {menu_id}")
    
    async def send_progress(data: Dict[str, any]):
        """Callback to send progress data through WebSocket"""
        try:
            await websocket.send_json({
                "menu_id": menu_id,
                "status": data.get("status"),
                "stage": data.get("stage"),
                "progress": data.get("progress"),
                "message": data.get("message"),
                "estimated_time_remaining": data.get("estimated_time_remaining", 0),
                "item_count": data.get("item_count", 0),
                "menu_title": data.get("menu_title")
            })
        except Exception as e:
            logger.error(f"Error sending WebSocket message: {e}")
    
    try:
        # Subscribe to progress updates
        await progress_tracker.subscribe(menu_id, send_progress)
        
        # Send initial progress if available
        current_progress = await progress_tracker.get_progress(menu_id)
        if current_progress:
            await send_progress(current_progress)
        
        # Keep connection alive
        while True:
            try:
                # Wait for client messages (ping/pong)
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text("pong")
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                break
                
    finally:
        # Unsubscribe when connection closes
        await progress_tracker.unsubscribe(menu_id, send_progress)
        logger.info(f"WebSocket connection closed for menu {menu_id}")

@router.get("/progress/{menu_id}")
async def get_menu_progress(
    menu_id: str,
    current_user: Dict = Depends(get_current_user)
):
    """Get current progress for a menu processing task"""
    progress = await progress_tracker.get_progress(menu_id)
    
    if not progress:
        # Check if menu exists and get its status
        try:
            menu_response = await async_supabase_client.table_select(
                "menus",
                "id, status, title",
                eq={"id": menu_id, "user_id": current_user["id"]},
                single=True
            )
            
            if not menu_response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Menu not found"
                )
            
            # Return completed status from database
            resolved_title = menu_response.data.get("title") or "Uploaded Menu"
            return {
                "menu_id": menu_id,
                "status": menu_response.data["status"],
                "progress": 100 if menu_response.data["status"] == "completed" else 0,
                "message": {"text": "Menu processing completed", "emoji": "✅"},
                "menu_title": resolved_title
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error checking menu status: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to get menu progress"
            )
    
    return progress
