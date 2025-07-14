#!/usr/bin/env python3
"""Test script to check if all imports work correctly"""

try:
    print("Testing basic imports...")
    
    # Test standard library imports
    import os
    import sys
    import logging
    print("OK: Standard library imports work")
    
    # Test typing imports
    from typing import Optional, Dict
    print("OK: Typing imports work")
    
    # Test if FastAPI is available
    try:
        import fastapi
        print("OK: FastAPI is available")
    except ImportError as e:
        print(f"ERROR: FastAPI not available: {e}")
        
    # Test if our app modules work
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from app.core.cache import user_cache
        print("OK: Cache module imports work")
    except ImportError as e:
        print(f"ERROR: Cache module import failed: {e}")
        
    try:
        from app.core.logging import setup_logging
        print("OK: Logging module imports work")
    except ImportError as e:
        print(f"ERROR: Logging module import failed: {e}")
    
    # Test main.py imports
    try:
        import main
        print("OK: Main module imports work")
    except ImportError as e:
        print(f"ERROR: Main module import failed: {e}")
        
    print("\nTest completed!")
    
except Exception as e:
    print(f"Unexpected error: {e}")
    import traceback
    traceback.print_exc()