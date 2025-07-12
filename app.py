# app.py (FastAPI Application)

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, status, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
import base64
import os
import httpx
import asyncio
import json
from io import BytesIO
from PIL import Image
import pytesseract
import jwt
from datetime import datetime, timedelta
import logging

# Supabase client
from supabase import create_client, Client

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Configuration (from environment variables) ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_CSE_API_KEY = os.getenv("GOOGLE_CSE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")  # Use ANON key, not service key
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")  # For admin operations if needed

# Validate required environment variables
required_env_vars = {
    "OPENAI_API_KEY": OPENAI_API_KEY,
    "GOOGLE_CSE_API_KEY": GOOGLE_CSE_API_KEY,
    "GOOGLE_CSE_ID": GOOGLE_CSE_ID,
    "SUPABASE_URL": SUPABASE_URL,
    "SUPABASE_ANON_KEY": SUPABASE_ANON_KEY,
}

missing_vars = [var for var, value in required_env_vars.items() if not value]
if missing_vars:
    raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

# Initialize Supabase client with anon key (for public operations)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

app = FastAPI(
    title="MenuLens Backend API",
    description="API for processing menu images and finding associated food images.",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = datetime.utcnow()
    
    # Log request
    logger.info(f"Request: {request.method} {request.url}")
    logger.info(f"Headers: {dict(request.headers)}")
    
    response = await call_next(request)
    
    # Log response
    process_time = (datetime.utcnow() - start_time).total_seconds()
    logger.info(f"Response: {response.status_code} (took {process_time:.2f}s)")
    
    return response

# Startup event
@app.on_event("startup")
async def startup_event():
    logger.info("MenuLens API starting up...")
    logger.info(f"Supabase URL: {SUPABASE_URL}")
    logger.info(f"OpenAI API configured: {'Yes' if OPENAI_API_KEY else 'No'}")
    logger.info(f"Google CSE configured: {'Yes' if GOOGLE_CSE_API_KEY else 'No'}")
    
    # Log all routes
    routes = []
    for route in app.routes:
        if hasattr(route, 'methods') and hasattr(route, 'path'):
            routes.append(f"{list(route.methods)} {route.path}")
    logger.info(f"Available routes: {routes}")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("MenuLens API shutting down...")

# --- Pydantic Models ---

class UserProfile(BaseModel):
    first_name: str
    last_name: str
    email: str
    birthday: str
    gender: str
    credits: int

    @validator('email')
    def validate_email(cls, v):
        if '@' not in v:
            raise ValueError('Invalid email format')
        return v

class MenuItem(BaseModel):
    item_name: str
    description: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    images: List[str] = []

class ProcessedMenuResponse(BaseModel):
    menu_id: str
    items: List[MenuItem]
    credits_remaining: int

class ErrorResponse(BaseModel):
    detail: str
    error_code: Optional[str] = None

# --- Authentication Functions ---

def verify_jwt_token(token: str) -> Dict[str, Any]:
    """Verify JWT token and return payload."""
    try:
        # Get JWT secret from Supabase (this should be your JWT secret)
        # For development, you can skip verification, but for production, you need the secret
        
        # Option 1: Skip verification for development (NOT RECOMMENDED for production)
        payload = jwt.decode(token, options={"verify_signature": False})
        
        # Option 2: Verify with secret (RECOMMENDED for production)
        # Replace 'your-jwt-secret' with your actual Supabase JWT secret
        # payload = jwt.decode(token, 'your-jwt-secret', algorithms=['HS256'])
        
        # Check if token is expired
        if 'exp' in payload:
            exp_timestamp = payload['exp']
            if datetime.utcnow().timestamp() > exp_timestamp:
                raise jwt.ExpiredSignatureError("Token has expired")
        
        return payload
    
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}"
        )

async def get_current_user(request: Request) -> Dict[str, Any]:
    """Get current user from JWT token."""
    try:
        # Extract token from Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing Authorization header"
            )
        
        if not auth_header.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Authorization header format"
            )
        
        token = auth_header[7:]  # Remove "Bearer " prefix
        
        # Verify JWT token
        payload = verify_jwt_token(token)
        user_id = payload.get('sub')
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user ID"
            )
        
        # Create authenticated Supabase client
        authenticated_supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
        
        # Set the session with the user's token
        try:
            # Method 1: Set session manually
            authenticated_supabase.auth.set_session(token, "")
            
            # Method 2: Alternative approach - set headers
            # authenticated_supabase.auth.set_session(access_token=token, refresh_token="")
            
        except Exception as e:
            logger.warning(f"Failed to set Supabase session: {e}")
            # Continue anyway - we'll query with the user_id directly
        
        # Query user data
        try:
            response = authenticated_supabase.from_('users').select('*').eq('id', user_id).execute()
            
            if not response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found in database"
                )
            
            user_data = response.data[0]
            logger.info(f"Successfully authenticated user: {user_data.get('email')}")
            return user_data
            
        except Exception as e:
            logger.error(f"Database query error: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch user data"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed"
        )

# --- Helper Functions ---

async def call_openai_gpt4o(image_base64: str) -> List[dict]:
    """Call OpenAI GPT-4o to extract menu items from an image."""
    if not OPENAI_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OpenAI API key not configured"
        )
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}"
    }
    
    payload = {
        "model": "gpt-4o",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": """
                        Extract all menu items from this image. For each item, provide:
                        - name: The item name
                        - description: Item description (if available)
                        - price: Numeric price (if available)
                        - currency: Currency symbol (if available)
                        
                        Return as a JSON array of objects. Example:
                        [
                            {"name": "Spaghetti Carbonara", "description": "Classic Italian pasta", "price": 15.50, "currency": "€"},
                            {"name": "Margherita Pizza", "description": "Tomato, mozzarella, basil", "price": 12.00, "currency": "€"}
                        ]
                        
                        If information is not available, use null for that field.
                        """
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
                    }
                ]
            }
        ],
        "max_tokens": 4000
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            
            content = response.json()["choices"][0]["message"]["content"]
            
            # Clean up markdown formatting
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            return json.loads(content)
            
        except httpx.HTTPStatusError as e:
            logger.error(f"OpenAI API error: {e.response.status_code} - {e.response.text}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OpenAI API request failed"
            )
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse OpenAI response: {content}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Invalid response from OpenAI"
            )
        except Exception as e:
            logger.error(f"OpenAI API unexpected error: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Menu extraction failed"
            )

async def call_openai_parse_text(text: str) -> List[dict]:
    """Parse OCR text using OpenAI."""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}"
    }
    
    prompt = """
    Extract menu items from this text. Return as JSON array with format:
    [{"name": "Item Name", "description": "Description", "price": 12.50, "currency": "$"}]
    Use null for missing information.
    """
    
    payload = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": f"{prompt}\n\nText:\n{text}"}],
        "max_tokens": 4000
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            
            content = response.json()["choices"][0]["message"]["content"]
            if content.startswith("```json"):
                content = content[7:-3].strip()
            
            return json.loads(content)
            
        except Exception as e:
            logger.error(f"OpenAI text parsing failed: {e}")
            raise

async def extract_menu_items(image_bytes: bytes) -> List[dict]:
    """Extract menu items using OCR with OpenAI fallback."""
    try:
        # Try OCR first
        image = Image.open(BytesIO(image_bytes))
        text = pytesseract.image_to_string(image)
        
        if text.strip():
            logger.info("Using OCR text extraction")
            return await call_openai_parse_text(text)
        else:
            raise ValueError("OCR returned empty text")
            
    except Exception as e:
        logger.info(f"OCR failed, using OpenAI vision: {e}")
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")
        return await call_openai_gpt4o(image_base64)

async def search_google_images(query: str) -> List[str]:
    """Search Google Custom Search for images."""
    if not GOOGLE_CSE_API_KEY or not GOOGLE_CSE_ID:
        logger.warning("Google CSE not configured, skipping image search")
        return []
    
    params = {
        "key": GOOGLE_CSE_API_KEY,
        "cx": GOOGLE_CSE_ID,
        "q": f"{query} food dish",
        "searchType": "image",
        "num": 3,
        "imgSize": "large",
        "fileType": "jpg,png",
        "safe": "active"
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(
                "https://www.googleapis.com/customsearch/v1",
                params=params
            )
            response.raise_for_status()
            
            data = response.json()
            return [item["link"] for item in data.get("items", [])]
            
        except Exception as e:
            logger.error(f"Google image search failed: {e}")
            return []

# --- API Endpoints ---

@app.get("/")
async def read_root():
    return {"message": "MenuLens API v1.0", "status": "healthy", "version": "1.0.0"}

@app.get("/api")
async def read_api():
    return {"message": "MenuLens API v1.0", "status": "healthy", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

@app.get("/debug/routes")
async def debug_routes():
    """Debug endpoint to list all available routes"""
    routes = []
    for route in app.routes:
        if hasattr(route, 'methods') and hasattr(route, 'path'):
            routes.append({
                "path": route.path,
                "methods": list(route.methods),
                "name": route.name
            })
    return {"routes": routes}

@app.post("/menu/upload", response_model=ProcessedMenuResponse)
async def upload_menu(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """Upload and process a menu image."""
    
    # Validate file
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an image"
        )
    
    # Check file size (10MB limit)
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large (max 10MB)"
        )
    
    user_id = current_user['id']
    user_credits = current_user['credits']
    
    # Check credits
    COST_PER_MENU = 10
    if user_credits < COST_PER_MENU:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Insufficient credits"
        )
    
    try:
        # Extract menu items
        logger.info(f"Processing menu for user {user_id}")
        extracted_items = await extract_menu_items(contents)
        
        # Search for images concurrently
        image_tasks = []
        for item in extracted_items:
            if item.get("name"):
                image_tasks.append(search_google_images(item["name"]))
        
        image_results = await asyncio.gather(*image_tasks, return_exceptions=True)
        
        # Combine results
        processed_items = []
        for i, item in enumerate(extracted_items):
            images = []
            if i < len(image_results) and not isinstance(image_results[i], Exception):
                images = image_results[i]
            
            processed_items.append(MenuItem(
                item_name=item.get("name", "Unknown Item"),
                description=item.get("description"),
                price=item.get("price"),
                currency=item.get("currency"),
                images=images
            ))
        
        # Save to database
        try:
            # Create menu entry
            menu_response = supabase.from_('menus').insert({
                'user_id': user_id,
                'status': 'completed',
                'created_at': datetime.utcnow().isoformat()
            }).execute()
            
            menu_id = menu_response.data[0]['id']
            
            # Save menu items
            items_to_insert = []
            for item in processed_items:
                items_to_insert.append({
                    'menu_id': menu_id,
                    'item_name': item.item_name,
                    'description': item.description,
                    'price': item.price,
                    'currency': item.currency
                })
            
            items_response = supabase.from_('menu_items').insert(items_to_insert).execute()
            
            # Save images
            for i, item_data in enumerate(items_response.data):
                item_id = item_data['id']
                for img_url in processed_items[i].images:
                    supabase.from_('item_images').insert({
                        'menu_item_id': item_id,
                        'image_url': img_url,
                        'source': 'google_cse'
                    }).execute()
            
            # Deduct credits
            new_credits = user_credits - COST_PER_MENU
            supabase.from_('users').update({
                'credits': new_credits
            }).eq('id', user_id).execute()
            
            logger.info(f"Successfully processed menu {menu_id} for user {user_id}")
            
            return ProcessedMenuResponse(
                menu_id=menu_id,
                items=processed_items,
                credits_remaining=new_credits
            )
            
        except Exception as e:
            logger.error(f"Database error: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save menu data"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Menu processing error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Menu processing failed"
        )

@app.get("/user/profile", response_model=UserProfile)
async def get_user_profile(current_user: dict = Depends(get_current_user)):
    """Get user profile."""
    return UserProfile(
        first_name=current_user.get('first_name', ''),
        last_name=current_user.get('last_name', ''),
        email=current_user.get('email', ''),
        birthday=str(current_user.get('birthday', '')),
        gender=current_user.get('gender', ''),
        credits=current_user.get('credits', 0),
    )

@app.post("/user/profile", response_model=UserProfile)
async def post_user_profile(current_user: dict = Depends(get_current_user)):
    """Get user profile via POST (for compatibility)."""
    return await get_user_profile(current_user)

# Add API prefix routes for compatibility
@app.get("/api/user/profile", response_model=UserProfile)
async def get_user_profile_api(current_user: dict = Depends(get_current_user)):
    return await get_user_profile(current_user)

@app.post("/api/user/profile", response_model=UserProfile)
async def post_user_profile_api(current_user: dict = Depends(get_current_user)):
    return await get_user_profile(current_user)

@app.post("/api/menu/upload", response_model=ProcessedMenuResponse)
async def upload_menu_api(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    return await upload_menu(file, current_user)

# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
