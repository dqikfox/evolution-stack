---
name: social-media-export
description: Export clips that upload to TikTok/Instagram. MP4 recipes.
version: 1.0.0
author: THRONE, Hermes Agent
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [social-media, export, mp4, ffmpeg, tiktok, instagram, sharing]
    related_skills: [comfyui]
---

# Social media export

Make locally generated or captured media upload-ready for TikTok, Instagram
(Reels / Stories / feed) and WhatsApp: the format requirements, the ffmpeg
recipes, and the browser-capture pattern that gets there.

## When to Use

- The user wants to share a generated or captured image/clip to TikTok,
  Instagram, WhatsApp, or any social platform.
- A web app needs social-ready export features (format presets, watermark,
  one-tap caption).
- A browser-recorded WebM must become a platform-acceptable MP4.

## Standing rules

- The deliverable is **H.264 MP4, `yuv420p`, `+faststart`**. TikTok, Instagram
  and WhatsApp uploads reject WebM — a browser-recorded WebM is an
  intermediate, never the deliverable.
- Name files for humans: `slug-of-prompt-<aspect>.mp4`, never ids or hashes.
- For an adult (35+) social audience: name buttons after the platform
  ("Reels & TikTok 9:16", "Instagram post 1:1"), keep the export step one tap,
  and ship a copy-caption + watermark alongside it.
- Verify every export with ffprobe (`codec_name,width,height,pix_fmt`)
  before telling the user it is platform-ready.

## Platform format table

| Target | Dimensions | Notes |
|---|---|---|
| TikTok / Reels / Stories | 1080×1920 (9:16) | blurred-fill letterbox when the source is not vertical |
| IG feed post | 1080×1080 (1:1) | |
| Small / WhatsApp-friendly | 720×720 | fastest transcode |
| Pictures | 1080×1080 PNG | cover-fit crop; handle watermark bottom-right |

## ffmpeg recipes

Vertical blurred-fill (square or wide source into 9:16):

```
ffmpeg -i in.webm -vf "split[bgsrc][fg];[bgsrc]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:2[bg];[fg]scale=1080:-2[fgs];[bg][fgs]overlay=(W-w)/2:(H-h)/2,format=yuv420p" -c:v libx264 -crf 20 -preset veryfast -movflags +faststart -an out.mp4
```

Square: `-vf scale=1080:1080:flags=lanczos,format=yuv420p` (same codec flags).

Photo downscale with EXIF baked upright (ffmpeg autorotates on input):

```
ffmpeg -i in.jpg -vf "scale='min(1080,iw)':-2" -q:v 3 out.jpg
```

## Browser-capture → MP4 pattern

Browsers cannot MediaRecord H.264 directly; they record WebM. The pipeline
that works end to end:

1. Canvas `captureStream(30)` + `MediaRecorder` (`video/webm;codecs=vp9`,
   fallback vp8), ≥5 Mbps for 1080 canvases.
2. `POST` the WebM blob to the local server on a **binary route with its own
   Content-Length cap** — generic JSON body readers cap at ~16 KB and will
   reject the upload with a confusing validation error.
3. Server runs ffmpeg (recipes above), registers the MP4 as a gallery asset,
   client auto-downloads it.
4. Watermark on the canvas BEFORE recording (handle bottom-right, ~W/34 font,
   soft shadow) — cheaper and more consistent than ffmpeg drawtext.

## Caption and share kit

- Copy-caption button: `<prompt> — made with <product> ✨ #<Product> #<tag> #<tag>`
  via `navigator.clipboard.writeText`; confirm in a toast.
- `navigator.share({files:[file]})` where the browser offers it (mobile share
  sheet); otherwise auto-download with an "upload it as you normally would"
  note — never claim a share happened without a success callback.
