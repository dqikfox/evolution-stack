#!/data/data/com.termux/files/usr/bin/python
"""
Phone-native SimpleX media archiver for Cyclone-C4 (enhanced v2).
- Real-time watcher on the ephemeral app_files folder (new incoming videos)
- Periodic deep scan of SimplexGroups (already-saved group/room videos)
- Moves everything into dated folders on internal SD + physical SD mirror
"""

import os
import shutil
import time
from datetime import datetime
from pathlib import Path

# Real-time source (new downloads)
SRC_DIR = Path("/data/data/chat.simplex.app/files/app_files")

# Historical group media
GROUPS_DIRS = [
    Path("/sdcard/SimplexGroups/Videos"),
    Path("/sdcard/SimplexGroups/Rooms"),
    Path("/sdcard/SimplexGroups/Groups"),
]

# Destinations
ARCHIVE_ROOT = Path("/sdcard/SimplexVideos")
PHYSICAL_SD = Path("/storage/0403-0201/SimplexVideos")

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv", ".m4v", ".3gp", ".ts"}


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


def already_archived(name: str) -> bool:
    """Check if a file with this name already exists in the archive (any date folder)."""
    for d in ARCHIVE_ROOT.glob("*/"):
        if (d / name).exists():
            return True
    return False


def move_to_archive(src: Path, reason: str = ""):
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
        log(f"Moved ({reason}): {src.name} -> {dest}")
    except Exception as e:
        log(f"Move failed {src.name}: {e}")
        return

    # Mirror to physical SD
    try:
        phys_dir = PHYSICAL_SD / date_str
        phys_dir.mkdir(parents=True, exist_ok=True)
        phys_dest = phys_dir / dest.name
        shutil.copy2(str(dest), str(phys_dest))
        log(f"Mirrored to physical SD: {phys_dest}")
    except Exception as e:
        log(f"Physical SD mirror skipped: {e}")


def scan_ephemeral():
    """Real-time poll of the app's temporary receive folder."""
    if not SRC_DIR.exists():
        return
    for f in list(SRC_DIR.iterdir()):
        if f.is_file() and is_video(f.name) and not already_archived(f.name):
            move_to_archive(f, "ephemeral")


def scan_groups():
    """Deep scan of already-saved group/room media."""
    for base in GROUPS_DIRS:
        if not base.exists():
            continue
        for f in base.rglob("*"):
            if f.is_file() and is_video(f.name) and not already_archived(f.name):
                move_to_archive(f, f"groups:{base.name}")


def main():
    ARCHIVE_ROOT.mkdir(parents=True, exist_ok=True)
    log("Starting enhanced SimpleX media archiver v2 on Cyclone-C4")
    log(f"Real-time source: {SRC_DIR}")
    log(f"Group scan sources: {GROUPS_DIRS}")

    last_deep_scan = 0

    while True:
        try:
            # Always do the fast ephemeral poll
            scan_ephemeral()

            # Do a full groups scan every 5 minutes
            now = time.time()
            if now - last_deep_scan > 300:
                log("Starting deep scan of SimplexGroups...")
                scan_groups()
                last_deep_scan = now
                log("Deep scan complete")

            time.sleep(8)
        except KeyboardInterrupt:
            log("Watcher stopped by user")
            break
        except Exception as e:
            log(f"Error: {e}")
            time.sleep(20)


if __name__ == "__main__":
    main()
