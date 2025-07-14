# app/core/supabase_client.py
from supabase import create_client, Client
from supabase.lib.client_options import ClientOptions
import os
import logging
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

# Don't initialize at module level
_supabase_client: Optional[Client] = None
_http_client: Optional[httpx.AsyncClient] = None

def get_http_client() -> httpx.AsyncClient:
    """Get or create HTTP client with connection pooling"""
    global _http_client
    
    if _http_client is None:
        # Configure connection pooling
        limits = httpx.Limits(
            max_keepalive_connections=20,  # Number of connections to keep alive
            max_connections=100,           # Maximum number of connections
            keepalive_expiry=30.0         # How long to keep connections alive (seconds)
        )
        
        # Create async client with connection pooling
        _http_client = httpx.AsyncClient(
            limits=limits,
            timeout=httpx.Timeout(
                connect=10.0,   # 10 seconds to establish connection
                read=60.0,      # 60 seconds to read response
                write=10.0,     # 10 seconds to write request
                pool=5.0        # 5 seconds to get connection from pool
            ),
            http2=True  # Enable HTTP/2 for better performance
        )
        logger.info("Initialized HTTP client with connection pooling")
    
    return _http_client

def get_supabase_client() -> Client:
    """Get or create Supabase client with connection pooling"""
    global _supabase_client
    
    if _supabase_client is None:
        supabase_url = os.getenv("SUPABASE_URL")
        # Use service role key for backend operations
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
        
        if not supabase_url or not supabase_key:
            logger.error("Supabase credentials not found in environment variables")
            raise ValueError("Supabase credentials not configured")
        
        try:
            # Create client with minimal configuration to avoid conflicts
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

# Cleanup function for graceful shutdown
async def close_connections():
    """Close HTTP client connections on application shutdown"""
    global _http_client
    if _http_client:
        await _http_client.aclose()
        _http_client = None
        logger.info("Closed HTTP client connections")

__all__ = ["supabase_client", "get_supabase_client", "close_connections"]