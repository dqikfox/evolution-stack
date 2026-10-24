---
name: android-wireless-adb
description: Persistent wireless ADB from Windows to Android phones — stock pair flow (Android 14+) and Magisk-rooted init.d (Android 10/11/12).
---

# Wireless ADB to Android (Windows)

Standard `adb` over USB drops the moment the phone sleeps, USB is unplugged, or the screen turns off. Wireless ADB (TCP/IP) survives those — but on Android 14+ Google added a 5-minute idle disconnect that kills the TCP session unless you keep the device warm. This skill covers both the stock pair flow and the Magisk-rooted init.d flow, depending on what the device supports.

## Which flow applies?

- **Stock Android 14+** (or any unrooted device with Developer Options → Wireless debugging): use **§ Stock pair flow** below.
- **Magisk-rooted Android 10/11/12**: skip the pair flow entirely — see `references/magisk-persistent-adb.md` for the init.d script approach. Cyclone_C4 (Android 10) is the canonical example.
- **Unrooted Android 10–13**: stock wireless ADB without the 5-min idle timeout, but no pairing code dance either — see the `service.adb.tcp.port` pattern in `references/magisk-persistent-adb.md`; it works on stock too if you have a one-time `adb shell setprop` to enable it. Note this setting does NOT survive reboot on stock devices.

## When to Use

- ADB connection drops the moment the phone screen sleeps
- Phone is on a different LAN subnet than the PC (different Wi-Fi, or PC on Tailscale)
- Want to drive the phone from `adb` without a USB cable
- A previous session installed "Debug Toolbox Pro" or similar — figure out what it actually does

## Don't use for: USB ADB (just plug in and `adb devices`).

## Which device is the phone?

Hitchy has two Android devices on the tailnet; **do not assume which is "the phone" without verifying**:

| Tailscale name | IP | Status (typical) | Specs | Notes |
|---|---|---|---|---|
| **Cyclone-C4** | `100.71.239.65` / `192.168.4.241` | **active** (canonical) | Android 10 (API 29), 32-bit armv7, Magisk rooted, Termux + SSH server, **no SIM** | The phone you actually drive. ADB works directly over Tailscale. |
| **S23** | `100.118.95.91` | **offline 58d+** (typical) | Android 16, Vodafone AU, daily driver | The user's real phone for SMS/calls/Telegram. NOT reachable on tailnet — connecting to it requires the user to bring it online first. |
| S19 | `100.120.82.1` | offline (intermittent) | older Android | Another test device. |
| quest-3s | `100.121.220.48` | offline 31d+ | Quest 3S headset | Not a phone. |

**Verify before claiming phone-side state:**
```bash
tailscale status | grep -E 'cyclone|s23|s19'  # check which is online NOW
adb devices                                  # confirm ADB has the right peer
```

**Failure mode this prevents:** saying "I'll send it to the phone" then driving the wrong device. S23 is the device Hitchy reads Telegram on; Cyclone-C4 is the device you can actually reach. If the user says "the phone", ask which one if unclear, or default to the tailnet-online one. S23 is rarely reachable — its absence from `tailscale status` is normal, not a daemon fault.

**Telegram specifically:** if the user wants you to verify a Telegram bot on the phone, the round trip goes phone → Telegram cloud → TDesktop on THRONE. Don't try to drive S23; install/sign-in on Cyclone-C4 and let the chat sync via the cloud. Cyclone-C4 has no SIM, so SMS auth doesn't work there — Telegram falls back to "send code to other signed-in device" which means TDesktop.

## What "Debug Toolbox Pro" actually does

`com.github.superadb` ("ADB Shell - Debug Toolbox Pro", published by `nextaix.com`) is an **ADB client UI** — buttons for things you'd otherwise hand-type. It does NOT install a persistent wireless server on Android 14+. The Play Store description "Android 4.X–Android 13(Support wireless pair mode)" stops at Android 13 because that's where Google's simple TCP ADB was deprecated. On Android 14+, the official path is `Settings → Developer Options → Wireless debugging`.

## Procedure — Stock pair flow (Android 14+)

### 1. Find a routable IP for the phone

```bash
adb -s <usb-serial> shell "ip -4 addr show wlan0 | grep -oE 'inet [0-9.]+' | head -1"
# Or check Tailscale status (if phone + PC share a tailnet)
"C:/Program Files/Tailscale/tailscale.exe" status --json | python -c "import sys,json; d=json.load(sys.stdin); print(d['TailscaleIPs'])"
```

Common gotchas:
- Phone on `192.168.1.x`, PC on `192.168.4.x` → gateway refuses intra-VLAN routing → use Tailscale instead
- Tailscale reachable but the listed port is closed → the pairing window already expired (5-min default)
- Tailscale shows peer as `active; direct 192.168.4.x:port` with high TX/RX but the PC can't connect to the tailnet IP → the headset/phone moved off the LAN; the direct endpoint is stale and needs a re-handshake. See `references/magisk-persistent-adb.md` § "Post-reboot gotcha" for the same root cause on phones.

### 2. Trigger a fresh pairing window

```bash
adb shell am start -a android.settings.WIRELESS_DEV_SETTINGS 2>&1 | tail -2
# If the device intercepts (some launchers do), force-stop the foreground app first
adb shell am force-stop <interfering.package>
adb shell am start -a android.settings.SETTINGS
```

Then on the phone: tap **Developer Options → Wireless debugging → Pair device with pairing code**. Note the IP:port and 6-digit code.

### 3. Pair + connect

```bash
adb pair <phone-ip>:<pair-port>          # paste the 6-digit code when prompted
adb connect <phone-ip>:<adb-port>        # usually 5555, or whatever the page shows
adb devices                              # confirm both entries (USB + wireless)
```

### 4. Keep the connection alive past the 5-min idle timeout

Android 14+ disconnects idle TCP adbd sessions. Ping every 30s with a watchdog. See `scripts/adb-keepalive.ps1` — copy and edit `$DeviceTarget`.

### 5. Verify the wireless link actually works

```bash
adb -s <phone-ip>:<port> shell getprop ro.product.model   # must return model name
adb -s <phone-ip>:<port> shell id                          # must show uid=2000(shell)
adb -s <phone-ip>:<port> shell input keyevent KEYCODE_HOME # phone should react
```

If `shell` fails with "more than one device/emulator", add `-s <phone-ip>:<port>` to every adb call.

## Pitfalls

- **LAN cross-subnet routing** — `192.168.1.x` → `192.168.4.x` usually fails. Tailscale or a routable VPN is the workaround.
- **Port expires after 5 min** — re-pair if you wait too long between connect steps.
- **`shell echo ping` in PS watchdog** — `Test-Connection` shadows the built-in cmdlet; rename to `Test-AdbConnection`.
- **Tailscale Android peer shows `active; direct` but tailnet IP is unreachable** — the direct endpoint is cached from an earlier session; trigger a fresh handshake via `monkey -p com.tailscale.ipn -c android.intent.category.LAUNCHER 1` (Android-side). On PC side, `tailscale ping <peer>` forces re-evaluation.
- **Hermes-agent-android hides its host name on the device** — the LAN/USB adb serial (e.g. `RFCW402J18M`) and the Tailscale name (`S19`) can differ; don't rely on either for routing.
- **`adb connect` succeeds but `shell` hangs** — port is open but the daemon isn't actually adbd. Check `adb shell "cat /proc/<pid>/cmdline | tr '\0' ' '"` and look for `adbd`.
- **`adb shell su -c 'cat > file << EOF ... EOF'` fails** — MSYS path/quote mangling. Push the file from disk and `cp` into place instead: see `references/magisk-persistent-adb.md`.
- **`adb install <local.apk>` from git-bash/MSYS fails with "failed to stat …: No such file or directory"** even after a successful `adb push` to `/data/local/tmp/`. The MSYS path translation sometimes drops the device-side temp path. Workaround: push the APK, then install via the device shell directly: `adb shell pm install -r /data/local/tmp/<apk>.apk`. The shell's `/data/local/tmp/` is what `pm` actually sees; MSYS mangling of the host-side `adb install` path argument is the cause. Worked example: 67MB Telegram APK pushed to Cyclone-C4 and installed via `adb shell pm install -r /data/local/tmp/telegram.apk` in ~30s.
- **Modern Telegram APK installs as a `org.telegram.messenger.web` stub, not `org.telegram.messenger`.** The main `org.telegram.messenger` package is registered but the only launcher activity is `org.telegram.messenger.web/org.telegram.messenger.DefaultIcon`. Launch the `.web` variant — that's the real app, the bare `org.telegram.messenger` package is a stub left in the manifest for legacy reasons. The `telegram.org/dl/android/apk` URL serves the universal 67MB APK that includes armv7 + arm64 + x86 + x86_64 native libs; for 32-bit-only devices like Cyclone-C4 (armeabi-v7a), this is the right APK and the install succeeds.
- **`screencap -p` returns 0-byte PNGs mid-transition, during in-app password fields, when FLAG_SECURE is active, or when the surface hasn't rendered yet.** `adb exec-out screencap -p` pipes a raw PNG stream; if the app has set FLAG_SECURE (privacy-protected screens) or the surface flinger hasn't rendered a new frame, the result is 0 bytes. For traditional Android Views, fall back to `uiautomator dump` for state inspection — it reads the live view tree and is unaffected by screen capture restrictions. For Jetpack Compose apps (Android 16+, Simplex Chat, etc.), `uiautomator dump` also returns empty or nearly-empty XML because Compose does not expose its view hierarchy to the accessibility framework — you must use the `su`-based screencap workaround instead. After destructive actions (dialog dismiss, app restart, deep-link), wait 2-3s before screencap so the surface flinger has time to render. Example: Simplex Chat's passphrase screen returns blank screencaps reliably; on a Compose build, neither `exec-out` nor `uiautomator` help — disable the app's screen-protection pref (e.g. `PrivacyProtectScreen` → `false` in shared_prefs) and use `su -c 'screencap /sdcard/...'` followed by `adb pull`.

- **Jetpack Compose UI is not inspectable via `uiautomator dump`.** Compose renders off the accessibility tree, so `uiautomator dump` produces an empty or single-node XML on Android 16+ Compose apps. The only reliable automation strategy is coordinate-based tapping guided by `screencap` screenshots. Be aware that list positions shift as content loads, so a tap that opened a chat at y≈520 in one screenshot may hit a different row after scrolling or on a different device. Always take a fresh screenshot after every navigation action to confirm coordinates before tapping.

- **Full `/data` partition causes silent screencap and `cp` failures — and breaks app databases.** If `screencap /sdcard/foo.png` produces a 0-byte file, or `cp` to `/sdcard` fails with "No space left on device" even though `/sdcard` appears to have space, check `df -h /data` — `/sdcard` is often a FUSE mount pointing to `/data/media/0`. The same fullness presents as a broken app DB: `SQLiteDiskIOException: disk I/O error` / `SQLITE_IOERR_*` in logcat across MANY apps at once (it's ENOSPC, not corruption). Check `df -h /data` BEFORE attempting any DB repair — see "Procedure — App DB broken" below.

## Procedure — "App database is broken" (usually a full disk)

When the user reports an app's database is broken/corrupt, the usual root cause on a long-lived Android device is `/data` at 100%, not corruption. Diagnose in this order:

```bash
# 1. Disk first — 100% full = root cause, stop looking elsewhere
adb shell df -h /data

# 2. Confirm mechanism in logcat: ENOSPC shows as I/O errors in EVERY app's SQLite, not just one
adb logcat -d | grep -iE 'sqlite|disk I/O error' | tail -20

# 3. Find the hog — /sdcard shares the userdata partition, so /sdcard hogs ARE /data hogs
adb shell 'du -sm /sdcard/* 2>/dev/null | sort -rn | head -15'
adb shell "su -c 'du -sm /data/data/* 2>/dev/null | sort -rn | head -15'"

# 4. Before deleting a big device file, prove a byte-identical copy exists on the host:
#    compare size AND md5sum on both sides — a matching size alone is not enough
md5sum <host-copy>            # host
adb shell md5sum <device-copy> # device — must match before rm

# 5. Free space, then restart the app and verify the DB actually recovers
adb shell am force-stop <pkg>
adb shell monkey -p <pkg> -c android.intent.category.LAUNCHER 1
sleep 12
adb logcat -d | grep -iE 'sqlite.*error' | tail   # must be silent post-restart
adb shell "su -c 'ls -la /data/data/<pkg>/*.db'"    # mtime updated on open = clean checkpoint
adb shell screencap -p /sdcard/v.png && adb pull /sdcard/v.png .  # visual confirmation of working UI
```

- **Common hogs:** leftover restore/backup archives in `/sdcard/Download/` (multi-GB tars/zips pushed during earlier sessions and never cleaned), app-received video caches (`DCIM/`, app media dirs), `Download/*.img` flashing leftovers.
- **A DB file whose mtime updates when the app opens is a healthy DB** — SQLCipher DBs have encrypted headers, so `head -c 16` showing garbage is normal, not corruption.
- **Android 14 documentsUI `OpenDocument` / `ACTION_GET_CONTENT` picker is not clickable in the standard way.** The picker UI (com.google.android.documentsui.picker.PickActivity) often shows rows where no element has `clickable="true"` in uiautomator; the only way to navigate is via accessibility actions or keyboard. Reliable sequence: (1) tap the "Show roots" ImageButton at top-left (content-desc="Show roots") to open the storage drawer, (2) tap the desired root (e.g. "Downloads"), (3) the folder list appears with no clickable elements per uiautomator but the file picker responds to `input keyevent KEYCODE_TAB` (focus the file list), then `KEYCODE_DPAD_DOWN` to move to the target file, then `KEYCODE_ENTER` to select it. Single `input tap` on a file row silently does nothing in this picker.
- **Discover what the calling app actually wants before staging files.** When an app launches a file picker, check the activity intent before pushing: `adb shell dumpsys activity activities | grep -A 2 'launchedFromPackage\|requestIntent\|launchedFromUid'`. Look for `act=android.intent.action.GET_CONTENT` plus `typ=...` — the MIME type tells you what to provide. `typ=application/zip` means the app wants a ZIP; pushing raw `.db` files in a folder leaves the picker with no selectable item, no matter how you name them. Different Simplex Chat versions use different MIMEs: v6.x wants `simplex_v1_chat.db` directly via SAF tree picker; v7.x wants an `application/zip` archive containing those files. Always stage the right container shape before telling the user "the files are on the phone."
- **No-SIM Android cannot receive SMS auth codes.** A rooted test device with no cellular service (`signalStrength=2147483647` everywhere, `dumpsys telephony.registry` shows empty `line1Number`) cannot receive Telegram SMS verification, Twilio auth codes, or any other SMS-based OTP. Auth flows fall back to "send code to another signed-in device" (Telegram), "use TOTP from authenticator app" (most modern services), or "email a code" (where supported). Don't promise SMS delivery to a no-SIM device; switch the auth path before the user gets frustrated.

## Quick Reference

```bash
adb connect <phone-ip>:<port>
adb -s <phone-ip>:<port> shell getprop ro.product.model
adb shell am start -a android.settings.WIRELESS_DEV_SETTINGS
adb shell "ss -tlnp 2>/dev/null | grep :<port>"

# Edit an app's shared_prefs when the app is not debuggable (requires root)
# 1. Pull the prefs file to local
adb shell su -c "cat /data/data/<package>/shared_prefs/<file>.xml > /sdcard/<file>.xml"
adb pull /sdcard/<file>.xml <local-path>
# 2. Edit locally, then push back
adb push <local-path> /sdcard/<file>_new.xml
adb shell su -c "cat /sdcard/<file>_new.xml > /data/data/<package>/shared_prefs/<file>.xml"
# 3. Force-stop the app to reload prefs
adb shell am force-stop <package>
```

## Procedure — On-Device Media Organization (no host pull)

When the user wants media organized on the phone itself — not pulled to the host — create a shell script that runs on-device via `su`. This is faster for large collections (avoiding the ADB transfer bottleneck) and respects "keep data on phone" requirements.

### Typical pattern

```bash
# 1. Create the organizer script on host (edit SRC_* and DEST_*)
#    See scripts/on-device-media-organizer.sh for a template.

# 2. Push to device temp
adb -s <device> push on-device-media-organizer.sh /data/local/tmp/
adb -s <device> shell chmod 755 /data/local/tmp/on-device-media-organizer.sh

# 3. Run on device with root
adb -s <device> shell "su -c '/data/local/tmp/on-device-media-organizer.sh'"

# 4. Verify results on device
adb -s <device> shell "du -sh /storage/emulated/0/AppMediaExport/"
adb -s <device> shell "find /storage/emulated/0/AppMediaExport/ -type f | wc -l"
```

### Key rules

- **Always check storage first.** Run `df -h /data` before starting. If usage is >95%, the script will silently fail on `cp` or `screencap` because `/sdcard` is a FUSE mount pointing to `/data/media/0`.
- **Use `cp` with wildcards for bulk moves**, not `find ... -exec cp` — the latter forks a process per file and times out on thousands of items.
- **Dedupe with filename patterns.** Android download managers create `(1)`, `(2)`, `(3)` suffix duplicates. These are safe to delete: `find ... -name '*\(1\)*' -delete`.
- **Organize by type then by date.** Move files to `Videos/` and `Images/` first, then create `ByDate/YYYYMMDD/` subfolders by parsing filenames (`video_20260715_...` → `20260715`).
- **Generate an index file.** After organization, write an `INDEX.txt` with file counts and locations so the user can browse without re-scanning.

### Common app media locations

| App | Images/Videos | Notes |
|---|---|---|
| Simplex Chat | `/sdcard/Pictures/SimpleX_Media/` (direct), `/sdcard/DCIM/Movies/` (groups) | Group videos use system download manager |
| Telegram | `/sdcard/Telegram/Telegram Images/`, `/sdcard/Telegram/Telegram Video/` | App-private unless "Save to Gallery" is on |
| WhatsApp | `/sdcard/WhatsApp/Media/` | Standard Android media tree |
| Chrome/Downloads | `/sdcard/Download/` | Mixed content, often requires filtering |

### Verification

After the script completes, check:
- Source folders still have original files (script should copy, not move, unless explicitly asked)
- Destination tree has expected structure (`Videos/`, `Images/`, `ByDate/`)
- `INDEX.txt` exists at destination root with accurate counts

## Procedure — Install an APK on a connected Android

Common case: the user wants an APK installed on the phone. The full path is:

```bash
# 1. Pull the APK to disk (any source — direct URL, app store download, 1Password attachment)
# 2. Push to the device tmp dir
adb -s <serial-or-tailnet-ip> push "<local.apk>" /data/local/tmp/<name>.apk
# 3. Install via the device shell (NOT `adb install <local>` — see pitfall)
adb -s <serial-or-tailnet-ip> shell pm install -r /data/local/tmp/<name>.apk
# 4. Verify the package is registered
adb -s <serial-or-tailnet-ip> shell pm list packages | grep <package.name>
# 5. Find the launcher activity (some APKs register as .web or .stub variants)
adb -s <serial-or-tailnet-ip> shell cmd package resolve-activity --brief -c android.intent.category.LAUNCHER <package.name>
# 6. Launch
adb -s <serial-or-tailnet-ip> shell am start -n <package>/<launcher.activity>
# 7. Wait for first paint, then uiautomator dump to confirm
sleep 3
adb -s <serial-or-tailnet-ip> shell uiautomator dump /sdcard/ui.xml  # increase timeout to 30s
adb -s <serial-or-tailnet-ip> pull /sdcard/ui.xml "<local>/ui.xml"
grep -oE '(text|content-desc)="[^"]+"' "<local>/ui.xml"   # confirm the expected screen
```

`pm install -r` reinstalls and keeps data; `-t` allows test-only APKs. For 32-bit-only devices (armv7), always confirm the APK includes `lib/armeabi-v7a/` — modern APKs may have dropped armv7 in favor of arm64-only. Check with `unzip -l <apk> | grep ^lib/`.

## Verification

After pairing, `adb devices` must show BOTH `<usb-serial> device` (USB) and `<phone-ip>:<port> device` (wireless). Wait 6 minutes — if the wireless entry disappears, your watchdog is broken or not running.

## Related Files

- `scripts/adb-keepalive.ps1` — PowerShell watchdog template (rename + edit `$DeviceTarget`) — stock Android 14+ only
- `scripts/on-device-media-organizer.sh` — Android shell script template for organizing app-downloaded media into dated folders on the device itself (no host pull)
- `references/magisk-persistent-adb.md` — Magisk-rooted init.d approach (Android 10/11/12), incl. Tailscale-tunnel post-reboot gotcha
- `references/android-14-file-picker-driving.md` — Driving the system documentsUI `OpenDocument` picker via ADB (non-clickable file rows, keyboard navigation fallback)
- `references/messaging-app-compose-automation.md` — Jetpack Compose messaging app automation: Simplex Chat patterns, media locations, passphrase entry, and on-device media organization
- `%LOCALAPPDATA%/hermes/scripts/adb_tcp.sh` — Magisk post-fs-data.d script source for rooted Android 10 devices
- `%LOCALAPPDATA%/hermes/scripts/phone_cyclone_adb.sh` — Cyclone_C4 helper: picks Tailscale IP first, falls back to LAN, then USB serial
