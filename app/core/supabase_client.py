# app/core/supabase_client.py
from supabase import create_client, Client
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Don't initialize at module level
_supabase_client: Optional[Client] = None

def get_supabase_client() -> Client:
    """Get or create Supabase client"""
    global _supabase_client
    
    if _supabase_client is None:
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_ANON_KEY")
        
        if not supabase_url or not supabase_key:
            logger.error("Supabase credentials not found in environment variables")
            raise ValueError("Supabase credentials not configured")
        
        try:
            _supabase_client = create_client(supabase_url, supabase_key)
            logger.info("Successfully initialized Supabase client")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
            raise
    
    return _supabase_client

# For backward compatibility, create a property that initializes on first access
class SupabaseClientProxy:
    @property
    def table(self):
        return get_supabase_client().table
    
    @property
    def auth(self):
        return get_supabase_client().auth
    
    @property
    def storage(self):
        return get_supabase_client().storage
    
    @property
    def functions(self):
        return get_supabase_client().functions

# Export a proxy object
supabase_client = SupabaseClientProxy()

__all__ = ["supabase_client", "get_supabase_client"]
