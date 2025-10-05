#!/usr/bin/env python3
"""
Upload dish images to Supabase storage bucket.

This script uploads .jpg images from a local directory to the Supabase 'dishes-photos' bucket.
The filenames should match the 'name_opt' column from prompts_meta.csv.

Usage:
    python scripts/upload_images_to_supabase.py --image-dir /path/to/images

Example:
    python scripts/upload_images_to_supabase.py --image-dir ../dishplay-helper/generated-images
"""

import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.supabase_client import get_supabase_client

# Load environment variables
load_dotenv()

BUCKET_NAME = "dishes-photos"


def upload_images(image_dir: Path, overwrite: bool = False):
    """
    Upload all .jpg images from a directory to Supabase storage.

    Args:
        image_dir: Directory containing .jpg images
        overwrite: If True, overwrite existing files
    """
    supabase = get_supabase_client()

    # Get all .jpg and .png files
    image_files = (
        list(image_dir.glob("*.jpg")) +
        list(image_dir.glob("*.JPG")) +
        list(image_dir.glob("*.png")) +
        list(image_dir.glob("*.PNG"))
    )

    if not image_files:
        print(f"No image files (.jpg, .png) found in {image_dir}")
        return

    print(f"Found {len(image_files)} images to upload")
    print(f"Uploading to Supabase bucket: {BUCKET_NAME}")
    print("-" * 60)

    uploaded = 0
    skipped = 0
    errors = 0

    for image_path in image_files:
        filename = image_path.name

        try:
            # Read file
            with open(image_path, "rb") as f:
                file_data = f.read()

            # Check if file already exists
            if not overwrite:
                try:
                    existing = supabase.storage.from_(BUCKET_NAME).list(path="")
                    file_exists = any(f.get("name") == filename for f in existing)

                    if file_exists:
                        print(f"[SKIP] {filename} (already exists)")
                        skipped += 1
                        continue
                except:
                    pass  # If list fails, try to upload anyway

            # Determine content type based on file extension
            content_type = "image/png" if filename.lower().endswith(".png") else "image/jpeg"

            # Upload file
            result = supabase.storage.from_(BUCKET_NAME).upload(
                path=filename,
                file=file_data,
                file_options={"content-type": content_type, "upsert": overwrite}
            )

            print(f"[OK] {filename}")
            uploaded += 1

        except Exception as e:
            print(f"[ERROR] {filename}: {str(e)}")
            errors += 1

    print("-" * 60)
    print(f"Upload complete:")
    print(f"  Uploaded: {uploaded}")
    print(f"  Skipped:  {skipped}")
    print(f"  Errors:   {errors}")
    print(f"  Total:    {len(image_files)}")


def verify_bucket_exists():
    """Verify that the dishes-photos bucket exists and is accessible."""
    try:
        supabase = get_supabase_client()
        buckets = supabase.storage.list_buckets()

        bucket_names = [b.name for b in buckets]

        if BUCKET_NAME not in bucket_names:
            print(f"ERROR: Bucket '{BUCKET_NAME}' not found!")
            print(f"Available buckets: {', '.join(bucket_names)}")
            print(f"\nPlease create the '{BUCKET_NAME}' bucket in Supabase Dashboard:")
            print(f"1. Go to Storage in Supabase Dashboard")
            print(f"2. Click 'New bucket'")
            print(f"3. Name it '{BUCKET_NAME}'")
            print(f"4. Make it Public")
            return False

        print(f"✓ Bucket '{BUCKET_NAME}' exists and is accessible")
        return True

    except Exception as e:
        print(f"ERROR: Could not verify bucket: {str(e)}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Upload dish images to Supabase storage",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Upload images from a directory
  python scripts/upload_images_to_supabase.py --image-dir ../dishplay-helper/generated-images

  # Upload and overwrite existing files
  python scripts/upload_images_to_supabase.py --image-dir ./images --overwrite
        """
    )

    parser.add_argument(
        "--image-dir",
        type=str,
        required=True,
        help="Directory containing .jpg images to upload"
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing files in storage"
    )

    args = parser.parse_args()

    # Validate directory
    image_dir = Path(args.image_dir)
    if not image_dir.exists():
        print(f"ERROR: Directory not found: {image_dir}")
        sys.exit(1)

    if not image_dir.is_dir():
        print(f"ERROR: Not a directory: {image_dir}")
        sys.exit(1)

    # Verify bucket exists
    print("Verifying Supabase configuration...")
    if not verify_bucket_exists():
        sys.exit(1)

    print()

    # Upload images
    upload_images(image_dir, overwrite=args.overwrite)


if __name__ == "__main__":
    main()
