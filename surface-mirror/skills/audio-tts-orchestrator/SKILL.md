---
name: audio-tts-orchestrator
description: Coordinate Edge, OpenAI, ElevenLabs, pyttsx3 TTS.
---

# TTS Orchestration

## When to load
- "read this aloud"
- "say X"
- TTS provider fails or rate-limits
- Choosing voice for project

## Provider order (cheapest → most expensive)
1. **edge** — free, SAPI5 on Windows, decent quality
2. **pyttsx3** — fully local, SAPI5 voices, offline
3. **openai** — high quality, $15/1M chars
4. **minimax** — fast, multilingual
5. **xai** — expressive
6. **elevenlabs** — best voice cloning, user wants for personal voice

## Voice selection
- Hitchy's personal voice: ElevenLabs (clone target)
- Default read-aloud: edge (no API key, instant)
- Long-form narration: openai tts-1-hd
- Voice chat quick reply: pyttsx3 (offline, no latency)

## Failure handling
- HTTP 401 -> rotate provider down the list
- HTTP 429 -> wait 60s, retry once, then rotate
- No audio device -> fall back to mp3 file output
- 5k+ char input -> chunk at sentence boundary, concat audio

## Verify voice worked
- Check file size > 0
- ffprobe -i <output> 2>&1 | grep "Duration"
- If silent, swap provider

## Do not
- Burn paid API quota on long texts
- Use ElevenLabs without explicit user request
- Echo API keys in output
- Block on TTS provider if user is waiting