#!/data/data/com.termux/files/usr/bin/python
"""
Phone-native SimpleX video archiver for Cyclone-C4.
Watches the official SimpleX app's received-files directory and moves
any incoming videos directly to the SD card (internal or physical).

No CLI or WebSocket required — just polls the app's app_files folder.
"""

import os
import shutil
import time
from datetime import datetime
from pathlib import Path

# Where the official SimpleX app drops received files
SRC_DIR = Path("/data/data/chat.simplex.app/files/app_files")

# Primary destination on the phone (internal storage)
ARCHIVE_ROOT = Path("/sdcard/SimplexVideos")

# Also try to mirror to the physical SD card if mounted
PHYSICAL_SD = Path("/storage/0403-0201/SimplexVideos")

VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv", ".m4v", ".3gp", ".ts"
}


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(ARCHIVE_ROOT / "watcher.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def is_video(name: str) -> bool:
    return Path(name).suffix.lower() in VIDEO_EXTENSIONS


def move_to_sd(src: Path):
    date_str = datetime.now().strftime("%Y-%m-%d")
    dest_dir = ARCHIVE_ROOT / date_str
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest = dest_dir / src.name
    counter = 1
    while dest.exists():
        dest = dest_dir / f"{src.stem}_{counter}{src.suffix}"
        counter += 1

    try:
        shutil.move(str(src), str(dest))
        log(f"Moved to internal SD: {dest}")
    except Exception as e:
        log(f"Failed to move {src.name}: {e}")
        return

    # Try physical SD card as well
    try:
        phys_dir = PHYSICAL_SD / date_str
        phys_dir.mkdir(parents=True, exist_ok=True)
        phys_dest = phys_dir / dest.name
        shutil.copy2(str(dest), str(phys_dest))
        log(f"Also copied to physical SD: {phys_dest}")
    except Exception as e:
        log(f"Physical SD copy skipped: {e}")


def main():
    ARCHIVE_ROOT.mkdir(parents=True, exist_ok=True)
    log("Starting phone-native SimpleX video watcher on Cyclone-C4")
    log(f"Watching: {SRC_DIR}")

    seen = set()

    while True:
        try:
            if not SRC_DIR.exists():
                time.sleep(10)
                continue

            for f in SRC_DIR.iterdir():
                if f.is_file() and is_video(f.name) and f.name not in seen:
                    move_to_sd(f)
                    seen.add(f.name)

            # Keep seen set from growing forever
            if len(seen) > 500:
                seen.clear()

            time.sleep(8)
        except KeyboardInterrupt:
            log("Watcher stopped")
            break
        except Exception as e:
            log(f"Error: {e}")
            time.sleep(15)


if __name__ == "__main__":
    main()
