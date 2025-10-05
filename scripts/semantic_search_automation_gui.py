#!/usr/bin/env python3
"""
Semantic Search Automation GUI

This GUI automates two workflows:
1. Generate prompts for unmatched menu items from Supabase
2. Generate embeddings and upload them to Supabase

Author: Dishplay Team
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import os
import sys
import csv
import subprocess
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase_client

# Load environment
load_dotenv()

# Paths
BACKEND_DIR = Path(__file__).parent.parent
HELPER_DIR = BACKEND_DIR.parent / "dishplay-helper"
CSV_TO_TEXT_DIR = HELPER_DIR / "CSV-to-structured-text"
CLEAN_DISH_DIR = HELPER_DIR / "Clean-dish-list"
PROMPTS_META_CSV = CSV_TO_TEXT_DIR / "prompts_meta.csv"
INPUT_CSV = CSV_TO_TEXT_DIR / "input.csv"
OLLAMA_SCRIPT = CSV_TO_TEXT_DIR / "csv_to_prompts_ollama.py"
EMBED_SCRIPT = CLEAN_DISH_DIR / "embed_prompts_meta.py"
UPLOAD_SCRIPT = BACKEND_DIR / "scripts" / "upload_embeddings_from_prompts_meta.py"


class SemanticSearchGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Semantic Search Automation")
        self.root.geometry("900x700")
        self.root.resizable(True, True)

        # Variables
        self.is_running = False

        # Setup UI
        self.setup_ui()

    def setup_ui(self):
        # Title
        title_label = ttk.Label(
            self.root,
            text="Semantic Search Automation",
            font=("Arial", 16, "bold")
        )
        title_label.pack(pady=10)

        # Frame for buttons
        button_frame = ttk.Frame(self.root)
        button_frame.pack(pady=10, padx=20, fill="x")

        # Flow 1 Button
        self.flow1_btn = ttk.Button(
            button_frame,
            text="Flow 1: Generate Prompts (All Items)",
            command=self.run_flow1,
            width=40
        )
        self.flow1_btn.pack(side="left", padx=5)

        # Flow 2 Button
        self.flow2_btn = ttk.Button(
            button_frame,
            text="Flow 2: Generate & Upload Embeddings",
            command=self.run_flow2,
            width=40
        )
        self.flow2_btn.pack(side="left", padx=5)

        # Status frame
        status_frame = ttk.LabelFrame(self.root, text="Status", padding=10)
        status_frame.pack(pady=10, padx=20, fill="both", expand=True)

        # Progress bar
        self.progress = ttk.Progressbar(
            status_frame,
            mode='indeterminate',
            length=300
        )
        self.progress.pack(pady=5)

        # Log output
        self.log_text = scrolledtext.ScrolledText(
            status_frame,
            width=100,
            height=30,
            font=("Courier", 9)
        )
        self.log_text.pack(pady=5, fill="both", expand=True)

        # Footer with paths info
        footer_frame = ttk.Frame(self.root)
        footer_frame.pack(pady=5, padx=20, fill="x")

        paths_info = f"Paths:\n" \
                    f"• Prompts CSV: {PROMPTS_META_CSV}\n" \
                    f"• Ollama Script: {OLLAMA_SCRIPT}\n" \
                    f"• Embed Script: {EMBED_SCRIPT}"

        footer_label = ttk.Label(
            footer_frame,
            text=paths_info,
            font=("Arial", 8),
            justify="left"
        )
        footer_label.pack(anchor="w")

    def log(self, message, level="INFO"):
        """Add log message to text widget"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_msg = f"[{timestamp}] [{level}] {message}\n"

        self.log_text.insert(tk.END, formatted_msg)
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def set_buttons_state(self, state):
        """Enable or disable buttons"""
        self.flow1_btn.config(state=state)
        self.flow2_btn.config(state=state)

    def run_flow1(self):
        """Run Flow 1: Generate prompts for unmatched items"""
        if self.is_running:
            messagebox.showwarning("Warning", "A flow is already running!")
            return

        self.is_running = True
        self.set_buttons_state("disabled")
        self.log_text.delete(1.0, tk.END)
        self.progress.start()

        # Run in thread to avoid blocking UI
        thread = threading.Thread(target=self._flow1_worker, daemon=True)
        thread.start()

    def run_flow2(self):
        """Run Flow 2: Generate & upload embeddings"""
        if self.is_running:
            messagebox.showwarning("Warning", "A flow is already running!")
            return

        self.is_running = True
        self.set_buttons_state("disabled")
        self.log_text.delete(1.0, tk.END)
        self.progress.start()

        # Run in thread to avoid blocking UI
        thread = threading.Thread(target=self._flow2_worker, daemon=True)
        thread.start()

    def _flow1_worker(self):
        """Flow 1 worker thread"""
        try:
            self.log("=" * 80)
            self.log("FLOW 1: Generate Prompts from items_without_pictures", "INFO")
            self.log("=" * 80)

            # Step 1: Fetch all items from items_without_pictures table
            self.log("Step 1/5: Fetching all items from items_without_pictures...", "INFO")
            unmatched_items = self._fetch_unmatched_items()

            if not unmatched_items:
                self.log("No items found in items_without_pictures table!", "SUCCESS")
                self._finish_flow(success=True)
                return

            # Count processed vs unprocessed
            processed_count = sum(1 for item in unmatched_items if item.get('processed', False))
            unprocessed_count = len(unmatched_items) - processed_count

            self.log(f"Found {len(unmatched_items)} total items:", "SUCCESS")
            self.log(f"  - {unprocessed_count} unprocessed items", "INFO")
            self.log(f"  - {processed_count} already processed items", "INFO")

            # Step 2: Create input CSV for Ollama script
            self.log("Step 2/5: Creating input CSV for Ollama...", "INFO")
            self._create_input_csv(unmatched_items)
            self.log(f"Created input CSV: {INPUT_CSV}", "SUCCESS")

            # Step 3: Run Ollama script to generate prompts
            self.log("Step 3/5: Running Ollama to generate prompts...", "INFO")
            self.log("This may take several minutes depending on the number of items...", "INFO")
            self._run_ollama_script()
            self.log("Prompts generated successfully!", "SUCCESS")

            # Step 4: Update prompts_meta.csv with new entries
            self.log("Step 4/5: Updating prompts_meta.csv...", "INFO")
            self._update_prompts_meta()
            self.log(f"Updated {PROMPTS_META_CSV}", "SUCCESS")

            # Step 5: Mark items as processed in Supabase
            self.log("Step 5/5: Marking items as processed in Supabase...", "INFO")
            self._mark_items_processed(unmatched_items)
            self.log("Marked all items as processed", "SUCCESS")

            self.log("=" * 80)
            self.log("FLOW 1 COMPLETED SUCCESSFULLY!", "SUCCESS")
            self.log("=" * 80)
            self.log("Next steps:", "INFO")
            self.log("1. Generate images for new prompts (manual step)", "INFO")
            self.log("2. Upload images to Supabase storage bucket 'dishes-photos'", "INFO")
            self.log("3. Run Flow 2 to generate and upload embeddings", "INFO")

            self._finish_flow(success=True)

        except Exception as e:
            self.log(f"ERROR: {str(e)}", "ERROR")
            self.log("Flow 1 failed!", "ERROR")
            self._finish_flow(success=False, error=str(e))

    def _flow2_worker(self):
        """Flow 2 worker thread"""
        try:
            self.log("=" * 80)
            self.log("FLOW 2: Generate & Upload Embeddings", "INFO")
            self.log("=" * 80)

            # Step 1: Check if prompts_meta.csv exists
            if not PROMPTS_META_CSV.exists():
                raise FileNotFoundError(f"prompts_meta.csv not found at {PROMPTS_META_CSV}")

            # Step 2: Clear old embeddings from Supabase
            self.log("Step 1/3: Clearing old embeddings from Supabase...", "INFO")
            self._clear_old_embeddings()
            self.log("Old embeddings cleared", "SUCCESS")

            # Step 3: Generate embeddings
            self.log("Step 2/3: Generating embeddings...", "INFO")
            self.log("This may take several minutes depending on dataset size...", "INFO")
            self._run_embed_script()
            self.log("Embeddings generated successfully!", "SUCCESS")

            # Step 4: Upload embeddings to Supabase
            self.log("Step 3/3: Uploading embeddings to Supabase...", "INFO")
            self._run_upload_script()
            self.log("Embeddings uploaded successfully!", "SUCCESS")

            self.log("=" * 80)
            self.log("FLOW 2 COMPLETED SUCCESSFULLY!", "SUCCESS")
            self.log("=" * 80)
            self.log("Semantic search is now updated and ready to use!", "INFO")

            self._finish_flow(success=True)

        except Exception as e:
            self.log(f"ERROR: {str(e)}", "ERROR")
            self.log("Flow 2 failed!", "ERROR")
            self._finish_flow(success=False, error=str(e))

    def _finish_flow(self, success=True, error=None):
        """Finish flow execution"""
        self.progress.stop()
        self.is_running = False
        self.set_buttons_state("normal")

        if success:
            messagebox.showinfo("Success", "Flow completed successfully!")
        else:
            messagebox.showerror("Error", f"Flow failed!\n\nError: {error}")

    # ========== Flow 1 Helper Methods ==========

    def _fetch_unmatched_items(self):
        """Fetch all items from items_without_pictures table"""
        try:
            self.log("Connecting to Supabase...", "INFO")
            supabase = get_supabase_client()

            # Fetch ALL items regardless of processed status
            self.log("Fetching all rows from items_without_pictures table...", "INFO")
            response = supabase.table('items_without_pictures') \
                .select('id, title, description, processed') \
                .execute()

            self.log(f"Raw response: {response}", "INFO")
            self.log(f"Response data type: {type(response.data)}", "INFO")
            self.log(f"Number of items fetched: {len(response.data) if response.data else 0}", "INFO")

            return response.data
        except Exception as e:
            self.log(f"Exception details: {str(e)}", "ERROR")
            raise Exception(f"Failed to fetch items from items_without_pictures: {str(e)}")

    def _create_input_csv(self, items):
        """Create input.csv for Ollama script"""
        CSV_TO_TEXT_DIR.mkdir(parents=True, exist_ok=True)

        with open(INPUT_CSV, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['title', 'short_description', 'precise_content'])
            writer.writeheader()

            for item in items:
                writer.writerow({
                    'title': item.get('title', ''),
                    'short_description': item.get('description', ''),
                    'precise_content': item.get('description', '')  # Use description as precise_content
                })

    def _run_ollama_script(self):
        """Run Ollama script to generate prompts"""
        if not OLLAMA_SCRIPT.exists():
            raise FileNotFoundError(f"Ollama script not found at {OLLAMA_SCRIPT}")

        # Check if Ollama is running
        try:
            result = subprocess.run(
                ['curl', '-s', 'http://127.0.0.1:11434/api/tags'],
                capture_output=True,
                timeout=5
            )
            if result.returncode != 0:
                raise Exception("Ollama is not running. Please start Ollama first.")
        except subprocess.TimeoutExpired:
            raise Exception("Ollama is not responding. Please check if it's running.")
        except FileNotFoundError:
            # curl not available on Windows, skip check
            pass

        # Run script
        result = subprocess.run(
            [sys.executable, str(OLLAMA_SCRIPT)],
            cwd=str(CSV_TO_TEXT_DIR),
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            raise Exception(f"Ollama script failed:\n{result.stderr}")

        # Log output
        for line in result.stdout.split('\n'):
            if line.strip():
                self.log(line, "INFO")

    def _update_prompts_meta(self):
        """Update prompts_meta.csv with new entries from Ollama output"""
        # Read existing prompts_meta.csv if it exists
        existing_rows = []
        if PROMPTS_META_CSV.exists():
            with open(PROMPTS_META_CSV, 'r', encoding='utf-8', newline='') as f:
                reader = csv.DictReader(f)
                existing_rows = list(reader)

        # Read new entries from Ollama output (they're already in prompts_meta.csv)
        # The Ollama script appends to prompts_meta.csv, but we want to deduplicate
        with open(PROMPTS_META_CSV, 'r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            all_rows = list(reader)

        # Deduplicate by name
        seen = set()
        unique_rows = []
        for row in all_rows:
            name = row.get('name', '')
            if name not in seen:
                seen.add(name)
                unique_rows.append(row)

        # Write back deduplicated data
        with open(PROMPTS_META_CSV, 'w', encoding='utf-8', newline='') as f:
            if unique_rows:
                fieldnames = list(unique_rows[0].keys())
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(unique_rows)

        self.log(f"Total unique entries in prompts_meta.csv: {len(unique_rows)}", "INFO")

    def _mark_items_processed(self, items):
        """Mark items as processed in Supabase"""
        try:
            supabase = get_supabase_client()
            item_ids = [item['id'] for item in items]

            supabase.table('items_without_pictures') \
                .update({'processed': True}) \
                .in_('id', item_ids) \
                .execute()

        except Exception as e:
            raise Exception(f"Failed to mark items as processed: {str(e)}")

    # ========== Flow 2 Helper Methods ==========

    def _clear_old_embeddings(self):
        """Clear old embeddings from Supabase"""
        try:
            supabase = get_supabase_client()

            # Delete all rows from dish_embeddings
            supabase.table('dish_embeddings').delete().neq('id', 0).execute()

            self.log("Deleted all old embeddings", "INFO")

        except Exception as e:
            # If table is empty, this might fail - that's OK
            self.log(f"Note: {str(e)}", "INFO")

    def _run_embed_script(self):
        """Run embedding generation script"""
        if not EMBED_SCRIPT.exists():
            raise FileNotFoundError(f"Embed script not found at {EMBED_SCRIPT}")

        if not PROMPTS_META_CSV.exists():
            raise FileNotFoundError(f"prompts_meta.csv not found at {PROMPTS_META_CSV}")

        # Run script
        result = subprocess.run(
            [sys.executable, str(EMBED_SCRIPT)],
            cwd=str(CLEAN_DISH_DIR),
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            raise Exception(f"Embed script failed:\n{result.stderr}")

        # Log output
        for line in result.stdout.split('\n'):
            if line.strip():
                self.log(line, "INFO")

    def _run_upload_script(self):
        """Run upload embeddings script"""
        if not UPLOAD_SCRIPT.exists():
            raise FileNotFoundError(f"Upload script not found at {UPLOAD_SCRIPT}")

        embeddings_dir = CLEAN_DISH_DIR / "embeddings"
        if not embeddings_dir.exists():
            raise FileNotFoundError(f"Embeddings directory not found at {embeddings_dir}")

        # Run script
        result = subprocess.run(
            [
                sys.executable,
                str(UPLOAD_SCRIPT),
                '--csv-path', str(PROMPTS_META_CSV),
                '--embeddings-dir', str(embeddings_dir)
            ],
            cwd=str(BACKEND_DIR),
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            raise Exception(f"Upload script failed:\n{result.stderr}")

        # Log output
        for line in result.stdout.split('\n'):
            if line.strip():
                self.log(line, "INFO")


def main():
    # Check paths exist
    issues = []

    if not CSV_TO_TEXT_DIR.exists():
        issues.append(f"CSV-to-structured-text directory not found at {CSV_TO_TEXT_DIR}")
    if not CLEAN_DISH_DIR.exists():
        issues.append(f"Clean-dish-list directory not found at {CLEAN_DISH_DIR}")
    if not OLLAMA_SCRIPT.exists():
        issues.append(f"Ollama script not found at {OLLAMA_SCRIPT}")
    if not EMBED_SCRIPT.exists():
        issues.append(f"Embed script not found at {EMBED_SCRIPT}")
    if not UPLOAD_SCRIPT.exists():
        issues.append(f"Upload script not found at {UPLOAD_SCRIPT}")

    # Check environment variables
    if not os.getenv('SUPABASE_URL'):
        issues.append("SUPABASE_URL not set in environment variables")
    if not (os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_ANON_KEY')):
        issues.append("SUPABASE_SERVICE_ROLE_KEY or SUPABASE_ANON_KEY not set in environment variables")

    if issues:
        print("Setup Issues Found:")
        for issue in issues:
            print(f"  ✗ {issue}")
        print("\nPlease fix these issues before running the GUI.")
        return

    # Create and run GUI
    root = tk.Tk()
    app = SemanticSearchGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
