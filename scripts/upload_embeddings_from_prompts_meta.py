"""
Script to upload dish embeddings to Supabase from prompts_meta CSV.

This script reads embeddings and the prompts_meta CSV file and uploads
them to the Supabase dish_embeddings table.

The prompts_meta CSV has columns: name (or name_opt for legacy), title, description, type

Usage:
    python scripts/upload_embeddings_from_prompts_meta.py --csv-path path/to/prompts_meta.csv
"""

import os
import sys
import argparse
import pandas as pd
import numpy as np
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase_client

# Load environment variables
load_dotenv()

# Default paths
DEFAULT_EMBEDDINGS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "Clean-dish-list",
    "embeddings"
)


def load_embeddings_and_metadata(csv_path, embeddings_dir):
    """Load embeddings and metadata from files"""

    print(f"Loading metadata from CSV: {csv_path}")

    # Read prompts_meta CSV
    if not os.path.exists(csv_path):
        print(f"Error: CSV file not found at {csv_path}")
        return None

    df_meta = pd.read_csv(csv_path)
    print(f"Loaded {len(df_meta)} records from CSV")

    # Show sample
    print(f"\nSample metadata:")
    print(df_meta.head(2))
    print(f"\nColumns: {list(df_meta.columns)}")

    # Load embeddings from parquet
    parquet_path = os.path.join(embeddings_dir, "recipes.bge-m3.parquet")

    if not os.path.exists(parquet_path):
        print(f"\nError: Embeddings parquet file not found at {parquet_path}")
        print(f"Please generate embeddings first using Clean-dish-list/embed.py")
        return None

    print(f"\nLoading embeddings from: {parquet_path}")
    df_embeddings = pd.read_parquet(parquet_path)
    print(f"Loaded {len(df_embeddings)} embeddings")

    # The parquet file should have been generated with text_for_embedding column
    # that combines title and description
    # We need to match it with our prompts_meta records

    # Strategy: Match based on title
    # First, create a text_for_embedding column in df_meta to match with df_embeddings
    df_meta['text_for_embedding'] = df_meta['title'] + '. ' + df_meta['description'].fillna('')

    # Try to merge on title first
    if 'title' in df_embeddings.columns:
        print("\nMerging embeddings with metadata on 'title' column...")
        merged = df_embeddings.merge(
            df_meta,
            on='title',
            how='inner',
            suffixes=('_emb', '_meta')
        )
    else:
        # If embeddings don't have title, try merging on text_for_embedding
        print("\nMerging embeddings with metadata on 'text_for_embedding' column...")
        merged = df_embeddings.merge(
            df_meta,
            on='text_for_embedding',
            how='inner'
        )

    if len(merged) == 0:
        print("\nError: Could not match any records between embeddings and metadata")
        print("This might mean the embeddings were generated from a different dataset")
        print("\nYou need to regenerate embeddings using the prompts_meta CSV")
        return None

    print(f"\nSuccessfully matched {len(merged)} records")

    # After merge, we might have suffixes. Let's clean up the columns
    # Prefer _meta suffix (from prompts_meta CSV) for metadata columns
    # and keep embedding from embeddings dataframe
    result = pd.DataFrame()

    # Get the right columns, handling potential suffixes
    # Support both 'name' and 'name_opt' for backwards compatibility
    if 'name_meta' in merged.columns:
        result['name_opt'] = merged['name_meta']
    elif 'name' in merged.columns:
        result['name_opt'] = merged['name']
    elif 'name_opt_meta' in merged.columns:
        result['name_opt'] = merged['name_opt_meta']
    elif 'name_opt' in merged.columns:
        result['name_opt'] = merged['name_opt']

    result['title'] = merged['title']

    if 'description_meta' in merged.columns:
        result['description'] = merged['description_meta']
    elif 'description' in merged.columns:
        result['description'] = merged['description']

    if 'type_meta' in merged.columns:
        result['type'] = merged['type_meta']
    elif 'type' in merged.columns:
        result['type'] = merged['type']

    result['embedding'] = merged['embedding']

    # Check for required columns
    required = ['name_opt', 'title', 'description', 'type', 'embedding']
    missing = [col for col in required if col not in result.columns]

    if missing:
        print(f"\nError: Missing required columns: {missing}")
        print(f"Available columns: {list(result.columns)}")
        return None

    return result


def upload_to_supabase(df):
    """Upload dataframe to Supabase dish_embeddings table"""

    print("\nConnecting to Supabase...")
    supabase = get_supabase_client()

    print("Preparing records for upload...")
    batch_size = 500  # Increased from 100 to 500 for faster uploads
    total_uploaded = 0
    errors = 0

    for i in range(0, len(df), batch_size):
        batch = df.iloc[i:i+batch_size]

        records = []
        for _, row in batch.iterrows():
            # Convert embedding to list if needed
            embedding = row['embedding']
            if isinstance(embedding, str):
                embedding = eval(embedding)
            elif isinstance(embedding, np.ndarray):
                embedding = embedding.tolist()

            records.append({
                'name_opt': str(row['name_opt']),
                'title': str(row['title']),
                'description': str(row['description']) if pd.notna(row['description']) else '',
                'type': str(row['type']) if pd.notna(row['type']) else 'food',
                'embedding': embedding
            })

        # Upload batch
        try:
            import time
            start_time = time.time()

            response = supabase.table('dish_embeddings').upsert(
                records,
                on_conflict='name_opt'
            ).execute()

            total_uploaded += len(records)
            elapsed = time.time() - start_time

            batch_num = i//batch_size + 1
            total_batches = (len(df)-1)//batch_size + 1

            print(f"Uploaded batch {batch_num}/{total_batches} "
                  f"({total_uploaded}/{len(df)} records) "
                  f"- {elapsed:.1f}s")

        except Exception as e:
            print(f"Error uploading batch {i//batch_size + 1}: {str(e)}")

            # For large batches, try splitting in half instead of one by one
            if len(records) > 50:
                print(f"  Retrying with smaller batches...")
                mid = len(records) // 2
                for sub_batch in [records[:mid], records[mid:]]:
                    try:
                        supabase.table('dish_embeddings').upsert(
                            sub_batch,
                            on_conflict='name_opt'
                        ).execute()
                        total_uploaded += len(sub_batch)
                    except Exception as sub_error:
                        print(f"  Sub-batch also failed: {str(sub_error)}")
                        errors += len(sub_batch)
            else:
                # Try uploading one by one for small batches
                for record in records:
                    try:
                        supabase.table('dish_embeddings').upsert(
                            [record],
                            on_conflict='name_opt'
                        ).execute()
                        total_uploaded += 1
                    except Exception as record_error:
                        print(f"  Error with record '{record['name_opt']}': {str(record_error)}")
                        errors += 1

    print(f"\n{'='*60}")
    print(f"Upload Summary")
    print(f"{'='*60}")
    print(f"Total records:        {len(df)}")
    print(f"Successfully uploaded: {total_uploaded}")
    print(f"Errors:               {errors}")
    print(f"{'='*60}")

    return errors == 0


def main():
    parser = argparse.ArgumentParser(description='Upload dish embeddings to Supabase')
    parser.add_argument(
        '--csv-path',
        type=str,
        required=True,
        help='Path to prompts_meta.csv file'
    )
    parser.add_argument(
        '--embeddings-dir',
        type=str,
        default=DEFAULT_EMBEDDINGS_DIR,
        help=f'Path to embeddings directory (default: {DEFAULT_EMBEDDINGS_DIR})'
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Dish Embeddings Upload Script")
    print("=" * 60)
    print(f"CSV path:        {args.csv_path}")
    print(f"Embeddings dir:  {args.embeddings_dir}")
    print("=" * 60)

    # Load data
    df = load_embeddings_and_metadata(args.csv_path, args.embeddings_dir)

    if df is None:
        print("\n[ERROR] Failed to load data")
        return 1

    # Upload to Supabase
    success = upload_to_supabase(df)

    if success:
        print("\n[SUCCESS] All embeddings uploaded successfully!")
        return 0
    else:
        print("\n[ERROR] Some embeddings failed to upload. Check errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
