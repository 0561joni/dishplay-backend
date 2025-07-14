# app/core/cache.py
from typing import Any, Optional, Dict, Tuple
import time
import logging
from functools import wraps
import asyncio

logger = logging.getLogger(__name__)

class InMemoryCache:
    """Simple in-memory cache with TTL support"""
    
    def __init__(self):
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._lock = asyncio.Lock()
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired"""
        async with self._lock:
            if key in self._cache:
                value, expiry = self._cache[key]
                if time.time() < expiry:
                    logger.debug(f"Cache hit for key: {key}")
                    return value
                else:
                    # Remove expired entry
                    del self._cache[key]
                    logger.debug(f"Cache expired for key: {key}")
            logger.debug(f"Cache miss for key: {key}")
            return None
    
    async def set(self, key: str, value: Any, ttl: int = 300):
        """Set value in cache with TTL (default 5 minutes)"""
        async with self._lock:
            expiry = time.time() + ttl
            self._cache[key] = (value, expiry)
            logger.debug(f"Cached key: {key} with TTL: {ttl}s")
    
    async def delete(self, key: str):
        """Delete key from cache"""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                logger.debug(f"Deleted cache key: {key}")
    
    async def clear(self):
        """Clear all cache entries"""
        async with self._lock:
            self._cache.clear()
            logger.debug("Cleared all cache entries")
    
    async def cleanup_expired(self):
        """Remove all expired entries"""
        async with self._lock:
            current_time = time.time()
            expired_keys = [
                key for key, (_, expiry) in self._cache.items() 
                if current_time >= expiry
            ]
            for key in expired_keys:
                del self._cache[key]
            if expired_keys:
                logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")

# Global cache instance
user_cache = InMemoryCache()

def cache_user_data(ttl: int = 300):
    """Decorator to cache user data"""
    def decorator(func):
        @wraps(func)
        async def wrapper(user_id: str, *args, **kwargs):
            # Generate cache key
            cache_key = f"user:{user_id}"
            
            # Try to get from cache
            cached_data = await user_cache.get(cache_key)
            if cached_data is not None:
                return cached_data
            
            # Call the original function
            result = await func(user_id, *args, **kwargs)
            
            # Cache the result
            if result is not None:
                await user_cache.set(cache_key, result, ttl)
            
            return result
        return wrapper
    return decorator

# Background task to periodically clean up expired entries
async def cache_cleanup_task():
    """Periodically clean up expired cache entries"""
    while True:
        try:
            await asyncio.sleep(600)  # Run every 10 minutes
            await user_cache.cleanup_expired()
        except Exception as e:
            logger.error(f"Error in cache cleanup task: {str(e)}")

__all__ = ["user_cache", "cache_user_data", "cache_cleanup_task"]