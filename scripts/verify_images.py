#!/usr/bin/env python3
"""
Verify which dish images are present/missing in Supabase storage.

This script checks which dishes in the database have corresponding images
in the Supabase storage bucket.

Usage:
    python scripts/verify_images.py
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.supabase_client import get_supabase_client

# Load environment variables
load_dotenv()

BUCKET_NAME = "dishes-photos"


def verify_images():
    """Check which dishes have images in storage."""
    supabase = get_supabase_client()

    # Get all dishes from database
    print("Fetching dishes from database...")
    response = supabase.table("dishes").select("name_opt, title").execute()
    dishes = response.data

    if not dishes:
        print("No dishes found in database")
        return

    print(f"Found {len(dishes)} dishes in database")
    print()

    # Get all files in storage bucket
    print(f"Checking storage bucket: {BUCKET_NAME}")
    try:
        files_in_bucket = supabase.storage.from_(BUCKET_NAME).list(path="")
        storage_filenames = {f.get("name") for f in files_in_bucket}
        print(f"Found {len(storage_filenames)} files in storage")
    except Exception as e:
        print(f"ERROR: Could not list files in bucket: {str(e)}")
        print(f"\nMake sure the '{BUCKET_NAME}' bucket exists and is accessible")
        return

    print()
    print("-" * 80)

    # Check each dish
    found = 0
    missing = 0
    missing_dishes = []

    for dish in dishes:
        name_opt = dish.get("name_opt", "")
        title = dish.get("title", "")
        expected_filename = f"{name_opt}.jpg"

        if expected_filename in storage_filenames:
            print(f"[OK] {expected_filename} - {title}")
            found += 1
        else:
            print(f"[MISSING] {expected_filename} - {title}")
            missing += 1
            missing_dishes.append({
                "filename": expected_filename,
                "name_opt": name_opt,
                "title": title
            })

    print("-" * 80)
    print()
    print(f"Summary:")
    print(f"  Found:   {found}/{len(dishes)} ({found/len(dishes)*100:.1f}%)")
    print(f"  Missing: {missing}/{len(dishes)} ({missing/len(dishes)*100:.1f}%)")

    if missing_dishes:
        print()
        print(f"Missing images:")
        for dish in missing_dishes[:10]:  # Show first 10
            print(f"  - {dish['filename']} ({dish['title']})")

        if len(missing_dishes) > 10:
            print(f"  ... and {len(missing_dishes) - 10} more")

        print()
        print(f"To upload images:")
        print(f"  python scripts/upload_images_to_supabase.py --image-dir /path/to/images")


def main():
    try:
        verify_images()
    except Exception as e:
        print(f"ERROR: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
