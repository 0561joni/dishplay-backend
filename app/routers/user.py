# app/routers/user.py
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict
import logging
from datetime import datetime

from app.core.auth import get_current_user
from app.core.supabase_client import supabase_client
from app.models.user import UserProfile, UserCreditsUpdate

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/profile", response_model=UserProfile)
async def get_user_profile(current_user: Dict = Depends(get_current_user)):
    """Get current user profile"""
    return UserProfile(
        id=current_user["id"],
        email=current_user["email"],
        first_name=current_user.get("first_name"),
        last_name=current_user.get("last_name"),
        birthday=current_user.get("birthday"),
        gender=current_user.get("gender"),
        credits=current_user.get("credits", 0),
        created_at=current_user.get("created_at"),
        updated_at=current_user.get("updated_at")
    )

@router.put("/profile")
async def update_user_profile(
    profile_update: Dict,
    current_user: Dict = Depends(get_current_user)
):
    """Update user profile"""
    
    # Only allow updating certain fields
    allowed_fields = ["first_name", "last_name", "birthday", "gender"]
    update_data = {k: v for k, v in profile_update.items() if k in allowed_fields}
    
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid fields to update"
        )
    
    try:
        # Add updated_at timestamp
        update_data["updated_at"] = datetime.utcnow().isoformat()
        
        response = supabase_client.table("users").update(update_data).eq("id", current_user["id"]).execute()
        
        return {"message": "Profile updated successfully"}
        
    except Exception as e:
        logger.error(f"Error updating user profile: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update profile"
        )

@router.get("/credits")
async def get_user_credits(current_user: Dict = Depends(get_current_user)):
    """Get user's current credit balance"""
    return {"credits": current_user.get("credits", 0)}

@router.put("/credits")
async def update_user_credits(
    credits_update: UserCreditsUpdate,
    current_user: Dict = Depends(get_current_user)
):
    """Update user credits (admin only - implement proper authorization)"""
    
    # TODO: Add proper admin authorization check
    # For now, users can't update their own credits through this endpoint
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Not authorized to update credits"
    )