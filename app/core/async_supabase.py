# app/core/async_supabase.py
import asyncio
from functools import partial
from typing import Any, Dict, Optional
import logging

from .supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class AsyncSupabaseClient:
    """Async wrapper for Supabase client operations"""
    
    def __init__(self):
        self._client = None
        self._loop = None
    
    @property
    def client(self):
        if self._client is None:
            self._client = get_supabase_client()
        return self._client
    
    @property
    def loop(self):
        if self._loop is None:
            self._loop = asyncio.get_event_loop()
        return self._loop
    
    async def table_insert(self, table_name: str, data: Dict[str, Any]):
        """Async wrapper for table insert operations"""
        func = partial(self.client.table(table_name).insert(data).execute)
        return await self.loop.run_in_executor(None, func)
    
    async def table_update(self, table_name: str, data: Dict[str, Any], **filters):
        """Async wrapper for table update operations"""
        query = self.client.table(table_name).update(data)
        
        # Apply filters
        for key, value in filters.items():
            if key == "eq":
                for field, val in value.items():
                    query = query.eq(field, val)
        
        func = partial(query.execute)
        return await self.loop.run_in_executor(None, func)
    
    async def table_select(self, table_name: str, columns: str = "*", **filters):
        """Async wrapper for table select operations"""
        query = self.client.table(table_name).select(columns)
        
        # Apply filters
        for key, value in filters.items():
            if key == "eq":
                for field, val in value.items():
                    query = query.eq(field, val)
            elif key == "single":
                if value:
                    query = query.single()
            elif key == "order":
                for field, desc in value.items():
                    query = query.order(field, desc=desc)
            elif key == "limit":
                query = query.limit(value)
        
        func = partial(query.execute)
        return await self.loop.run_in_executor(None, func)
    
    async def auth_sign_in_with_password(self, email: str, password: str):
        """Async wrapper for auth sign in"""
        func = partial(self.client.auth.sign_in_with_password, 
                      {"email": email, "password": password})
        return await self.loop.run_in_executor(None, func)
    
    async def auth_sign_up(self, email: str, password: str):
        """Async wrapper for auth sign up"""
        func = partial(self.client.auth.sign_up, 
                      {"email": email, "password": password})
        return await self.loop.run_in_executor(None, func)
    
    async def auth_get_user(self, jwt: str):
        """Async wrapper for getting user from JWT"""
        func = partial(self.client.auth.get_user, jwt)
        return await self.loop.run_in_executor(None, func)


# Create a singleton instance
async_supabase_client = AsyncSupabaseClient()
