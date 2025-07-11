# main.py (FastAPI Application)

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, status, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
import base64
import os
import httpx  # For async HTTP requests
import asyncio  # For concurrent tasks
import json
from io import BytesIO
from PIL import Image
import pytesseract

# Supabase client (you'll initialize this properly )
from supabase import create_client, Client

# --- Configuration (from environment variables) ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_CSE_API_KEY = os.getenv("GOOGLE_CSE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID") # Your Custom Search Engine ID
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI(
    title="MenuLens Backend API",
    description="API for processing menu images and finding associated food images.",
    version="0.1.0"
)

# Allow cross-origin requests for browser-based clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Models for Request/Response Bodies ---

class UserProfile(BaseModel):
    first_name: str
    last_name: str
    email: str
    birthday: str # Consider using date type if frontend sends ISO format
    gender: str
    credits: int

class MenuItem(BaseModel):
    item_name: str
    description: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    images: List[str] = [] # List of image URLs

class ProcessedMenuResponse(BaseModel):
    menu_id: str
    items: List[MenuItem]
    credits_remaining: int

# --- Dependency for User Authentication (using Supabase Auth) ---
async def get_current_user(request: Request):
    """Validate JWT from Authorization header and fetch user profile."""
    try:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

        token = auth_header.split(" ")[1]

        try:
            user_response = supabase.auth.get_user(token)
            user_id = user_response.user.id
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from e

        response = supabase.from_("users").select("*").eq("id", user_id).single().execute()
        user_data = response.data
        if not user_data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        return user_data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Authentication failed: {e}")


# --- Helper Functions for API Calls ---

async def call_openai_gpt4o(image_base64: str) -> List[dict]:
    """
    Calls OpenAI GPT-4o to extract menu items from an image.
    Returns a list of dictionaries, each representing a menu item.
    """
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
                    {"type": "text", "text": """
                    Extract all menu items from this image. For each item, provide its name, description (if available), and price (if available).
                    If a price is found, also try to identify its currency symbol.
                    Return the data as a JSON array of objects, where each object has 'name', 'description', 'price', and 'currency' fields.
                    Example format:
                    [
                        {"name": "Spaghetti Carbonara", "description": "Classic Italian pasta with eggs, cheese, pancetta, and black pepper.", "price": 15.50, "currency": "€"},
                        {"name": "Margherita Pizza", "description": "Tomato, mozzarella, basil.", "price": 12.00, "currency": "€"}
                    ]
                    If a description or price is not found, set it to null.
                    """},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 4000 # Adjust as needed
    }

    async with httpx.AsyncClient(timeout=60.0 ) as client: # Increased timeout for image processing
        try:
            response = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload )
            response.raise_for_status() # Raise an exception for HTTP errors
            
            content = response.json()["choices"][0]["message"]["content"]
            # OpenAI might return markdown code block, try to parse it
            if content.startswith("```json") and content.endswith("```"):
                content = content[7:-3].strip()
            
            return json.loads(content) # Parse the JSON string
        except httpx.HTTPStatusError as e:
            print(f"OpenAI API HTTP error: {e.response.status_code} - {e.response.text}" )
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error communicating with OpenAI API.")
        except json.JSONDecodeError:
            print(f"Failed to decode JSON from OpenAI: {content}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="OpenAI returned malformed JSON.")
        except Exception as e:
            print(f"An unexpected error occurred with OpenAI API: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred during menu extraction.")


async def call_openai_parse_text(text: str) -> List[dict]:
    """Use OpenAI to parse raw OCR text into structured menu items."""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}"
    }
    prompt = (
        "Extract all menu items from the following text.\n"
        "For each item, provide its name, description if available, price if available, "
        "and currency symbol if present. Return the data as JSON in the format:\n"
        "[{'name': 'Item', 'description': 'desc', 'price': 12.5, 'currency': '$'}]"
    )
    payload = {
        "model": "gpt-4o",
        "messages": [
            {"role": "user", "content": f"{prompt}\n\n{text}"}
        ],
        "max_tokens": 4000
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            if content.startswith("```json") and content.endswith("```"):
                content = content[7:-3].strip()
            return json.loads(content)
        except Exception as e:
            print(f"OpenAI parsing failed: {e}")
            raise


async def extract_menu_items(image_bytes: bytes) -> List[dict]:
    """Extract menu items using open source OCR with OpenAI fallback."""
    try:
        loop = asyncio.get_running_loop()
        text = await loop.run_in_executor(None, lambda: pytesseract.image_to_string(Image.open(BytesIO(image_bytes))))
        if not text.strip():
            raise ValueError("OCR returned empty text")
        return await call_openai_parse_text(text)
    except Exception as e:
        print(f"OCR failed, falling back to OpenAI vision: {e}")
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")
        return await call_openai_gpt4o(image_base64)


async def search_google_images(query: str) -> List[str]:
    """
    Searches Google Custom Search for images based on a query.
    Returns a list of image URLs.
    """
    search_url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": GOOGLE_CSE_API_KEY,
        "cx": GOOGLE_CSE_ID,
        "q": query,
        "searchType": "image",
        "num": 3, # Request 3 images
        "imgSize": "large", # Prefer large images
        "fileType": "jpg|png", # Prefer common image types
        "safe": "active" # Safe search
    }

    async with httpx.AsyncClient( ) as client:
        try:
            response = await client.get(search_url, params=params)
            response.raise_for_status()
            data = response.json()
            
            image_urls = []
            if "items" in data:
                for item in data["items"]:
                    if "link" in item:
                        image_urls.append(item["link"])
            return image_urls
        except httpx.HTTPStatusError as e:
            print(f"Google CSE API HTTP error: {e.response.status_code} - {e.response.text}" )
            # Do not raise HTTPException, as per requirement to proceed without images
            return []
        except Exception as e:
            print(f"An unexpected error occurred with Google CSE API: {e}")
            return []

# --- API Endpoints ---

@app.get("/")
@app.get("/api")
async def read_root():
    return {"message": "Welcome to MenuLens API!"}

@app.post("/menu/upload", response_model=ProcessedMenuResponse)
@app.post("/api/menu/upload", response_model=ProcessedMenuResponse)
async def upload_menu(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user) # Authenticated user
):
    user_id = current_user['id']
    user_credits = current_user['credits']

    # Define cost per menu processing
    COST_PER_MENU = 10 # Example cost

    if user_credits < COST_PER_MENU:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="Insufficient credits.")

    # 1. Read image bytes
    contents = await file.read()

    # 2. Extract menu items using OCR with OpenAI fallback
    try:
        extracted_items_raw = await extract_menu_items(contents)
    except HTTPException as e:
        raise e # Re-raise HTTP exceptions from helper
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to extract menu items: {e}")

    processed_items: List[MenuItem] = []
    image_search_tasks = []

    # Prepare concurrent image search tasks
    for item_raw in extracted_items_raw:
        item_name = item_raw.get("name")
        if item_name:
            # Create a task for each image search
            image_search_tasks.append(search_google_images(f"{item_name} food"))
        else:
            # If no name, add a placeholder or skip
            processed_items.append(MenuItem(item_name="Unknown Item", description=item_raw.get("description"), price=item_raw.get("price"), currency=item_raw.get("currency")))
            
    # Run all image search tasks concurrently
    image_results = await asyncio.gather(*image_search_tasks)

    # Combine extracted items with image results
    item_index = 0
    for item_raw in extracted_items_raw:
        item_name = item_raw.get("name")
        if item_name:
            images = image_results[item_index]
            processed_items.append(MenuItem(
                item_name=item_name,
                description=item_raw.get("description"),
                price=item_raw.get("price"),
                currency=item_raw.get("currency"),
                images=images
            ))
            item_index += 1
        # else: already handled above if no name

    # 3. Store menu and items in Supabase
    try:
        # Create a new menu entry
        menu_response = supabase.from_('menus').insert({
            'user_id': user_id,
            'status': 'completed' # Or 'failed' if extraction failed
        }).execute()
        menu_id = menu_response.data[0]['id']

        # Prepare menu items for batch insert
        items_to_insert = []
        for item in processed_items:
            items_to_insert.append({
                'menu_id': menu_id,
                'item_name': item.item_name,
                'description': item.description,
                'price': item.price,
                'currency': item.currency
            })
        
        # Insert menu items
        menu_items_response = supabase.from_('menu_items').insert(items_to_insert).execute()
        
        # Insert images for each item (this could be optimized for batch insert too)
        for i, item_data in enumerate(menu_items_response.data):
            item_db_id = item_data['id']
            images_to_insert = []
            for img_url in processed_items[i].images:
                images_to_insert.append({
                    'menu_item_id': item_db_id,
                    'image_url': img_url,
                    'source': 'google_cse'
                })
            if images_to_insert:
                supabase.from_('item_images').insert(images_to_insert).execute()

        # Deduct credits
        new_credits = user_credits - COST_PER_MENU
        supabase.from_('users').update({'credits': new_credits}).eq('id', user_id).execute()

    except Exception as e:
        print(f"Database error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save menu data.")

    return ProcessedMenuResponse(
        menu_id=menu_id,
        items=processed_items,
        credits_remaining=new_credits
    )

# --- User Profile Endpoints ---

@app.get("/user/profile", response_model=UserProfile)
@app.get("/api/user/profile", response_model=UserProfile)
async def get_user_profile(current_user: dict = Depends(get_current_user)):
    """Return the authenticated user's profile."""
    return UserProfile(
        first_name=current_user['first_name'],
        last_name=current_user['last_name'],
        email=current_user['email'],
        birthday=str(current_user['birthday']),  # Ensure date is string for Pydantic
        gender=current_user['gender'],
        credits=current_user['credits'],
    )

@app.post("/user/profile", response_model=UserProfile)
@app.post("/api/user/profile", response_model=UserProfile)
async def post_user_profile(current_user: dict = Depends(get_current_user)):
    """Return the authenticated user's profile via POST."""
    return UserProfile(
        first_name=current_user['first_name'],
        last_name=current_user['last_name'],
        email=current_user['email'],
        birthday=str(current_user['birthday']),  # Ensure date is string for Pydantic
        gender=current_user['gender'],
        credits=current_user['credits'],
    )

# Add more endpoints for user updates, credit purchase (future), etc.

# --- Authentication Endpoints (Simplified - Supabase handles most of this) ---
# You'd typically use Supabase's client-side SDK for auth,
# but if you need server-side auth flows, here's a placeholder.

# @app.post("/auth/signup")
# async def signup(user_data: dict): # Use a Pydantic model for user_data
#     try:
#         # Supabase handles user creation and email verification
#         response = supabase.auth.sign_up(email=user_data['email'], password=user_data['password'])
#         # Then insert additional profile data into your 'users' table
#         supabase.from_('users').insert({
#             'id': response.user.id,
#             'email': response.user.email,
#             'first_name': user_data.get('first_name'),
#             # ... other fields
#             'credits': 50 # Initial credits
#         }).execute()
#         return {"message": "User signed up successfully. Check email for verification."}
#     except Exception as e:
#         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

# @app.post("/auth/login")
# async def login(credentials: dict): # Use a Pydantic model for credentials
#     try:
#         response = supabase.auth.sign_in_with_password(email=credentials['email'], password=credentials['password'])
#         return {"access_token": response.session.access_token, "token_type": "bearer"}
#     except Exception as e:
#         raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

# To run locally:
# pip install fastapi uvicorn python-dotenv openai google-api-python-client supabase-py httpx
# Create a .env file:
# OPENAI_API_KEY="sk-..."
# GOOGLE_CSE_API_KEY="AIza..."
# GOOGLE_CSE_ID="your_cse_id"
# SUPABASE_URL="https://your-project-ref.supabase.co"
# SUPABASE_KEY="your_anon_public_key"
#
# uvicorn main:app --reload
