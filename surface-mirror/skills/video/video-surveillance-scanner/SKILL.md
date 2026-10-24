---
name: video-surveillance-scanner
category: video
description: ffmpeg motion+colour scanner for surveillance MP4s.
trigger: "Scan surveillance footage for motion + object-specific colour (e.g. AUD $50 notes)."
---

# Video Surveillance Scanner

Build and run targeted ffmpeg-based scanners that combine scene-change motion detection with jurisdiction- or object-specific colour signatures. Designed for large collections of short MP4 clips from fixed cameras.

## Always-on rules

- Lead with the foreground command the user can paste and run; background execution is secondary.
- Encode exact RGB thresholds for the target object's dominant colour; do not use generic 'green cash' heuristics when the jurisdiction uses polymer notes of a different hue.
- Report motion event count + colour match status in a single CSV with columns: video, path, motion_events, colour_match, status, size_mb.
- Status values are strictly: FLAGGED (motion + colour), MOTION (motion only), CLEAN.
- Minimum motion threshold defaults to 2 scene changes; adjust only when the user explicitly requests a different sensitivity.
- Never queue parallel scans on multiple days unless the user explicitly says 'scan all of them'.

## Procedure

1. Identify the target colour signature from reference images or known note/item descriptions.
2. Write or update `detect_<target>_tone()` using ffmpeg frame sampling at a fixed offset (default 1.5–2.0 s) and RGB range checks.
3. Run `run_ffmpeg_scene_detection()` with `select='gt(scene,0.25)'` to count motion events per clip.
4. Apply threshold filter: only run colour detection on clips with motion_events ≥ min_motion.
5. Emit one-row-per-video CSV with status derived from the two signals.
6. Surface the full foreground command to the user; do not rely on background process polling for status.

## Pitfalls

- Polling background processes via the process tool is unreliable in this environment — the shell treats `process(action=...)` as literal commands and errors. Always provide the exact foreground `python3 ...` command the user can paste.
- Generic colour detectors (e.g. 'green cash') produce false negatives on polymer notes of different hues; the RGB rule must match the physical item, not an assumption.
- Sampling a single frame too early or too late in short clips misses the object; default to 1.5–2.0 s from start unless the user supplies a better offset.
- Large collections (hundreds of clips) make real-time progress invisible when run in background; the user sees nothing until the CSV appears. Warn them of expected duration.

## References

- `references/aud50-colour-signature.md` — exact RGB thresholds and rationale for Australian $50 polymer notes.
