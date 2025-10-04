#!/bin/bash

# Semantic Search Setup Script
# This script helps you set up semantic search for Dishplay backend

set -e

echo "============================================================"
echo "Dishplay Semantic Search Setup Script"
echo "============================================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if we're in the right directory
if [ ! -f "requirements.txt" ]; then
    echo -e "${RED}Error: This script must be run from the dishplay-backend directory${NC}"
    exit 1
fi

echo ""
echo "This script will guide you through setting up semantic search."
echo ""

# Step 1: Check Python version
echo -e "${YELLOW}Step 1: Checking Python version...${NC}"
PYTHON_VERSION=$(python --version 2>&1 | awk '{print $2}')
echo "Python version: $PYTHON_VERSION"

# Step 2: Install dependencies
echo ""
echo -e "${YELLOW}Step 2: Install Python dependencies?${NC}"
read -p "Install dependencies now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    pip install -r requirements.txt
    echo -e "${GREEN}✓ Dependencies installed${NC}"
else
    echo "Skipped. Make sure to run: pip install -r requirements.txt"
fi

# Step 3: Check Supabase connection
echo ""
echo -e "${YELLOW}Step 3: Checking Supabase configuration...${NC}"
if [ -f ".env" ]; then
    echo -e "${GREEN}✓ .env file found${NC}"

    # Check required variables
    MISSING_VARS=()
    if ! grep -q "SUPABASE_URL" .env; then
        MISSING_VARS+=("SUPABASE_URL")
    fi
    if ! grep -q "SUPABASE_ANON_KEY" .env; then
        MISSING_VARS+=("SUPABASE_ANON_KEY")
    fi

    if [ ${#MISSING_VARS[@]} -eq 0 ]; then
        echo -e "${GREEN}✓ Supabase credentials configured${NC}"
    else
        echo -e "${RED}✗ Missing environment variables: ${MISSING_VARS[*]}${NC}"
        echo "Please add them to your .env file"
    fi
else
    echo -e "${RED}✗ .env file not found${NC}"
    echo "Please create .env file with Supabase credentials"
fi

# Step 4: SQL Migration
echo ""
echo -e "${YELLOW}Step 4: Database Setup${NC}"
echo "The SQL migration needs to be run in your Supabase SQL Editor."
echo ""
echo "Migration file location:"
echo "  supabase/migrations/semantic_search_setup.sql"
echo ""
read -p "Have you run the SQL migration in Supabase? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${GREEN}✓ SQL migration completed${NC}"
else
    echo -e "${YELLOW}Please run the SQL migration before continuing${NC}"
    echo "Instructions:"
    echo "1. Go to your Supabase project dashboard"
    echo "2. Navigate to SQL Editor"
    echo "3. Copy and paste the contents of supabase/migrations/semantic_search_setup.sql"
    echo "4. Execute the SQL"
fi

# Step 5: Generate embeddings
echo ""
echo -e "${YELLOW}Step 5: Generate Embeddings${NC}"
echo ""
echo "You need to generate embeddings using the Clean-dish-list project."
echo ""
echo "Steps:"
echo "1. Prepare your prompts_meta.csv with columns: name_opt, title, description, type"
echo "2. Run: cd ../Clean-dish-list && python embed_prompts_meta.py"
echo ""
read -p "Have you generated embeddings? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${GREEN}✓ Embeddings generated${NC}"

    # Ask for CSV path
    echo ""
    read -p "Enter path to prompts_meta.csv (or press Enter for default): " CSV_PATH
    if [ -z "$CSV_PATH" ]; then
        CSV_PATH="../Clean-dish-list/prompts_meta.csv"
    fi

    # Ask for embeddings directory
    read -p "Enter path to embeddings directory (or press Enter for default): " EMB_DIR
    if [ -z "$EMB_DIR" ]; then
        EMB_DIR="../Clean-dish-list/embeddings"
    fi

    # Step 6: Upload embeddings
    echo ""
    echo -e "${YELLOW}Step 6: Upload Embeddings to Supabase${NC}"
    echo ""
    read -p "Upload embeddings now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        python scripts/upload_embeddings_from_prompts_meta.py \
            --csv-path "$CSV_PATH" \
            --embeddings-dir "$EMB_DIR"

        if [ $? -eq 0 ]; then
            echo -e "${GREEN}✓ Embeddings uploaded successfully${NC}"
        else
            echo -e "${RED}✗ Embeddings upload failed${NC}"
        fi
    else
        echo "Skipped. You can upload later using:"
        echo "python scripts/upload_embeddings_from_prompts_meta.py \\"
        echo "    --csv-path $CSV_PATH \\"
        echo "    --embeddings-dir $EMB_DIR"
    fi
else
    echo "Please generate embeddings first:"
    echo "cd ../Clean-dish-list && python embed_prompts_meta.py"
fi

# Step 7: Upload images
echo ""
echo -e "${YELLOW}Step 7: Upload Dish Images${NC}"
echo ""
echo "Upload your dish images to Supabase storage bucket 'dishes-photos'"
echo "Images should be named: {name_opt}.jpg"
echo ""
echo "You can upload via:"
echo "1. Supabase Dashboard → Storage → dishes-photos"
echo "2. Supabase CLI"
echo "3. Python script using Supabase storage API"
echo ""
read -p "Have you uploaded dish images? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${GREEN}✓ Dish images uploaded${NC}"
else
    echo "Please upload dish images before testing"
fi

# Summary
echo ""
echo "============================================================"
echo -e "${GREEN}Setup Summary${NC}"
echo "============================================================"
echo ""
echo "Next steps:"
echo "1. Test the backend locally: uvicorn main:app --reload"
echo "2. Upload a test menu image"
echo "3. Check logs for semantic search activity"
echo "4. Monitor the items_without_pictures table"
echo "5. Deploy to Render when ready"
echo ""
echo "For detailed documentation, see:"
echo "  - SEMANTIC_SEARCH_SETUP.md"
echo "  - IMPLEMENTATION_SUMMARY.md"
echo ""
echo "============================================================"
