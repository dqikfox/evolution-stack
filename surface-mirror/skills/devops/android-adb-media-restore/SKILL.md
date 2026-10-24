---
name: android-adb-media-restore
category: devops
description: ADB restore of media tars to Android gallery paths.
trigger: 'Use when restoring large media/attachment sets (images, video, files) from a tar or archive on a host to an Android device via ADB, especially when app-private directories are blocked by SELinux or sandbox rules.'
---

# Android ADB Media Restore

Restore large media/attachment archives from a Windows/Linux host into a location visible to the Android gallery or file manager when direct writes into `/data/data/<app>/files/` are blocked.

## Always-on rules
- Target a public SD-card path (`/sdcard/Pictures/`, `/sdcard/DCIM/`, `/sdcard/Download/`) rather than app-private storage when the final `mv` or `cp` into the app sandbox fails with "Operation not permitted".
- Use `adb push` for the tar, then extract on-device with `tar -xzf` under `su`.
- Run the push as a background Hermes process when the archive exceeds ~2 GB; poll with `process(action="poll")` only when needed.
- After extraction, verify with `ls | wc -l` and `du -sh` on the target directory; never assume success from exit code alone.
- Prefer `--strip-components=1` when the tar root is a single directory that should be flattened into the destination.
- When `tar` on the device rejects `--strip-components`, extract first then flatten with `mv <dir>/* . && rmdir <dir>` after extraction.

## Procedure
1. Stage the archive on the host in a durable location (E: or equivalent).
2. Push the tar to `/sdcard/Download/<name>.tar.gz` (or the final destination parent) with a background `adb push`.
3. On-device: `su -c 'mkdir -p /sdcard/Pictures/<TargetDir>'`.
4. Extract: `su -c 'tar -xzf /sdcard/Download/<name>.tar.gz -C /sdcard/Pictures/<TargetDir> --strip-components=1'`.
5. Verify count and size.
6. If the tar is already on-device at `/data/local/tmp/`, move it to `/sdcard/Download/` first before extracting to a gallery path.

## Pitfalls
- Never rely on a single `adb push` succeeding on the first attempt when the file is >8 GB; races with prior partial pushes or extract scripts commonly truncate or delete the tar mid-transfer.
- Do not attempt `mv` or `chown` directly into `/data/data/<pkg>/files/app_files` after a root extract — SELinux + app sandbox will block every file with "Operation not permitted" even when run as root.
- `run-as <pkg>` copy is unreliable for thousands of files; it frequently fails with permission errors on the source side.
- Background extract scripts launched via `setsid` or `nohup` are killed when the adb shell session ends; always verify the tar still exists before starting extraction.
- When the tar is partially extracted ("File exists" errors), always `rm -rf` the partial directory before re-extracting; incremental tar appends are not supported.
- After a long `adb push` of a >8 GB tar, always verify the final byte size on-device with `ls -l` before extraction; partial pushes leave truncated files that produce silent corruption or early termination.

## References
- references/android-adb-media-paths.md — decision table for target directories and visibility.