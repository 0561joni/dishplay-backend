#!/usr/bin/env python3
"""Test Supabase client initialization"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_supabase_client():
    """Test if Supabase client initializes correctly"""
    
    # Check environment variables
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_ANON_KEY")
    
    print(f"SUPABASE_URL: {'✓' if supabase_url else '✗'}")
    print(f"SUPABASE_ANON_KEY: {'✓' if supabase_key else '✗'}")
    
    if not supabase_url or not supabase_key:
        print("Missing environment variables - cannot test")
        return False
    
    try:
        # Import and test the client
        from app.core.supabase_client import get_supabase_client
        
        print("Attempting to initialize Supabase client...")
        client = get_supabase_client()
        print("✓ Supabase client initialized successfully!")
        
        # Try a simple operation
        print("Testing connection with a simple query...")
        response = client.table("users").select("id").limit(1).execute()
        print("✓ Connection test successful!")
        
        return True
        
    except Exception as e:
        print(f"✗ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Testing Supabase client initialization...")
    print("-" * 50)
    
    success = test_supabase_client()
    
    print("-" * 50)
    if success:
        print("✓ All tests passed!")
    else:
        print("✗ Tests failed!")