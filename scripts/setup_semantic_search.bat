@echo off
REM Semantic Search Setup Script for Windows
REM This script helps you set up semantic search for Dishplay backend

echo ============================================================
echo Dishplay Semantic Search Setup Script
echo ============================================================

REM Check if we're in the right directory
if not exist "requirements.txt" (
    echo Error: This script must be run from the dishplay-backend directory
    exit /b 1
)

echo.
echo This script will guide you through setting up semantic search.
echo.

REM Step 1: Check Python version
echo Step 1: Checking Python version...
python --version
if %errorlevel% neq 0 (
    echo Error: Python is not installed or not in PATH
    exit /b 1
)
echo.

REM Step 2: Install dependencies
echo Step 2: Install Python dependencies?
set /p INSTALL_DEPS="Install dependencies now? (y/n): "
if /i "%INSTALL_DEPS%"=="y" (
    pip install -r requirements.txt
    echo [OK] Dependencies installed
) else (
    echo Skipped. Make sure to run: pip install -r requirements.txt
)
echo.

REM Step 3: Check Supabase connection
echo Step 3: Checking Supabase configuration...
if exist ".env" (
    echo [OK] .env file found
) else (
    echo [ERROR] .env file not found
    echo Please create .env file with Supabase credentials
)
echo.

REM Step 4: SQL Migration
echo Step 4: Database Setup
echo The SQL migration needs to be run in your Supabase SQL Editor.
echo.
echo Migration file location:
echo   supabase\migrations\semantic_search_setup.sql
echo.
set /p SQL_DONE="Have you run the SQL migration in Supabase? (y/n): "
if /i "%SQL_DONE%"=="y" (
    echo [OK] SQL migration completed
) else (
    echo Please run the SQL migration before continuing
    echo Instructions:
    echo 1. Go to your Supabase project dashboard
    echo 2. Navigate to SQL Editor
    echo 3. Copy and paste the contents of supabase\migrations\semantic_search_setup.sql
    echo 4. Execute the SQL
)
echo.

REM Step 5: Generate embeddings
echo Step 5: Generate Embeddings
echo.
echo You need to generate embeddings using the Clean-dish-list project.
echo.
echo Steps:
echo 1. Prepare your prompts_meta.csv with columns: name_opt, title, description, type
echo 2. Run: cd ..\Clean-dish-list ^&^& python embed_prompts_meta.py
echo.
set /p EMB_DONE="Have you generated embeddings? (y/n): "
if /i "%EMB_DONE%"=="y" (
    echo [OK] Embeddings generated
    echo.

    REM Ask for CSV path
    set /p CSV_PATH="Enter path to prompts_meta.csv (or press Enter for default): "
    if "%CSV_PATH%"=="" (
        set CSV_PATH=..\Clean-dish-list\prompts_meta.csv
    )

    REM Ask for embeddings directory
    set /p EMB_DIR="Enter path to embeddings directory (or press Enter for default): "
    if "%EMB_DIR%"=="" (
        set EMB_DIR=..\Clean-dish-list\embeddings
    )

    REM Step 6: Upload embeddings
    echo.
    echo Step 6: Upload Embeddings to Supabase
    echo.
    set /p UPLOAD_EMB="Upload embeddings now? (y/n): "
    if /i "%UPLOAD_EMB%"=="y" (
        python scripts\upload_embeddings_from_prompts_meta.py --csv-path "%CSV_PATH%" --embeddings-dir "%EMB_DIR%"

        if %errorlevel% equ 0 (
            echo [OK] Embeddings uploaded successfully
        ) else (
            echo [ERROR] Embeddings upload failed
        )
    ) else (
        echo Skipped. You can upload later using:
        echo python scripts\upload_embeddings_from_prompts_meta.py --csv-path "%CSV_PATH%" --embeddings-dir "%EMB_DIR%"
    )
) else (
    echo Please generate embeddings first:
    echo cd ..\Clean-dish-list ^&^& python embed_prompts_meta.py
)
echo.

REM Step 7: Upload images
echo Step 7: Upload Dish Images
echo.
echo Upload your dish images to Supabase storage bucket 'dishes-photos'
echo Images should be named: {name_opt}.jpg
echo.
echo You can upload via:
echo 1. Supabase Dashboard -^> Storage -^> dishes-photos
echo 2. Supabase CLI
echo 3. Python script using Supabase storage API
echo.
set /p IMG_DONE="Have you uploaded dish images? (y/n): "
if /i "%IMG_DONE%"=="y" (
    echo [OK] Dish images uploaded
) else (
    echo Please upload dish images before testing
)
echo.

REM Summary
echo ============================================================
echo Setup Summary
echo ============================================================
echo.
echo Next steps:
echo 1. Test the backend locally: uvicorn main:app --reload
echo 2. Upload a test menu image
echo 3. Check logs for semantic search activity
echo 4. Monitor the items_without_pictures table
echo 5. Deploy to Render when ready
echo.
echo For detailed documentation, see:
echo   - SEMANTIC_SEARCH_SETUP.md
echo   - IMPLEMENTATION_SUMMARY.md
echo.
echo ============================================================

pause
