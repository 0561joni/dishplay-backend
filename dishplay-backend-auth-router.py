# app/routers/auth.py
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

class HealthCheck(BaseModel):
    status: str
    message: str

@router.get("/health", response_model=HealthCheck)
async def auth_health():
    """Check if auth service is working"""
    return HealthCheck(
        status="healthy",
        message="Authentication service is running. Auth is handled by Supabase."
    )

# Note: All authentication (login, signup, logout) is handled by Supabase on the frontend
# The backend only validates JWT tokens in the auth middleware