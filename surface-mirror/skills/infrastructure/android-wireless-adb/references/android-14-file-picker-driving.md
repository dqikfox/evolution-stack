# Driving Android 14 documentsUI File Picker via ADB

When an Android app launches the system file picker (`com.google.android.documentsui.picker.PickActivity`) to import a file, the picker UI is not a normal clickable list. The standard approach of `uiautomator dump` + `input tap` works for the topbar but the file list itself is non-clickable in the dump. This reference covers the working pattern for the picker that most apps on Android 14+ use.

## When this matters

- A phone-side app (e.g. Simplex Chat import, Telegram export, any "import data" / "open file" flow) opens a system file picker
- The picker shows your files but tapping them does nothing
- The picker's intent is `android.intent.action.GET_CONTENT cat=android.intent.category.OPENABLE typ=<mime>` — find it via `adb shell dumpsys activity activities | grep -A 5 'com.google.android.documentsui'`

## Discover what the calling app wants

```bash
adb shell dumpsys activity activities | grep -A 20 'documentsui' | grep -E 'Intent|launchedFromPackage'
# Look for: act=android.intent.action.GET_CONTENT typ=<mime> cmp=...PickActivity
```

Common MIMEs:
- `application/zip` — wants a ZIP file (e.g. Simplex Chat v7.x import)
- `*/*` — accepts any file (most open flows)
- `text/*` — text only

Stage the file on the phone **first**, with the right shape. Pushing raw `.db` files into `/sdcard/Download/` does not satisfy `application/zip`.

## Reliable navigation pattern

```bash
# 1. Find the Show roots button (top-left ImageButton, content-desc="Show roots")
adb shell uiautomator dump /sdcard/ui.xml
adb pull /sdcard/ui.xml ui.xml
grep -oE 'content-desc="Show roots"[^>]*bounds="\[[0-9,]+\]\[[0-9,]+\]"' ui.xml

# 2. Tap it to open the storage drawer
adb shell input tap <cx> <cy>

# 3. Wait, dump again, find the root you want (e.g. "Downloads")
adb shell uiautomator dump /sdcard/ui2.xml
adb pull /sdcard/ui2.xml ui2.xml
grep -oE 'text="Downloads"[^>]*bounds="\[[0-9,]+\]\[[0-9,]+\]"' ui2.xml

# 4. Tap the root
adb shell input tap <cx> <cy>
```

## The file-list trap

After tapping into a root, the file list shows your files but **uiautomator shows no `clickable="true"` element** in the file rows. Single `input tap` on a file row silently does nothing. The only working pattern is keyboard navigation:

```bash
# 5. Move focus into the file list
adb shell input keyevent KEYCODE_TAB
# 6. Move down to your target file (repeat as needed)
adb shell input keyevent KEYCODE_DPAD_DOWN
# 7. Press Enter to select
adb shell input keyevent KEYCODE_ENTER
# 8. Verify the calling app took over
adb shell dumpsys activity activities | grep mResumedActivity
# Should now show the calling app, not documentsui
```

After step 7, the picker dismisses and the calling app receives the URI. The app may then show a confirmation dialog (e.g. "Import database?") — those are clickable in the normal way.

## Verification

After the picker returns to the calling app:

```bash
# Check that activity flow completed
adb shell dumpsys activity activities | grep mResumedActivity
# Should now show the calling app's main activity
```

For state inspection, prefer `uiautomator dump` over `screencap` — the picker and post-picker confirmation dialogs are short-lived and screencap sometimes returns 0-byte files mid-transition.

## Pre-staging files: ZIP for Simplex Chat v7.x

```bash
# On the host PC, build the ZIP from the app's actual database files
python3 -c "
import zipfile, os
with zipfile.ZipFile('/tmp/simplex_migration.zip', 'w', zipfile.ZIP_DEFLATED) as zf:
    for f in os.listdir('/c/Users/KING/AppData/Roaming/Simplex'):
        full = os.path.join('/c/Users/KING/AppData/Roaming/Simplex', f)
        if os.path.isfile(full) and f.endswith('.db'):
            zf.write(full, f)
"

# Push to phone
adb push /tmp/simplex_migration.zip /sdcard/Download/simplex_migration.zip

# Then drive the picker as above
```

The ZIP's contents need only the `simplex_v1_*.db` files at the root. Empty `simplex_v1_files/` and `simplex_v1_assets/` directories can be omitted; Simplex creates them on import.

## Don't use this for: pickers that DO show clickable rows

Some apps roll their own file browser (e.g. Termux's built-in file manager, Telegram's internal file picker). The standard `uiautomator` + `input tap` pattern works for those. The `documentsui.picker.PickActivity` is the one with the non-clickable quirk.
