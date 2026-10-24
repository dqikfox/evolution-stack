#!/system/bin/sh
# On-Device Media Organizer — runs entirely on Android via su
# Usage: push to /data/local/tmp/, chmod 755, run with su
#
# Configurable: edit SRC and DEST below, then execute on device.

SRC_MEDIA="/storage/emulated/0/Pictures/SimpleX_Media"
SRC_DCIM="/storage/emulated/0/DCIM/Movies"
DEST_BASE="/storage/emulated/0/AppMediaExport"

echo "=== On-Device Media Organizer ==="
echo "Device: $(getprop ro.product.model)"
echo "Time: $(date)"
echo ""

mkdir -p "$DEST_BASE/AllMedia"
mkdir -p "$DEST_BASE/Videos"
mkdir -p "$DEST_BASE/Images"
mkdir -p "$DEST_BASE/ByDate"

echo "[1/4] Collecting from app media folders..."
# Use cp -r for directories, cp for wildcards
if [ -d "$SRC_MEDIA" ]; then
    cp "$SRC_MEDIA/"*.* "$DEST_BASE/AllMedia/" 2>/dev/null
fi
if [ -d "$SRC_DCIM" ]; then
    cp "$SRC_DCIM/"*.* "$DEST_BASE/AllMedia/" 2>/dev/null
fi

echo "[2/4] Organizing by file type..."
for f in "$DEST_BASE/AllMedia/"*; do
    [ -f "$f" ] || continue
    case "$f" in
        *.mp4|*.mov|*.avi|*.m4v|*.webm|*.3gp|*.MP4|*.MOV|*.AVI|*.M4V)
            mv "$f" "$DEST_BASE/Videos/" 2>/dev/null ;;
        *.jpg|*.jpeg|*.png|*.gif|*.webp|*.bmp|*.JPG|*.JPEG|*.PNG|*.GIF)
            mv "$f" "$DEST_BASE/Images/" 2>/dev/null ;;
    esac
done

echo "[3/4] Organizing by date (from filenames)..."
for f in "$DEST_BASE/Videos/"* "$DEST_BASE/Images/"*; do
    [ -f "$f" ] || continue
    BASENAME=$(basename "$f")
    DATE=""
    # video_YYYYMMDD_*
    if echo "$BASENAME" | grep -qE '^video_[0-9]{8}'; then
        DATE=$(echo "$BASENAME" | sed 's/video_\([0-9]\{8\}\).*/\1/')
    # IMG_YYYYMMDD_*
    elif echo "$BASENAME" | grep -qE '^IMG_[0-9]{8}'; then
        DATE=$(echo "$BASENAME" | sed 's/IMG_\([0-9]\{8\}\).*/\1/')
    fi
    if [ -n "$DATE" ] && [ "$DATE" != "$BASENAME" ]; then
        mkdir -p "$DEST_BASE/ByDate/$DATE"
        cp "$f" "$DEST_BASE/ByDate/$DATE/" 2>/dev/null
    fi
done

echo "[4/4] Generating stats..."
TOTAL=$(find "$DEST_BASE/AllMedia" -type f 2>/dev/null | wc -l)
VIDEOS=$(find "$DEST_BASE/Videos" -type f 2>/dev/null | wc -l)
IMAGES=$(find "$DEST_BASE/Images" -type f 2>/dev/null | wc -l)
DATES=$(find "$DEST_BASE/ByDate" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)
SIZE=$(du -sh "$DEST_BASE" 2>/dev/null | awk '{print $1}')

echo ""
echo "=== RESULTS ==="
echo "Total files: $TOTAL"
echo "Videos: $VIDEOS"
echo "Images: $IMAGES"
echo "Date folders: $DATES"
echo "Storage used: $SIZE"
echo "Location: $DEST_BASE"
echo ""

# Create index
echo "Creating index..."
INDEX="$DEST_BASE/INDEX.txt"
echo "MEDIA INDEX" > "$INDEX"
echo "Generated: $(date)" >> "$INDEX"
echo "Files: $TOTAL" >> "$INDEX"
echo "Videos: $VIDEOS" >> "$INDEX"
echo "Images: $IMAGES" >> "$INDEX"
echo "" >> "$INDEX"
echo "FILE LIST:" >> "$INDEX"
ls -la "$DEST_BASE/Videos/" >> "$INDEX" 2>/dev/null
ls -la "$DEST_BASE/Images/" >> "$INDEX" 2>/dev/null

echo "Index saved: $INDEX"
echo "=== DONE ==="
