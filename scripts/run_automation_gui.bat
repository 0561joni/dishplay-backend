@echo off
REM Semantic Search Automation GUI Launcher
REM This script launches the automation GUI for semantic search workflows

echo ================================================
echo Semantic Search Automation GUI
echo ================================================
echo.

REM Change to script directory
cd /d "%~dp0"

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found!
    echo Please install Python 3.8+ and add it to PATH
    pause
    exit /b 1
)

echo Starting GUI...
echo.

REM Run the GUI
python semantic_search_automation_gui.py

if errorlevel 1 (
    echo.
    echo ERROR: GUI failed to start
    echo Check the error messages above
    pause
    exit /b 1
)

pause
