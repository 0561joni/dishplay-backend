# app/core/auth.py
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict
import logging
import os
from datetime import datetime

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

async def verify_token_with_supabase(token: str) -> Dict:
    """Verify token using Supabase SDK's built-in method"""
    try:
        # Log token format for debugging
        if not token:
            logger.error("No token provided")
            raise AuthError("No authentication token provided")
        
        # Check if token looks like a JWT (should have 3 parts separated by dots)
        token_parts = token.split('.')
        if len(token_parts) != 3:
            logger.error(f"Invalid token format - expected 3 parts, got {len(token_parts)}")
            logger.error(f"Token preview: {token[:50]}...")
            raise AuthError("Invalid token format")
        
        # Use the async wrapper to get user from token
        logger.info("Verifying token with Supabase SDK")
        user_response = await async_supabase_client.auth_get_user(token)
        
        if not user_response or not user_response.user:
            logger.error("Invalid token - no user returned")
            raise AuthError("Invalid authentication token")
        
        # Convert the user object to a dictionary
        user_data = {
            "id": user_response.user.id,
            "email": user_response.user.email,
            "email_confirmed_at": getattr(user_response.user, 'email_confirmed_at', None),
            "created_at": getattr(user_response.user, 'created_at', None),
            "updated_at": getattr(user_response.user, 'updated_at', None),
            "role": getattr(user_response.user, 'role', None),
            "app_metadata": getattr(user_response.user, 'app_metadata', {}),
            "user_metadata": getattr(user_response.user, 'user_metadata', {})
        }
        
        logger.info(f"Successfully verified user: {user_data['id']} ({user_data['email']})")
        return user_data
        
    except AuthError:
        raise
    except Exception as e:
        logger.error(f"Token verification failed: {str(e)}")
        logger.error(f"Error type: {type(e).__name__}")
        raise AuthError("Failed to verify token")

async def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)) -> Dict:
    """Get current user from JWT token"""
    token = credentials.credentials
    
    # Log token info for debugging
    logger.info(f"Received token (first 20 chars): {token[:20] if token else 'None'}...")
    logger.info(f"Token length: {len(token) if token else 0}")
    
    try:
        # Verify token with Supabase
        auth_data = await verify_token_with_supabase(token)
        
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
