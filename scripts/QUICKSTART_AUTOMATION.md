# Quick Start: Semantic Search Automation GUI

## 🚀 5-Minute Setup

### Step 1: Install Dependencies
```bash
cd dishplay-backend
pip install -r requirements.txt
```

### Step 2: Configure Environment
Create `dishplay-backend/.env`:
```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
```

### Step 3: Setup Database
1. Go to Supabase SQL Editor
2. Run the migration: `supabase/migrations/semantic_search_setup.sql`

### Step 4: Install Ollama (for Flow 1 only)
```bash
# Download from https://ollama.ai
# Then pull the model:
ollama pull qwen3:8b
```

### Step 5: Launch GUI
**Windows:**
```bash
cd dishplay-backend\scripts
run_automation_gui.bat
```

**Linux/Mac:**
```bash
cd dishplay-backend/scripts
./run_automation_gui.sh
```

---

## 🎯 Usage

### Scenario 1: You have new menu items without images

1. **Click: Flow 1 - Generate Prompts**
   - ✅ Fetches unmatched items from Supabase
   - ✅ Generates prompts with Ollama
   - ✅ Updates `prompts_meta.csv`

2. **Manual: Generate & Upload Images**
   - Use Stable Diffusion/DALL-E/Midjourney
   - Name: `{name_opt}.jpg` (from `prompts_meta.csv`)
   - Upload to Supabase bucket: `dishes-photos`

3. **Click: Flow 2 - Generate & Upload Embeddings**
   - ✅ Creates embeddings
   - ✅ Uploads to Supabase
   - ✅ Done!

### Scenario 2: You updated prompts_meta.csv manually

1. **Click: Flow 2 - Generate & Upload Embeddings**
   - ✅ Creates embeddings
   - ✅ Uploads to Supabase
   - ✅ Done!

---

## ⚡ Commands Cheat Sheet

### Check Ollama Status
```bash
curl http://127.0.0.1:11434/api/tags
```

### Start Ollama
```bash
ollama serve
```

### View Logs
All logs are shown in the GUI window in real-time.

### Test Supabase Connection
```bash
cd dishplay-backend
python -c "from app.core.supabase_client import get_supabase_client; print('✓ Connected:', get_supabase_client())"
```

---

## 📁 File Locations

| File | Purpose |
|------|---------|
| `CSV-to-structured-text/prompts_meta.csv` | Main prompts database |
| `CSV-to-structured-text/input.csv` | Temporary input for Ollama |
| `Clean-dish-list/embeddings/` | Generated embeddings |
| `dishplay-backend/.env` | Supabase credentials |

---

## ❗ Common Issues

### "Ollama is not running"
```bash
ollama serve
```

### "No GPU detected"
CPU will be used (slower but works). To enable GPU:
```bash
pip install torch --index-url https://download.pytorch.org/whl/cu121
```

### "Supabase credentials not configured"
Check your `.env` file has:
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

---

## 📊 Expected Performance

| Flow | Items | GPU Time | CPU Time |
|------|-------|----------|----------|
| Flow 1 (Ollama) | 100 | ~5 min | ~5 min |
| Flow 2 (Embeddings) | 50,000 | ~15 sec | ~8 min |

---

## 🔄 Complete Workflow Example

```
1. New menu items added to restaurant database
   ↓
2. Items without matches appear in `items_without_pictures` table
   ↓
3. Run Flow 1 → Generates prompts
   ↓
4. Generate images (manual step)
   ↓
5. Upload images to Supabase (manual step)
   ↓
6. Run Flow 2 → Creates embeddings
   ↓
7. ✅ Semantic search is live!
```

---

## 📚 More Info

See [AUTOMATION_GUI_README.md](AUTOMATION_GUI_README.md) for detailed documentation.
