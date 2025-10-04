# Semantic Search for Dishplay 🍽️🔍

A semantic search implementation for the Dishplay menu digitization application, using BAAI/bge-m3 embeddings and Supabase pgvector.

## 🎯 Overview

This implementation adds intelligent image retrieval with a 3-tier fallback system:

1. **🎯 Semantic Search** (Primary) - Find similar dishes in curated database using vector similarity
2. **🔎 Google Search** (Fallback) - Search Google Custom Search for images
3. **🎨 DALL-E Generation** (Last Resort) - Generate AI images when nothing else works

## 🚀 Quick Start

### Prerequisites
- Supabase project with pgvector enabled
- Python 3.9+ with GPU support (for embedding generation)
- Clean-dish-list project for embedding generation
- prompts_meta.csv with dish metadata

### Installation

1. **Run the setup wizard:**
   ```bash
   # Windows
   scripts\setup_semantic_search.bat

   # Linux/Mac
   chmod +x scripts/setup_semantic_search.sh
   ./scripts/setup_semantic_search.sh
   ```

2. **Or manually follow these steps:**

   **Step 1: Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

   **Step 2: Enable pgvector in Supabase**
   - Go to Supabase SQL Editor
   - Run: `supabase/migrations/semantic_search_setup.sql`

   **Step 3: Generate embeddings**
   ```bash
   cd ../Clean-dish-list
   python embed_prompts_meta.py
   ```

   **Step 4: Upload embeddings**
   ```bash
   cd ../dishplay-backend
   python scripts/upload_embeddings_from_prompts_meta.py \
       --csv-path ../Clean-dish-list/prompts_meta.csv \
       --embeddings-dir ../Clean-dish-list/embeddings
   ```

   **Step 5: Upload dish images**
   - Upload to Supabase storage bucket: `dishes-photos`
   - Filename format: `{name_opt}.jpg`

   **Step 6: Test**
   ```bash
   uvicorn main:app --reload
   ```

## 📁 Project Structure

```
dishplay-backend/
├── app/
│   ├── services/
│   │   └── semantic_search_service.py     # Core semantic search logic
│   └── routers/
│       └── menu.py                         # Updated with 3-phase image retrieval
├── supabase/
│   └── migrations/
│       └── semantic_search_setup.sql       # Database schema & functions
├── scripts/
│   ├── upload_embeddings_from_prompts_meta.py  # Upload script
│   ├── setup_semantic_search.bat           # Windows setup wizard
│   ├── setup_semantic_search.sh            # Linux/Mac setup wizard
│   └── README.md                           # Scripts documentation
├── SEMANTIC_SEARCH_SETUP.md                # Detailed setup guide
├── IMPLEMENTATION_SUMMARY.md               # Implementation details
└── requirements.txt                        # Updated dependencies
```

## 🔧 Configuration

### Similarity Threshold
In `app/services/semantic_search_service.py`:
```python
SIMILARITY_THRESHOLD = 0.8  # Adjust between 0.0 and 1.0
```

- **0.9+**: Very strict, only near-perfect matches
- **0.8**: Recommended, good balance of quality and coverage
- **0.7**: More lenient, broader matches
- **0.6**: Very lenient, may include less relevant results

### Embedding Model
```python
MODEL_NAME = "BAAI/bge-m3"  # 1024-dimensional embeddings
```

Alternative models:
- `sentence-transformers/all-MiniLM-L6-v2` (384-dim, faster, less accurate)
- `sentence-transformers/all-mpnet-base-v2` (768-dim, good balance)
- `BAAI/bge-large-en-v1.5` (1024-dim, better for English)

⚠️ **Note**: Changing models requires:
1. Updating vector dimension in SQL
2. Regenerating all embeddings
3. Re-uploading to Supabase

## 📊 Database Schema

### `dish_embeddings` Table
Stores dish metadata and embeddings for semantic search.

| Column | Type | Description |
|--------|------|-------------|
| id | bigserial | Primary key |
| name_opt | text | Unique identifier (matches image filename) |
| title | text | Display name of dish |
| description | text | Dish description |
| type | text | Category (e.g., "food") |
| embedding | vector(1024) | BAAI/bge-m3 embedding |
| created_at | timestamp | Creation time |
| updated_at | timestamp | Last update time |

### `items_without_pictures` Table
Tracks menu items that didn't have semantic matches.

| Column | Type | Description |
|--------|------|-------------|
| id | bigserial | Primary key |
| created_at | timestamp | When item was logged |
| title | text | Name of unmatched dish |
| description | text | Description of unmatched dish |

### `search_dish_embeddings()` Function
RPC function for vector similarity search.

**Parameters:**
- `query_embedding` (vector(1024)) - Embedding to search for
- `match_threshold` (float) - Minimum similarity (default: 0.8)
- `match_count` (int) - Number of results (default: 3)

**Returns:**
- name_opt, title, description, type, similarity

## 🔄 How It Works

### Image Acquisition Flow

```
Menu Upload
    ↓
Extract Items (OpenAI Vision)
    ↓
For each extracted item:
    ↓
    ┌─────────────────────────────────────┐
    │ Phase 1: Semantic Search            │
    │ - Generate query embedding          │
    │ - Search pgvector database          │
    │ - Return top 3 matches if > 0.8     │
    └─────────────────────────────────────┘
              ↓ No match
    ┌─────────────────────────────────────┐
    │ Phase 2: Google Search              │
    │ - Search Google Custom Search       │
    │ - Return top 3 image URLs           │
    │ - Cache results                     │
    └─────────────────────────────────────┘
              ↓ No results
    ┌─────────────────────────────────────┐
    │ Phase 3: DALL-E Generation          │
    │ - Generate with DALL-E 3/2          │
    │ - Upload to Supabase storage        │
    │ - Cache for future use              │
    └─────────────────────────────────────┘
              ↓
    ┌─────────────────────────────────────┐
    │ Log to items_without_pictures       │
    │ (if no semantic match)              │
    └─────────────────────────────────────┘
```

### Example Request Flow

1. **User uploads menu image** → Backend receives upload

2. **OpenAI extracts items:**
   ```json
   {
     "name": "Grilled Salmon",
     "description": "Fresh Atlantic salmon with herbs and lemon"
   }
   ```

3. **Semantic search:**
   - Combines name + description: "Grilled Salmon. Fresh Atlantic salmon with herbs and lemon"
   - Generates embedding using BAAI/bge-m3
   - Searches pgvector for similar dishes
   - Returns top 3 with similarity > 0.8

4. **Result:**
   ```json
   [
     {
       "title": "Pan-Seared Salmon with Herbs",
       "similarity": 0.87,
       "image_url": "https://.../dishes-photos/pan-seared-salmon.jpg"
     },
     {
       "title": "Grilled Atlantic Salmon",
       "similarity": 0.85,
       "image_url": "https://.../dishes-photos/grilled-atlantic-salmon.jpg"
     }
   ]
   ```

5. **If no match** → Try Google Search → Try DALL-E → Use fallback

## 📈 Performance

### Speed Comparison

| Method | Average Time | Cost per Request |
|--------|-------------|------------------|
| **Semantic Search** | 50-200ms | Free (after setup) |
| Google CSE | 2-5s | $5 per 1000 queries |
| DALL-E 3 | 10-30s | $0.04 per image |
| DALL-E 2 | 5-10s | $0.02 per image |

### Expected Improvements

- **50-70% faster** image retrieval for matched dishes
- **60-80% reduction** in API costs (less Google/DALL-E calls)
- **Higher quality** images from curated database
- **More consistent** results across similar dishes

## 🧪 Testing

### Test Semantic Search

```python
import asyncio
from app.services.semantic_search_service import search_similar_dishes

async def test_search():
    results = await search_similar_dishes(
        query_name="Caesar Salad",
        query_description="Romaine lettuce with parmesan and croutons",
        top_k=5,
        threshold=0.7
    )

    print(f"Found {len(results)} matches:")
    for r in results:
        print(f"  {r['title']}: {r['similarity']:.3f}")
        print(f"  Image: {r['image_url']}")
        print()

asyncio.run(test_search())
```

### Monitor Match Rate

```sql
-- In Supabase SQL Editor
SELECT
    DATE(created_at) as date,
    COUNT(*) as total_items,
    COUNT(DISTINCT menu_id) as total_menus
FROM menu_items
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY DATE(created_at)
ORDER BY date DESC;
```

### View Unmatched Items

```sql
SELECT
    title,
    description,
    created_at
FROM items_without_pictures
ORDER BY created_at DESC
LIMIT 50;
```

Use these to expand your dish database.

## 🛠️ Troubleshooting

### Common Issues

**"No module named 'sentence_transformers'"**
```bash
pip install -r requirements.txt
```

**"CUDA out of memory"**
- Model will automatically fall back to CPU
- Or reduce batch_size in encode calls

**"No similar dishes found above threshold"**
- Lower the threshold: `SIMILARITY_THRESHOLD = 0.7`
- Check embeddings uploaded: `SELECT COUNT(*) FROM dish_embeddings;`
- Verify model name matches

**"Image URL returns 404"**
- Check images uploaded to `dishes-photos` bucket
- Verify filename matches `name_opt` column
- Ensure bucket permissions are correct

**"Semantic search is slow"**
- Check pgvector index exists
- Increase `lists` parameter in ivfflat index
- Consider HNSW index for better performance

## 📚 Documentation

- **[SEMANTIC_SEARCH_SETUP.md](SEMANTIC_SEARCH_SETUP.md)** - Complete setup guide
- **[IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)** - Technical implementation details
- **[scripts/README.md](scripts/README.md)** - Scripts documentation

## 🎯 Next Steps

- [ ] Deploy to Render with updated requirements
- [ ] Run SQL migration in Supabase
- [ ] Generate and upload embeddings
- [ ] Upload dish images to storage
- [ ] Test with real menu uploads
- [ ] Monitor semantic match rate
- [ ] Iterate on threshold and dataset

## 🔮 Future Enhancements

- Frontend UI to select image source priority
- A/B testing for similarity thresholds
- Multi-language embedding support
- Real-time embedding for new dishes
- Analytics dashboard for match rates
- Automatic retraining with unmatched items

## 💡 Tips

1. **Start with high threshold** (0.8) and lower if needed
2. **Monitor items_without_pictures** to identify gaps
3. **Use descriptive dish names** in prompts_meta.csv
4. **Include cooking method** in descriptions (grilled, fried, etc.)
5. **Update embeddings regularly** as you add new dishes
6. **Cache frequently searched items** for even better performance

## 🤝 Contributing

When adding new dishes:
1. Add to prompts_meta.csv
2. Upload corresponding image to dishes-photos
3. Regenerate embeddings
4. Re-run upload script (will upsert)

## 📄 License

Same as main Dishplay project.

---

**Need help?** Check the troubleshooting section or review the detailed setup guide in [SEMANTIC_SEARCH_SETUP.md](SEMANTIC_SEARCH_SETUP.md).
