#!/usr/bin/env python3
"""List all files in Supabase storage bucket."""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.supabase_client import get_supabase_client

load_dotenv()

BUCKET_NAME = "menu-images"
FOLDER_PATH = "dishes-photos"

supabase = get_supabase_client()

print(f"Listing files in bucket: {BUCKET_NAME}/{FOLDER_PATH}")
print("-" * 80)

try:
    files = supabase.storage.from_(BUCKET_NAME).list(path=FOLDER_PATH)

    print(f"Found {len(files)} files:\n")

    for i, f in enumerate(files[:20], 1):  # Show first 20
        name = f.get("name", "")
        size = f.get("metadata", {}).get("size", 0)
        print(f"{i}. {name} ({size} bytes)")

    if len(files) > 20:
        print(f"\n... and {len(files) - 20} more files")

except Exception as e:
    print(f"ERROR: {e}")
