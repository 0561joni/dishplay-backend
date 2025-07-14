from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, status
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
from typing import Optional
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add the current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.routers import auth, menu, user
from app.core.logging import setup_logging
from app.core.supabase_client import get_supabase_client

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown"""
    logger.info("Starting DishPlay API server...")
    
    # Verify required environment variables
    required_vars = [
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "OPENAI_API_KEY",
        "GOOGLE_CSE_API_KEY",
        "GOOGLE_CSE_ID"
    ]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing_vars)}")
    
    logger.info("All required environment variables are present")
    
    # Test Supabase connection
    try:
        # Simple health check query
        client = get_supabase_client()
        response = client.table("users").select("id").limit(1).execute()
        logger.info("Successfully connected to Supabase")
    except Exception as e:
        logger.error(f"Failed to connect to Supabase: {str(e)}")
        raise RuntimeError(f"Failed to connect to Supabase: {str(e)}")
    
    yield
    
    logger.info("Shutting down DishPlay API server...")

# Create FastAPI app with lifespan
app = FastAPI(
    title="DishPlay API",
    description="Backend API for DishPlay menu digitization application",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS - you can adjust these settings based on your frontend domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(menu.router, prefix="/api/menu", tags=["Menu"])
app.include_router(user.router, prefix="/api/user", tags=["User"])

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Welcome to DishPlay API",
        "version": "1.0.0",
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    try:
        # Test database connection
        client = get_supabase_client()
        response = client.table("users").select("id").limit(1).execute()
        db_status = "healthy"
    except Exception as e:
        logger.error(f"Database health check failed: {str(e)}")
        db_status = "unhealthy"
    
    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "services": {
            "api": "healthy",
            "database": db_status
        }
    }

# This is important - it needs to be at module level for uvicorn to find it
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=os.getenv("ENVIRONMENT", "production") == "development"
    )
