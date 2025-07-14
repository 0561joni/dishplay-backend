# app/core/auth.py
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict
import logging
import os
from datetime import datetime
import requests

from .supabase_client import supabase_client

logger = logging.getLogger(__name__)

security = HTTPBearer()

class AuthError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )

def verify_token_with_supabase(token: str) -> Dict:
    """Verify token directly with Supabase API using requests"""
    supabase_url = os.getenv("SUPABASE_URL")
    anon_key = os.getenv("SUPABASE_ANON_KEY")
    
    if not supabase_url or not anon_key:
        logger.error("Missing Supabase configuration")
        raise AuthError("Server configuration error")
    
    try:
        # Make a synchronous request to Supabase
        response = requests.get(
            f"{supabase_url}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": anon_key
            },
            timeout=10
        )
        
        logger.info(f"Supabase auth response status: {response.status_code}")
        
        if response.status_code != 200:
            logger.error(f"Supabase auth failed: {response.text}")
            raise AuthError("Invalid authentication token")
        
        return response.json()
        
    except requests.RequestException as e:
        logger.error(f"Request to Supabase failed: {str(e)}")
        raise AuthError("Failed to verify token")

async def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)) -> Dict:
    """Get current user from JWT token"""
    token = credentials.credentials
    
    try:
        # Verify token with Supabase
        auth_data = verify_token_with_supabase(token)
        
        user_id = auth_data.get("id")
        email = auth_data.get("email", "")
        
        if not user_id:
            raise AuthError("Invalid token data")
        
        logger.info(f"Successfully verified user: {user_id} ({email})")
        
        # Get additional user data from the users table
        try:
            # Don't chain .single().execute() - execute first, then get single result
            user_response = supabase_client.table("users").select("*").eq("id", user_id).execute()
            
            if user_response.data and len(user_response.data) > 0:
                user = user_response.data[0]
                logger.info(f"Found existing user record with {user.get('credits', 0)} credits")
            else:
                raise Exception("No user record found")
                
        except Exception as e:
            # If user doesn't exist in our table, create them
            logger.info(f"Creating new user record for {user_id}: {str(e)}")
            
            user_data = {
                "id": user_id,
                "email": email,
                "credits": 10,  # Default credits for new users
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
            
            try:
                supabase_client.table("users").insert(user_data).execute()
                user = user_data
            except Exception as insert_error:
                logger.error(f"Failed to create user record: {str(insert_error)}")
                # If insert fails (maybe user exists), try to fetch again
                user_response = supabase_client.table("users").select("*").eq("id", user_id).single().execute()
                if user_response.data:
                    user = user_response.data
                else:
                    raise AuthError("Failed to create or fetch user record")
        
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
        response = supabase_client.table("users").select("credits").eq("id", user_id).execute()
        
        if not response.data or len(response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
            
        current_credits = response.data[0].get("credits", 0)
        
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
