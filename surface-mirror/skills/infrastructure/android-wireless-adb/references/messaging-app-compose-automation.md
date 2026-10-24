# Messaging App Compose Automation

Jetpack Compose messaging apps (Simplex Chat, Signal, etc.) render off the accessibility tree, making `uiautomator dump` useless and `screencap` unreliable when FLAG_SECURE is active. This reference covers the reliable automation patterns discovered through Simplex Chat work on Cyclone-C4.

## Simplex Chat Specifics

### Database Locations

Simplex v7 keeps its SQLCipher-encrypted databases at the app-data ROOT, not in `databases/`:

```
/data/data/chat.simplex.app/files_chat.db    # messages/connections (~100MB+)
/data/data/chat.simplex.app/files_agent.db   # SMP agent state (~20MB+)
```

An empty `databases/` directory is normal — do not conclude the DBs are missing from that. Both files have encrypted headers (no `SQLite format 3` magic); verify health by reopening the app and checking the DB mtime updates (clean checkpoint), not by reading bytes. The app creates `*.db.bak.<timestamp>` siblings next to them on export/backup events.

### Media Storage Locations

Simplex stores downloaded media in two places:

| Location | Contents | Size (typical) |
|---|---|---|
| `/storage/emulated/0/Pictures/SimpleX_Media/` | Images, GIFs, small videos from direct chats | ~600MB |
| `/storage/emulated/0/DCIM/Movies/` | Videos from groups/rooms (auto-downloaded) | ~30GB |
| `/data/data/chat.simplex.app/files/` | App-private DB, temp files, encrypted cache | ~200MB |

Group/room videos land in DCIM/Movies because Simplex uses the system download manager for large files, which places them in the shared DCIM tree. Images land in SimpleX_Media via direct app writes.

### Disabling Screen Protection (FLAG_SECURE)

Simplex sets FLAG_SECURE via `PrivacyProtectScreen` in shared_prefs. When `true`, both `adb exec-out screencap -p` and framebuffer reads return 0 bytes or pure black. The fix requires root:

```bash
# 1. Pull prefs
adb shell su -c "cat /data/data/chat.simplex.app/shared_prefs/chat.simplex.app.SIMPLEX_APP_PREFS.xml > /sdcard/sx_prefs.xml"
adb pull /sdcard/sx_prefs.xml ./

# 2. Edit locally: change PrivacyProtectScreen from true to false
# 3. Push back
adb push sx_prefs.xml /sdcard/sx_prefs_new.xml
adb shell su -c "cat /sdcard/sx_prefs_new.xml > /data/data/chat.simplex.app/shared_prefs/chat.simplex.app.SIMPLEX_APP_PREFS.xml"
adb shell am force-stop chat.simplex.app
```

After restart, `su -c 'screencap /sdcard/shot.png'` produces valid PNGs. `adb exec-out screencap -p` may still return 0 bytes on some Android builds — always use the `su` + pull pattern.

### Passphrase Entry Automation

Simplex with `LocalAuthenticationMode=PASSCODE` shows a passphrase screen on cold start. Automation:

```bash
adb shell input text '<passphrase>'
sleep 1
adb shell input keyevent 66  # ENTER
sleep 4  # Wait for decryption
```

After passphrase entry, Simplex may show a "Your current profile" setup screen asking to "Save and notify contacts". This is a one-time migration prompt. Dismissing it requires tapping the save button — coordinate-based since Compose blocks uiautomator.

### Coordinate-Based Navigation

Since Compose has no exposed view hierarchy, automation relies on screenshot → tap coordinate → screenshot confirmation loops.

Key patterns:
- **Chat list items**: tap on the avatar (left side) rather than text area to avoid triggering search/keyboard
- **List scrolling**: use `input swipe` with device coordinates; verify position with fresh screenshot after each scroll
- **Back navigation**: `input keyevent 4` (BACK) works, but on Compose apps it may open recents instead of going back — use the visible back arrow if present
- **Keyboard dismissal**: `input keyevent 4` when keyboard is open; if that triggers back, use `input tap` on a non-input area

### Checking Relay Connectivity

Simplex maintains persistent TCP:443 connections to SMP relays. Verify connectivity:

```bash
SIMPLEX_PID=$(adb shell "ps -A | grep chat.simplex.app | awk '{print $2}'" | tr -d '\r')
adb shell "cat /proc/$SIMPLEX_PID/net/tcp6 | grep -c -v '00000000000000000000000000000000:0000'"
```

A healthy Simplex instance shows 10–25 active connections. Decode addresses from `/proc/<pid>/net/tcp6` — IPv4-mapped addresses appear as `0000000000000000FFFF0000<hex-ip>:<hex-port>`.

### On-Device Media Organization

When the user wants media organized on the phone (not pulled to host), create a shell script that runs via `su` and copies from source locations to a destination tree:

```bash
DEST="/storage/emulated/0/SimplexGroups"
mkdir -p "$DEST/AllMedia" "$DEST/Videos" "$DEST/Images"

# Collect from both Simplex locations
cp /storage/emulated/0/Pictures/SimpleX_Media/* "$DEST/AllMedia/" 2>/dev/null
cp /storage/emulated/0/DCIM/Movies/* "$DEST/AllMedia/" 2>/dev/null

# Sort by type
mv "$DEST/AllMedia/"*.mp4 "$DEST/Videos/" 2>/dev/null
mv "$DEST/AllMedia/"*.jpg "$DEST/Images/" 2>/dev/null
```

For bulk operations on thousands of files, `find ... -exec cp` is slow. Use `cp` with wildcards for known extensions, or `tar` piped to extraction for large moves.

## Duplicate File Cleanup

Android download managers often create duplicates with `(1)`, `(2)`, `(3)` suffixes. These are safe to remove — they're byte-for-byte copies from retry loops or multiple download triggers.

```bash
# Count duplicates
find /storage/emulated/0/DCIM/Movies/ -maxdepth 1 -type f -name '*\(1\)*' | wc -l

# Delete duplicates (run on device)
find /storage/emulated/0/DCIM/Movies/ -maxdepth 1 -type f -name '*\(1\)*' -delete
find /storage/emulated/0/DCIM/Movies/ -maxdepth 1 -type f -name '*\(2\)*' -delete
find /storage/emulated/0/DCIM/Movies/ -maxdepth 1 -type f -name '*\(3\)*' -delete
```

Always verify remaining files with `du -sh` and `find ... | wc -l` after cleanup.

## Pitfalls

- **Storage at 100% causes silent failures.** `screencap`, `cp`, and even `sqlite3` writes fail silently when `/data` is full. Always check `df -h /data` before bulk operations.
- **Simplex Compose list shifts after each tap.** A chat at y≈520 in one screenshot may move to y≈460 after a scroll or keyboard dismiss. Never reuse coordinates across screenshots without re-verification.
- **Group chat vs private chat confusion.** Simplex shows the same contact name for both direct chats and group memberships. Tapping the wrong entry opens a group instead of private chat. Use the preview text to distinguish: group entries show system messages like "GC RULES" or "Audio/video calls: enabled".
- **ExpressVPN and similar VPN apps may change network interfaces.** When a VPN connects, it may briefly drop ADB wireless connections. Reconnect with `adb connect <ip>:5555` after VPN state changes.
