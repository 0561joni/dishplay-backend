# Semantic Search Setup Guide

This guide explains how to set up semantic search for the Dishplay backend using embeddings from the Clean-dish-list project.

## Overview

The semantic search system works as follows:

1. **Priority 1: Semantic Search** - Search for similar dishes in the pgvector-enabled Supabase database (threshold: 0.8 cosine similarity)
2. **Priority 2: Google Search** - If no semantic match found, use Google Custom Search API
3. **Priority 3: DALL-E Generation** - If Google search fails, generate images using DALL-E

Items without semantic matches are logged to the `items_without_pictures` table for future training data.

## Prerequisites

- Supabase project with pgvector extension enabled
- Clean-dish-list project with generated embeddings
- Python 3.9+ with CUDA support (for local embedding generation)
- prompts_meta.csv file with columns: `name_opt`, `title`, `description`, `type`

## Step 1: Enable pgvector in Supabase

1. Go to your Supabase project dashboard
2. Navigate to **SQL Editor**
3. Run the migration SQL:

```bash
# From dishplay-backend directory
cat supabase/migrations/semantic_search_setup.sql
```

Or manually execute the SQL in Supabase SQL Editor.

This will:
- Enable the `vector` extension
- Create `dish_embeddings` table with 1024-dimensional vector column
- Create `items_without_pictures` table
- Set up the `search_dish_embeddings` RPC function
- Create indexes for efficient search

## Step 2: Generate Embeddings (if not already done)

If you haven't generated embeddings yet in the Clean-dish-list project:

1. Navigate to Clean-dish-list directory:
```bash
cd ../Clean-dish-list
```

2. Prepare your prompts_meta.csv with the structure:
```csv
name_opt,title,description,type
970-0001-miso-butter-roast-chicken,Miso-Butter Roast Chicken With Acorn Squash Panzanella,whole chicken glazed with miso-butter...,food
```

3. Update `embed.py` to use prompts_meta.csv:
```python
SRC_CSV = "prompts_meta.csv"
TEXT_COL = "description"  # or combine title + description
TITLE_COL = "title"
```

4. Run the embedding generation:
```bash
python embed.py
```

This will create:
- `embeddings/recipes.bge-m3.parquet` - Embeddings with metadata
- `embeddings/recipes.bge-m3.npy` - Raw numpy embeddings
- `embeddings/recipes.ids.txt` - Dish IDs
- `embeddings/recipes.bge-m3.faiss.index` - FAISS index (optional)

## Step 3: Upload Embeddings to Supabase

From the dishplay-backend directory, run:

```bash
python scripts/upload_embeddings_from_prompts_meta.py \
    --csv-path /path/to/prompts_meta.csv \
    --embeddings-dir ../Clean-dish-list/embeddings
```

Example:
```bash
python scripts/upload_embeddings_from_prompts_meta.py \
    --csv-path F:/Programming/Clean-dish-list/prompts_meta.csv \
    --embeddings-dir F:/Programming/Clean-dish-list/embeddings
```

This will:
- Load the prompts_meta.csv
- Load the embeddings from the parquet file
- Match them by title
- Upload to Supabase `dish_embeddings` table

## Step 4: Upload Images to Supabase Storage

Your dish images should be uploaded to the Supabase storage bucket `dishes-photos` with filenames matching the `name_opt` column:

```
dishes-photos/
├── 970-0001-miso-butter-roast-chicken.jpg
├── 8907-0002-crispy-salt-and-pepper-potatoes.jpg
└── ...
```

You can upload via:
1. Supabase Dashboard (Storage → dishes-photos)
2. Supabase CLI
3. Python script using Supabase storage API

## Step 5: Install Dependencies

From dishplay-backend directory:

```bash
pip install -r requirements.txt
```

This includes:
- `sentence-transformers==3.3.1` - For embedding generation
- `torch==2.5.1` - PyTorch (with CUDA support if available)
- `numpy==1.26.4` - Numerical operations

## Step 6: Update Environment Variables

Ensure your `.env` file has:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key  # For admin operations
OPENAI_API_KEY=your-openai-key
GOOGLE_CSE_API_KEY=your-google-cse-key
GOOGLE_CSE_ID=your-cse-id
```

## Step 7: Test the Setup

Run a test query to verify semantic search works:

```python
from app.services.semantic_search_service import search_similar_dishes
import asyncio

async def test():
    results = await search_similar_dishes(
        query_name="Grilled Salmon",
        query_description="Fresh Atlantic salmon with herbs",
        top_k=3,
        threshold=0.8
    )

    for result in results:
        print(f"{result['title']}: {result['similarity']:.3f}")
        print(f"  Image: {result['image_url']}")

asyncio.run(test())
```

## Configuration

You can adjust these parameters in `app/services/semantic_search_service.py`:

- `MODEL_NAME`: Embedding model (default: `"BAAI/bge-m3"`)
- `SIMILARITY_THRESHOLD`: Minimum cosine similarity (default: `0.8`)
- `SUPABASE_BUCKET`: Storage bucket name (default: `"dishes-photos"`)

## Monitoring & Maintenance

### View Items Without Matches

Query the `items_without_pictures` table to see which menu items didn't have semantic matches:

```sql
SELECT title, description, created_at
FROM items_without_pictures
ORDER BY created_at DESC
LIMIT 50;
```

These can be used to:
1. Add more dishes to your database
2. Improve your embedding quality
3. Identify gaps in your dish coverage

### Update Embeddings

To update embeddings when adding new dishes:

1. Add new rows to prompts_meta.csv
2. Regenerate embeddings in Clean-dish-list
3. Re-run the upload script (it will upsert, not duplicate)

## Troubleshooting

### "No similar dishes found"

- Check that embeddings were uploaded correctly
- Verify the similarity threshold (0.8 might be too high)
- Check that the model name matches (BAAI/bge-m3)

### "Model loading error"

- Ensure you have enough GPU memory (BAAI/bge-m3 needs ~2GB)
- Check that torch is installed with CUDA support
- Fallback to CPU if needed (slower but works)

### "Image URL not found"

- Verify images are uploaded to `dishes-photos` bucket
- Check the `name_opt` column matches the filename
- Ensure bucket is public or use signed URLs

### Performance Issues

If semantic search is slow:
1. Check the pgvector index is created
2. Increase `lists` parameter in ivfflat index for larger datasets
3. Consider using HNSW index instead of ivfflat
4. Cache the embedding model (already implemented)

## Architecture

```
Menu Upload
    ↓
Extract Items (OpenAI)
    ↓
For each item:
    ↓
    ├─→ Semantic Search (pgvector)
    │   └─→ Match found? → Use images from Supabase storage
    │       ↓
    │       No match → Log to items_without_pictures
    │       ↓
    ├─→ Google Search
    │   └─→ Images found? → Cache and use
    │       ↓
    │       No images
    │       ↓
    └─→ DALL-E Generation
        └─→ Generate and cache
```

## Embedding File Upload Location

**Recommended approach:** Store embeddings in Supabase pgvector table (as implemented)

**Alternative:** If you want to load embeddings from files instead:

1. Upload embedding files to your backend server or cloud storage
2. Modify `semantic_search_service.py` to load from files instead of database
3. Use FAISS for local similarity search

However, the pgvector approach is preferred because:
- ✓ Centralized data management
- ✓ Easier to update and maintain
- ✓ Scales better
- ✓ Integrates with existing Supabase infrastructure

## Next Steps

After setup, you can:

1. **Monitor performance** - Track semantic match rate vs. Google/DALL-E usage
2. **Expand dataset** - Add more dishes to improve coverage
3. **Fine-tune threshold** - Adjust similarity threshold based on results
4. **Add frontend controls** - Let users choose image source priority
5. **Implement caching** - Cache semantic search results for common queries

## Support

For issues or questions:
1. Check Supabase logs for database errors
2. Check backend logs for semantic search errors
3. Verify embeddings are correctly formatted (1024-dimensional vectors)
4. Test with simple queries first
