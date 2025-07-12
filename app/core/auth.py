# app/core/auth.py
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from typing import Optional, Dict
import logging
import os
from datetime import datetime

from app.core.supabase_client import supabase_client

logger = logging.getLogger(__name__)

security = HTTPBearer()

class AuthError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )

def decode_jwt(token: str) -> Dict:
    """Decode and verify JWT token from Supabase"""
    try:
        # Get the JWT secret from Supabase settings
        jwt_secret = os.getenv("SUPABASE_JWT_SECRET", os.getenv("SUPABASE_ANON_KEY"))
        
        # Decode the token
        payload = jwt.decode(
            token,
            jwt_secret,
            algorithms=["HS256"],
            options={"verify_aud": False}  # Supabase doesn't always include aud
        )
        
        # Check if token is expired
        if "exp" in payload:
            exp_timestamp = payload["exp"]
            if datetime.utcnow().timestamp() > exp_timestamp:
                raise AuthError("Token has expired")
        
        return payload
    except JWTError as e:
        logger.error(f"JWT decode error: {str(e)}")
        raise AuthError("Invalid authentication token")
    except Exception as e:
        logger.error(f"Unexpected auth error: {str(e)}")
        raise AuthError("Authentication failed")

async def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)) -> Dict:
    """Get current user from JWT token"""
    token = credentials.credentials
    
    try:
        # Decode the JWT token
        payload = decode_jwt(token)
        
        # Get user ID from token
        user_id = payload.get("sub")
        if not user_id:
            raise AuthError("Invalid token: no user ID")
        
        # Verify user exists in database
        response = supabase_client.table("users").select("*").eq("id", user_id).single().execute()
        
        if not response.data:
            raise AuthError("User not found")
        
        user = response.data
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