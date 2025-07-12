# app/core/auth.py
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict
import logging
import os
from datetime import datetime
import httpx
import json

from .supabase_client import supabase_client, get_supabase_client

logger = logging.getLogger(__name__)

security = HTTPBearer()

class AuthError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )

async def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)) -> Dict:
    """Get current user from JWT token using Supabase API"""
    token = credentials.credentials
    
    try:
        # Make a direct API call to Supabase to verify the token
        supabase_url = os.getenv("SUPABASE_URL")
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{supabase_url}/auth/v1/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "apikey": os.getenv("SUPABASE_ANON_KEY")
                }
            )
            
            logger.info(f"Supabase auth response status: {response.status_code}")
            
            if response.status_code != 200:
                logger.error(f"Supabase auth failed: {response.text}")
                raise AuthError("Invalid authentication token")
            
            auth_data = response.json()
            
            if not auth_data or "id" not in auth_data:
                raise AuthError("Invalid authentication token")
            
            user_id = auth_data["id"]
            email = auth_data.get("email", "")
            
            logger.info(f"Successfully verified user: {user_id} ({email})")
        
        # Get additional user data from the users table
        user_response = supabase_client.table("users").select("*").eq("id", user_id).single().execute()
        
        if not user_response.data:
            # If user doesn't exist in our table, create them
            user_data = {
                "id": user_id,
                "email": email,
                "credits": 10,  # Default credits for new users
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
            
            logger.info(f"Creating new user record for {user_id}")
            supabase_client.table("users").insert(user_data).execute()
            user = user_data
        else:
            user = user_response.data
        
        user["token"] = token  # Include token for API calls
        
        return user
        
    except AuthError:
        raise
    except Exception as e:
        logger.error(f"Error getting current user: {str(e)}")
        raise AuthError("Failed to authenticate user")

async def verify_user_credits(user: Dict, required_credits: int = 1) -> bool:
    """Verify user has enough credits for an operation"""
    if user.get("credits", 0) < required_credits:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient credits. Required: {required_credits}, Available: {user.get('credits', 0)}"
        )
    return True

async def deduct_user_credits(user_id: str, credits: int = 1) -> Dict:
    """Deduct credits from user account"""
    try:
        # Get current credits
        response = supabase_client.table("users").select("credits").eq("id", user_id).single().execute()
        current_credits = response.data.get("credits", 0)
        
        if current_credits < credits:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Insufficient credits"
            )
        
        # Update credits
        new_credits = current_credits - credits
        update_response = supabase_client.table("users").update({
            "credits": new_credits,
            "updated_at": datetime.utcnow().isoformat()
        }).eq("id", user_id).execute()
        
        return {"credits": new_credits}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deducting credits: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to deduct credits"
        )
