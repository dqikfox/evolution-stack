# ADB Android Device Operations

The class-level procedure for driving an Android phone from THRONE via ADB:
reach it on Tailscale or LAN, push a file or install an APK, drive the UI,
verify what the screen shows, and pull data back. Phones under THRONE control
include Cyclone-C4 (rooted test rig), S19, S23, and any device Hitchy
connects over USB or `adb connect`.

## Reach the device

```bash
# USB-connected
adb devices

# Tailnet (Android Tailscale IP)
adb connect 100.71.239.65:5555

# Direct LAN
adb connect 192.168.4.241:5555

# Confirm
adb -s 100.71.239.65:5555 shell "getprop ro.product.cpu.abi; getprop ro.build.version.release"
```

When the user says "the phone" or "my phone", verify the address is alive
and reachable on Tailscale *and* the LAN before doing anything else —
`tailscale status` shows every device with a `lastSeen` timestamp, so a
peer that says "phone" but has been offline for 58 days is not the
phone. Always read the live `tailscale status` before assuming.

## ABI compatibility — the install that almost always fails first

F-Droid, Google Play, and many first-party sites now ship **arm64-only**
APKs. Many older or test-rig devices (Cyclone-C4 = `armeabi-v7a`) will
reject these with `INSTALL_FAILED_NO_MATCHING_ABIS: Failed to extract
native libraries, res=-113`.

**Before downloading a full APK, probe ABI first:**

```bash
adb -s SERIAL shell "getprop ro.product.cpu.abi"
# Output: armeabi-v7a  (32-bit)  or  arm64-v8a  (64-bit)
```

If 32-bit and F-Droid's APK is arm64-only, **check GitHub releases
for an armv7a build**. Many F-Droid packages are upstream GitHub
projects that publish per-ABI APKs. Worked example: Simplex Chat v7.0.4
on F-Droid is 64-bit only; the v7.0.4 GitHub release asset
`simplex-armv7a.apk` is 94.6 MB and installs cleanly on armv7a devices.

## Install an APK from a URL

```bash
# 1. Download
curl -L -o /tmp/app.apk "https://example.com/app.apk"

# 2. Verify it's a real ZIP/APK (magic bytes)
python -c "data = open('/tmp/app.apk','rb').read(2); print('APK' if data == b'PK' else f'unknown: {data!r}')"

# 3. Push
adb -s SERIAL push /tmp/app.apk /data/local/tmp/app.apk

# 4. Install (use pm install not just "adb install" — same thing, but
#    pm install with -r reinstalls over an existing package without
#    needing uninstall first)
adb -s SERIAL shell "pm install -r /data/local/tmp/app.apk"

# 5. Verify
adb -s SERIAL shell "pm list packages | grep <id>"
```

The install can take 30-90 s on first run while Android verifies
signatures. If `adb install` times out, the package may still have
installed — always `pm list packages` to confirm before retrying.

## Drive the UI without a screen

There are three layers: **input events** (tap/swipe/key), **uiautomator
dumps** (textual read of the visible UI), and **screenshots** (visual
read). Each has a different failure mode.

### Input events

```bash
# Tap at coordinates (origin top-left, screen size from wm size)
adb -s SERIAL shell "wm size"          # e.g. 720x1612
adb -s SERIAL shell "input tap 360 1205"
adb -s SERIAL shell "input keyevent KEYCODE_BACK"
adb -s SERIAL shell "input text 'Hello world'"   # ASCII only, %s for space
```

### Screenshot — when it works and when it doesn't

```bash
# File mode
adb -s SERIAL exec-out screencap -p > /tmp/shot.png
ls -la /tmp/shot.png    # MUST be > 0 bytes — see pitfall
```

**Pitfall — `screencap` returns 0 bytes on FLAG_SECURE or protected render surfaces.**
Apps that set `FLAG_SECURE` (Simplex Chat, banking apps, some messengers) or apps using Jetpack Compose/Skia hardware layers block `screencap` via the `exec-out` pipe. Symptom: the pulled file is 0 bytes or the piped output is empty.

**Two fixes, in order of preference:**

1. **Disable FLAG_SECURE in shared_prefs** (when the app exposes a toggle):
   ```bash
   adb -s SERIAL shell "su -c 'cat /data/data/<package>/shared_prefs/<prefs>.xml'" > /tmp/prefs.xml
   # Edit locally: change PrivacyProtectScreen/true to false, etc.
   adb -s SERIAL push /tmp/prefs.xml /sdcard/prefs.xml
   adb -s SERIAL shell "su -c 'cp /sdcard/prefs.xml /data/data/<package>/shared_prefs/<prefs>.xml'"
   adb -s SERIAL shell "am force-stop <package>"
   adb -s SERIAL shell "am start -n <package>/.MainActivity"
   ```

2. **Use root file-write screencap** (works even when FLAG_SECURE blocks exec-out):
   ```bash
   adb -s SERIAL shell "su -c 'screencap /sdcard/shot.png'"
   adb -s SERIAL pull /sdcard/shot.png /tmp/shot.png
   # File will be non-zero when the pipe method was failing
   ```

The `su -c 'screencap /sdcard/...'` path bypasses the pipe buffer restriction that FLAG_SECURE targets. Always verify the output file size after any screencap — a 0-byte result usually means either FLAG_SECURE is active or the device storage is full (see below).

```bash
# Streamed screencap (one more path that may bypass the 0-byte issue)
adb -s SERIAL exec-out screencap -p > /tmp/shot.png
# If that 0-bytes, fall back to root file-write or uiautomator dump
```

### `uiautomator dump` — the structural fallback (NOT universal)

```bash
adb -s SERIAL shell "uiautomator dump /sdcard/ui.xml"
adb -s SERIAL pull /sdcard/ui.xml /tmp/ui.xml
# Parse the text attributes
grep -oE 'text="[^"]+"' /tmp/ui.xml | head -20
# Parse the clickable bounds
grep -oE '(text|bounds|content-desc)="[^"]+"' /tmp/ui.xml
```

Bounds are `[x1,y1][x2,y2]`. Center is `((x1+x2)/2, (y1+y2)/2)`. Use
those to drive the next `input tap`. `uiautomator dump` is slow (1-3 s
per dump) and works on traditional View-based UIs, but **returns empty or near-empty XML for Jetpack Compose apps** (Android 16+). Compose renders off the standard view hierarchy, so the accessibility tree the dump reads contains only the window chrome, not the actual content. Simplex Chat, modern Telegram, and many 2024+ apps are Compose-only.

**When uiautomator dump fails, the only remaining options are:**
1. Root-enabled screencap with `su -c 'screencap /sdcard/...'` (if FLAG_SECURE is disabled or bypassed)
2. Coordinate-based `input tap` navigation using trial-and-error with screencap verification after each tap
3. Direct file inspection (`shared_prefs`, databases, etc.) when the app's config is file-based

After every tap, re-dump — if the screen changes and the dump is still empty, you're dealing with a Compose app and must switch to screencap-driven navigation.

## Media files: where Android puts them

| What | Path |
|---|---|
| User-pushed files | `/sdcard/Download/` |
| App-private storage | `/data/data/<package>/files/` (root needed for read) |
| App cache | `/data/data/<package>/cache/` |
| Telegram downloads | `/data/data/org.telegram.messenger.web/cache/` or `/storage/emulated/0/Telegram/Telegram Audio/` |
| Music auto-download | `/sdcard/Music/` or `/sdcard/Podcasts/` |

Push an MP3 to play locally:

```bash
adb -s SERIAL push /tmp/voice.mp3 /sdcard/Download/voice.mp3

# Launch with a generic media player
adb -s SERIAL shell "am start -a android.intent.action.VIEW \
  -d file:///sdcard/Download/voice.mp3 -t audio/mpeg"
```

`am start` returns "Activity not started, its current task has been
brought to the front" if the same intent is already running — that's
not a failure, it just means a chooser or media session was reused.

## Sign-in flows without a SIM

When the phone has no SIM (signal strength all `2147483647` =
`Integer.MAX_VALUE` = no service), Telegram/WhatsApp/etc. can't receive
SMS codes. Some apps support a **"send code to another signed-in
device"** flow that lets you complete sign-in via a code delivered to
a Telegram Desktop / WhatsApp Web session signed in on THRONE.

If the Telegram app shows "We've sent the code to the Telegram app for
+61 XXX XXX XXX on your other device", the code is on THRONE's Telegram
Desktop. Read the chat manually — Telegram Desktop's `tdata/` is locked
while the app runs, so do NOT try to parse it programmatically. Surface
the chat to the user and let them read the code.

## Read user info from the booted session

```bash
# Current user + permissions
adb -s SERIAL shell "dumpsys window windows | grep -i mCurrentFocus"

# Telephony status (signal strength = 2147483647 means no SIM)
adb -s SERIAL shell "dumpsys telephony.registry | grep mSignalStrength"

# Open notifications
adb -s SERIAL shell "dumpsys notification | head -50"
```

## Rooted phones — extra capabilities

Cyclone-C4 has Magisk. After any ADB connect, you can `adb root` to
get shell as root, which unlocks:

- Read/write any `/data/data/<package>/` without `run-as`
- Modify system files
- Pull app databases directly (e.g. Simplex's chat database)

```bash
adb -s SERIAL root
adb -s SERIAL shell "ls /data/data/chat.simplex.app/files/"
```

## Common operation gotchas

1. **Multiple devices, ambiguous `adb -s`.** If `adb devices` shows two
   rows for the same phone (one USB, one TCP), always pass `-s <serial>`
   explicitly. `adb` may pick the wrong one for a bare `shell`.

2. **`adb install` fails after APK push with "No such file"** because
   bash stripped the path. Use `adb -s SERIAL push LOCAL REMOTE` with
   the device path in single quotes if it contains spaces.

3. **Telegram install registers `org.telegram.messenger.web` only.**
   The official Telegram APK now uses `.messenger.web` as the
   application ID (the .messenger package is a stub). The launcher
   activity is `org.telegram.messenger.web/org.telegram.messenger.DefaultIcon`,
   NOT `org.telegram.messenger.ui.LaunchActivity`. If `am start` errors
   with "Activity class does not exist", check
   `cmd package resolve-activity --brief -c android.intent.category.LAUNCHER <pkg>`
   to find the right one.

4. **STUN/TURN-required apps fail at first launch on a phone with no
   SIM.** Telegram, WhatsApp, Signal all need a phone number to send
   the SMS code. The "send code to another device" path is the
   only fallback for a SIM-less device.

5. **PowerShell variable `$pid` is reserved.** When writing a
   PowerShell ADB helper that uses `[Win32]::GetWindowThreadProcessId`,
   use a name like `$procId` or `$targetPid`. PowerShell's auto-var
   `$pid` is read-only and writes fail with cryptic "Cannot overwrite
   variable PID" errors.

6. **Capture window through `MainWindowHandle` with `SetWindowPos`
   `HWND_TOPMOST`** to bring a background app forward for a screenshot,
   but be aware some Windows apps render as black when the parent
   compositor is mid-redraw. Take two screenshots ~2 s apart and pick
   the non-black one.

7. **Storage-full causes silent 0-byte outputs.** When `/data` is 100% full,
   `screencap` writes 0-byte files, `cp` fails with "No space left on device",
   and temp file creation silently fails. Before debugging mysterious 0-byte
   screenshots or failed file operations, always check:
   ```bash
   adb -s SERIAL shell "df -h /data"
   ```
   If Use% is 100%, clear space before proceeding — old media in
   `/sdcard/Movies/`, `/sdcard/Pictures/`, app caches, and downloaded
   archives are the usual culprits.

8. **Jetpack Compose UI coordinate navigation is unreliable.** Compose lists
   shift dynamically — tapping at a fixed coordinate to select a list item
   will hit the wrong row if the list scrolls or if multiple items share the
   same text. When multiple contacts/groups have identical names (e.g., two
   "anomy" entries), coordinate taps may open the wrong one. The only
   workaround is trial-and-error: tap, screenshot, verify the opened screen,
   and adjust coordinates. There is no programmatic "find element by text"
   for Compose apps via standard ADB tools.

9. **Shared_prefs editing for app configuration bypasses UI navigation.**
   Many apps store settings (proxy toggles, security flags, theme choices)
   in `/data/data/<package>/shared_prefs/*.xml`. With root access, you can
   read these files, edit them locally, and push them back — bypassing
   the need to navigate Compose settings screens entirely. Always
   force-stop and restart the app after editing prefs for changes to take
   effect:
   ```bash
   adb -s SERIAL shell "su -c 'cat /data/data/<pkg>/shared_prefs/<file>.xml'" > /tmp/prefs.xml
   # edit /tmp/prefs.xml locally
   adb -s SERIAL push /tmp/prefs.xml /sdcard/
   adb -s SERIAL shell "su -c 'cp /sdcard/prefs.xml /data/data/<pkg>/shared_prefs/<file>.xml'"
   adb -s SERIAL shell "am force-stop <pkg>"
   adb -s SERIAL shell "am start -n <pkg>/.MainActivity"
   ```
   Pitfall: some apps encrypt values in shared_prefs (e.g., SQLCipher
   passphrase blobs). Editing encrypted fields blindly corrupts the app
   state — only modify plain boolean/string entries whose meaning you
   understand.

## Verify the work

After any install or UI flow:

- `pm list packages | grep <id>` — package installed
- `pm path <id>` — APK path resolves
- `dumpsys package <id> | grep versionName` — version
- `uiautomator dump` shows the expected screen text
- `pidof <package>` — process running

Don't trust a single `screencap` 0-byte file as a failure signal
without checking whether the app is using a render surface the
screencap command can't capture.
