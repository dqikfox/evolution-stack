#!/usr/bin/env python3
import os
import shutil
import sys
from datetime import datetime

def log(message):
    print(f"[{datetime.now().isoformat()}] {message}")

def main():
    log("Starting Robust Nexus Sync...")
    source_dir = r'//Msi/e/ultron-memory/Lessons'
    dest_param = r'C:\Users\KING\Projects\TESSERACT\docs\nexus_sync_cache'
    # Let's use a simpler dest path for testing if the primary one fails
    dest_dir = dest_param 
    
    if not os.path.exists(source_dir):
        log(f"ERROR: Source directory NOT found or inaccessible: {source_dir}")
        sys.exit(1)

    try:
        if os.path.exists(dest_dir):
            log("Cleaning old cache...")
            shutil.rmtree(dest_dir)
        os.makedirs(dest_dir, exist_ok=True)

        log(f"Syncing files from {source_dir} to {dest_dir}...")
        file_count = 0
        for root, dirs, files in os.walk(source_dir):
            rel_path = os.path.relpath(root, source_dir)
            target_subdir = os.path.join(dest_dir, rel_path)
            if not os.path.exists(target_subdir):
                os.makedirs(target_subdir, exist_ok=True)

            for f in files:
                src_file = os.path.join(root, f)
                dst_file = os.path.join(target_subdir, f)
                log(f"Copying {f}...")
                shutil.copy2(src_file, dst_file)
                file_count += 1
        
        log(f"Sync completed successfully. {file_count} files processed.")
    except Exception as e:
        log(f"ERROR during sync process: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
