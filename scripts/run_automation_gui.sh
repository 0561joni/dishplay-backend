#!/bin/bash
# Semantic Search Automation GUI Launcher
# This script launches the automation GUI for semantic search workflows

set -e

echo "================================================"
echo "Semantic Search Automation GUI"
echo "================================================"
echo

# Change to script directory
cd "$(dirname "$0")"

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 not found!"
    echo "Please install Python 3.8+ first"
    exit 1
fi

echo "Starting GUI..."
echo

# Run the GUI
python3 semantic_search_automation_gui.py

if [ $? -ne 0 ]; then
    echo
    echo "ERROR: GUI failed to start"
    echo "Check the error messages above"
    exit 1
fi
