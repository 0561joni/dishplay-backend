# app/core/auth.py
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict
import logging
import os
from datetime import datetime
import requests  # Using requests directly without session for token verification

from .async_supabase import async_supabase_client
from .cache import user_cache

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
    
    logger.info(f"Verifying token with Supabase URL: {supabase_url}")
    
    if not supabase_url or not anon_key:
        logger.error(f"Missing Supabase configuration - URL: {supabase_url}, Key exists: {bool(anon_key)}")
        raise AuthError("Server configuration error")
    
    try:
        # Make a synchronous request to Supabase
        # Using a fresh request without session to ensure complete isolation
        auth_url = f"{supabase_url}/auth/v1/user"
        logger.info(f"Making request to: {auth_url}")
        
        # Explicitly set headers to ensure Authorization header is always included
        headers = {
            "Authorization": f"Bearer {token}",
            "apikey": anon_key,
            "Content-Type": "application/json"
        }
        
        response = requests.get(
            auth_url,
            headers=headers,
            timeout=10
        )
        
        logger.info(f"Supabase auth response status: {response.status_code}")
        
        if response.status_code != 200:
            logger.error(f"Supabase auth failed with status {response.status_code}: {response.text}")
            logger.error(f"Response headers: {dict(response.headers)}")
            raise AuthError("Invalid authentication token")
        
        return response.json()
        
    except requests.RequestException as e:
        logger.error(f"Request to Supabase failed: {str(e)}")
        logger.error(f"Request URL was: {supabase_url}/auth/v1/user")
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
        
        # Check cache first
        cache_key = f"user:{user_id}"
        cached_user = await user_cache.get(cache_key)
        if cached_user:
            # Create a copy to avoid modifying cached data
            user_with_token = cached_user.copy()
            user_with_token["token"] = token  # Always use the current token
            return user_with_token
        
        # Get additional user data from the users table
        try:
            # Don't chain .single().execute() - execute first, then get single result
            user_response = await async_supabase_client.table_select("users", "*", eq={"id": user_id})
            
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
                await async_supabase_client.table_insert("users", user_data)
                user = user_data
            except Exception as insert_error:
                logger.error(f"Failed to create user record: {str(insert_error)}")
                # If insert fails (maybe user exists), try to fetch again
                user_response = await async_supabase_client.table_select("users", "*", eq={"id": user_id})
                if user_response.data and len(user_response.data) > 0:
                    user = user_response.data[0]
                else:
                    raise AuthError("Failed to create or fetch user record")
        
        user["token"] = token  # Include token for API calls
        
        # Cache user data (without token)
        user_data_to_cache = {k: v for k, v in user.items() if k != "token"}
        await user_cache.set(cache_key, user_data_to_cache, ttl=300)  # Cache for 5 minutes
        
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
        response = await async_supabase_client.table_select("users", "credits", eq={"id": user_id})
        
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
        update_response = await async_supabase_client.table_update("users", {
            "credits": new_credits,
            "updated_at": datetime.utcnow().isoformat()
        }, eq={"id": user_id})
        
        # Invalidate user cache
        await user_cache.delete(f"user:{user_id}")
        
        return {"credits": new_credits}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deducting credits: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to deduct credits"
        )
