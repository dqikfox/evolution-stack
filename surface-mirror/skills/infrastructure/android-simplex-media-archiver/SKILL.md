---
name: android-simplex-media-archiver
description: On-device SimpleX video archiving for Android (Termux + root).
version: 1.0.0
author: THRONE
license: MIT
---

# Android SimpleX Media Archiver

## When to use
- User wants videos from SimpleX groups/rooms saved automatically on the phone.
- Must run entirely on-device (no Windows-side bot).
- Physical SD card present and should receive a mirror copy.

## Always-on rules
- Source folder `/data/data/chat.simplex.app/files/app_files` is ephemeral — SimpleX clears it immediately after processing. Poll frequently (8s max).
- Run as root (`su -c`) to read app data directories.
- Always mirror to physical SD (`/storage/<UUID>/SimplexVideos`) when the mount exists.
- Store in dated folders `YYYY-MM-DD` on both internal (`/sdcard`) and physical SD.
- Never rely on Windows-side bots for phone media; phone-native is mandatory.
- Keep the watcher running as a background root process (Termux shortcut or nohup).

## Procedure
1. Install Termux + grant root + storage permission.
2. Push the watcher script (v2) to `/data/data/com.termux/files/home/simplex_phone_watcher_v2.py`.
3. The script must implement BOTH real-time polling of `/data/data/chat.simplex.app/files/app_files` (8 s interval) AND a periodic deep scan (every 5 min) of `/sdcard/SimplexGroups/{Videos,Rooms,Groups}`.
4. Create a Termux shortcut that starts the v2 watcher via `nohup python ... > /sdcard/SimplexVideos/watcher.out 2>&1 &` and records the PID.
5. Verify with `ps`, `tail watcher.log`, `ls /sdcard/SimplexVideos/YYYY-MM-DD/`, and a count of files moved during the first deep scan.
6. Always keep the watcher running as a background root process.

## Pitfalls
- Polling the wrong folder (e.g. SimplexGroups) misses new arrivals — only app_files receives fresh downloads.
- Running without root produces permission denied on app data — always prefix with `su -c`.
- Physical SD UUID changes across devices; discover with `mount | grep media_rw` before hard-coding.
- Zero-byte files appear when SimpleX has not finished writing — skip files smaller than 1 KB or re-check size after 30 s.
- Termux killed by Android Doze — root + nohup + wake lock (optional) keeps it alive.
- Historical media already in SimplexGroups is never seen by the ephemeral watcher — a periodic deep scan of the saved folders (every 5 min) is required to catch it.

## References
- references/phone-watcher-script.md — original real-time-only watcher
- references/phone-watcher-script-v2.md — enhanced watcher with periodic deep scan of SimplexGroups
- references/termux-shortcut.md — how to create the one-tap launcher
