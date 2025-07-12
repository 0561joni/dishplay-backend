from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, status
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
from typing import Optional
import os
import sys
from dotenv import load_dotenv

# Debug: Print current directory and Python path
print(f"Current working directory: {os.getcwd()}")
print(f"Script location: {os.path.abspath(__file__)}")
print(f"Directory contents: {os.listdir('.')}")

# Add the current directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

print(f"Python path: {sys.path}")
print(f"Looking for app directory in: {current_dir}")
print(f"App directory exists: {os.path.exists(os.path.join(current_dir, 'app'))}")

# Now import our modules
try:
    from app.routers import auth, menu, user
    from app.core.logging import setup_logging
    from app.core.supabase_client import supabase_client
except ImportError as e:
    print(f"Import error: {e}")
    print(f"Directory structure:")
    for root, dirs, files in os.walk("."):
        level = root.replace(".", "", 1).count(os.sep)
        indent = " " * 2 * level
        print(f"{indent}{os.path.basename(root)}/")
        subindent = " " * 2 * (level + 1)
        for file in files:
            print(f"{subindent}{file}")
    
    # More specific checks
    print("\nChecking app structure:")
    app_path = os.path.join(current_dir, 'app')
    print(f"app/ contents: {os.listdir(app_path) if os.path.exists(app_path) else 'NOT FOUND'}")
    
    core_path = os.path.join(app_path, 'core')
    print(f"app/core/ contents: {os.listdir(core_path) if os.path.exists(core_path) else 'NOT FOUND'}")
    
    # Check if __init__.py files exist
    print(f"\nChecking __init__.py files:")
    print(f"app/__init__.py exists: {os.path.exists(os.path.join(app_path, '__init__.py'))}")
    print(f"app/core/__init__.py exists: {os.path.exists(os.path.join(core_path, '__init__.py'))}")
    
    # Check if supabase_client.py exists
    supabase_client_path = os.path.join(core_path, 'supabase_client.py')
    print(f"app/core/supabase_client.py exists: {os.path.exists(supabase_client_path)}")
    
    raise

# Load environment variables
load_dotenv()

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
        response = supabase_client.table("users").select("id").limit(1).execute()
        logger.info("Successfully connected to Supabase")
    except Exception as e:
        logger.error(f"Failed to connect to Supabase: {str(e)}")
        raise RuntimeError(f"Failed to connect to Supabase: {str(e)}")
    
    yield
    
    logger.info("Shutting down DishPlay API server...")

# Create FastAPI app
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
        response = supabase_client.table("users").select("id").limit(1).execute()
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

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=os.getenv("ENVIRONMENT", "production") == "development"
    )
