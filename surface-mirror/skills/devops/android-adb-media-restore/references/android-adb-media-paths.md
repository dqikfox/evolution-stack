# Android ADB Media Target Paths

Decision table for choosing the final destination when app-private storage is blocked.

| Goal | Recommended Path | Visibility | Notes |
|------|------------------|------------|-------|
| Gallery / Photos app | `/sdcard/Pictures/<Project>` or `/sdcard/DCIM/<Project>` | High | Appears in stock gallery and most third-party viewers. |
| Quick access / Downloads | `/sdcard/Download/<Project>` | Medium | Visible in file managers; not always scanned by gallery. |
| App-specific cache | `/sdcard/Android/data/<pkg>/files/` | Low | Often cleared; avoid for permanent media. |
| Root-only staging | `/data/local/tmp/` | None | Temporary only; must be moved before extraction. |

Always create the target directory with `mkdir -p` under `su` before extraction. Use `--strip-components=1` when the tar contains a single top-level directory that should be flattened.