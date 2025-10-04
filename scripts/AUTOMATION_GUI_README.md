# Semantic Search Automation GUI

A simple GUI tool to automate semantic search workflows for the Dishplay application.

## Features

### Flow 1: Generate Prompts for Unmatched Items
Automatically generates image prompts for menu items that weren't matched in the semantic search:

1. **Fetches** unmatched items from Supabase `items_without_pictures` table
2. **Creates** input CSV for Ollama processing
3. **Generates** prompts using the Ollama LLM (via `csv_to_prompts_ollama.py`)
4. **Updates** `prompts_meta.csv` with new entries
5. **Marks** items as processed in Supabase

**After Flow 1**, you need to manually:
- Generate images for the new prompts
- Upload images to Supabase storage (`dishes-photos` bucket)

### Flow 2: Generate & Upload Embeddings
Generates embeddings for all dishes and uploads them to Supabase:

1. **Clears** old embeddings from Supabase
2. **Generates** embeddings using BAAI/bge-m3 model (via `embed_prompts_meta.py`)
3. **Uploads** embeddings to Supabase `dish_embeddings` table

## Prerequisites

### 1. Directory Structure
```
Programming/
├── dishplay-backend/
│   ├── scripts/
│   │   ├── semantic_search_automation_gui.py  ← This tool
│   │   └── upload_embeddings_from_prompts_meta.py
│   └── .env  ← Supabase credentials
├── CSV-to-structured-text/
│   ├── csv_to_prompts_ollama.py
│   └── prompts_meta.csv
└── Clean-dish-list/
    └── embed_prompts_meta.py
```

### 2. Environment Variables
Create or update `dishplay-backend/.env`:
```bash
SUPABASE_URL=your_supabase_url
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
```

### 3. Dependencies
```bash
cd dishplay-backend
pip install -r requirements.txt
```

### 4. Ollama (for Flow 1)
- Install Ollama: https://ollama.ai
- Start Ollama: `ollama serve`
- Pull required model: `ollama pull qwen3:8b`

### 5. Database Setup
Run the migration in Supabase SQL Editor:
```sql
-- Execute: dishplay-backend/supabase/migrations/semantic_search_setup.sql
```

## Usage

### Launch GUI
```bash
cd dishplay-backend/scripts
python semantic_search_automation_gui.py
```

### Running Flows

**Flow 1** - When you have new menu items without images:
1. Click "Flow 1: Generate Prompts for Unmatched Items"
2. Wait for completion (progress shown in log)
3. Check output in `CSV-to-structured-text/prompts_meta.csv`
4. Generate images manually
5. Upload images to Supabase storage

**Flow 2** - After adding new images or updating prompts:
1. Click "Flow 2: Generate & Upload Embeddings"
2. Wait for completion (may take several minutes)
3. Semantic search is now updated!

## Workflow Example

### Scenario: New menu items added to Supabase

1. **Run Flow 1**
   - Fetches unmatched items from `items_without_pictures`
   - Generates prompts using Ollama
   - Updates `prompts_meta.csv`

2. **Manual Step: Generate Images**
   - Use Stable Diffusion/DALL-E/Midjourney
   - Name images: `{name_opt}.jpg` (from `prompts_meta.csv`)

3. **Manual Step: Upload Images**
   - Upload to Supabase storage bucket: `dishes-photos`

4. **Run Flow 2**
   - Generates embeddings from all prompts
   - Uploads to Supabase `dish_embeddings` table
   - ✅ Semantic search is now live!

## Troubleshooting

### "Ollama is not running"
```bash
# Start Ollama
ollama serve

# In another terminal, verify it's running
curl http://127.0.0.1:11434/api/tags
```

### "Supabase credentials not configured"
Check your `.env` file:
```bash
cat dishplay-backend/.env
# Should contain SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY
```

### "Ollama script not found"
Verify directory structure:
```bash
ls -la ../CSV-to-structured-text/csv_to_prompts_ollama.py
ls -la ../Clean-dish-list/embed_prompts_meta.py
```

### "No GPU detected" (Flow 2)
The embedding script will automatically fall back to CPU. It will be slower but still work.

To enable GPU:
- Ensure CUDA is installed
- Install PyTorch with CUDA support:
  ```bash
  pip install torch --index-url https://download.pytorch.org/whl/cu121
  ```

## Technical Details

### Flow 1 Details

**Input:**
- Supabase table: `items_without_pictures` (columns: `id`, `title`, `description`, `processed`)

**Process:**
1. Query: `SELECT * FROM items_without_pictures WHERE processed = false`
2. Create `input.csv` with columns: `title`, `short_description`, `precise_content`
3. Run Ollama script to generate prompts
4. Append new entries to `prompts_meta.csv`
5. Update Supabase: `UPDATE items_without_pictures SET processed = true WHERE id IN (...)`

**Output:**
- Updated `prompts_meta.csv` with new entries
- Text files: `prompts_0001.txt`, `prompts_0002.txt`, etc.

### Flow 2 Details

**Input:**
- `prompts_meta.csv` with columns: `name_opt`, `title`, `description`, `type`

**Process:**
1. Delete all rows from `dish_embeddings` table
2. Generate embeddings using BAAI/bge-m3 model (1024 dimensions)
3. Upload to Supabase in batches of 100

**Output:**
- `Clean-dish-list/embeddings/recipes.bge-m3.parquet`
- `Clean-dish-list/embeddings/recipes.bge-m3.npy`
- Supabase table `dish_embeddings` populated

### Error Handling

Both flows include comprehensive error handling:
- Network errors (Supabase connection)
- File not found errors
- Ollama connection errors
- Script execution errors

All errors are displayed in the GUI log with timestamps and error levels.

## Performance

### Flow 1 (Ollama)
- Speed: ~2-5 seconds per item (depends on Ollama model and hardware)
- For 100 items: ~5-10 minutes

### Flow 2 (Embeddings)
- With GPU (RTX 4090): ~10-20 seconds for 50k items
- With CPU: ~5-10 minutes for 50k items

## Files Modified by This Tool

### Created/Updated:
- `CSV-to-structured-text/input.csv` (temporary, overwritten each run)
- `CSV-to-structured-text/prompts_meta.csv` (appended)
- `CSV-to-structured-text/prompts_XXXX.txt` (created)
- `Clean-dish-list/embeddings/*.parquet` (overwritten)
- `Clean-dish-list/embeddings/*.npy` (overwritten)

### Database Tables:
- `items_without_pictures` (marks items as processed)
- `dish_embeddings` (cleared and repopulated)

## Limitations

1. **No undo**: Once Flow 2 clears embeddings, they're deleted. Keep backups of `prompts_meta.csv`.
2. **Manual image generation**: Flows don't auto-generate images (requires external tools).
3. **Single Ollama model**: Model is hardcoded in `csv_to_prompts_ollama.py` (currently `qwen3:8b`).

## Future Enhancements

- [ ] Backup/restore embeddings
- [ ] Batch image upload to Supabase
- [ ] Progress bars with actual percentages
- [ ] Configurable Ollama model selection
- [ ] Dry-run mode to preview changes

## Support

For issues or questions:
1. Check logs in GUI window
2. Verify all prerequisites are met
3. Check file paths in GUI footer
4. Review error messages for specific issues

## License

Part of the Dishplay project.
