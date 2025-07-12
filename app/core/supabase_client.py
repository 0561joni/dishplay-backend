# app/core/supabase_client.py
from supabase import create_client, Client
import os
import logging

logger = logging.getLogger(__name__)

# Initialize Supabase client
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_ANON_KEY")

if not supabase_url or not supabase_key:
    logger.error("Supabase credentials not found in environment variables")
    raise ValueError("Supabase credentials not configured")

supabase_client: Client = create_client(supabase_url, supabase_key)

# Export the client
__all__ = ["supabase_client"]
