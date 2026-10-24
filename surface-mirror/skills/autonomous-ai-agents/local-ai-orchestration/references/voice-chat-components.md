# Voice Chat Components for Vision (Local AI Stack)

Session: 2026-08-17. Context-compacted session where user asked for voice chat,
HTTPS, visual orb, and always-on listening in the Vision app.

See §9 for the minimal offline voice loop (pyttsx3 worker + Web Speech mic) — the fast path for single-page operator HUDs.

## 1. HTTPS for Localhost (No "Not Secure" Warning)

Generate self-signed certs with SAN for `localhost` + `127.0.0.1`:

```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout localhost.key -out localhost.crt \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
```

Wire uvicorn in launcher:
```python
uvicorn.run(
    "live_chat_app:app",
    host="0.0.0.0", port=8765,
    ssl_keyfile="localhost.key",
    ssl_certfile="localhost.crt",
)
```

Frontend auto-detects `wss://` vs `ws://` via `location.protocol`.

## 2. SAPI TTS (Windows Local Speech) — Replacing pyttsx3

**Why:** pyttsx3 conflicts with asyncio event loops, causing 30-second cascading timeouts.
**Fix:** Use `win32com.client.Dispatch("SAPI.SpVoice")` in threads.

```python
import win32com.client

def _sapi_speak(text: str):
    tts = win32com.client.Dispatch("SAPI.SpVoice")
    voices = tts.GetVoices()
    if voices.Count > 0:
        tts.Voice = voices.Item(voice_idx)
    tts.Rate = max(-10, min(10, int((rate - 175) / 20)))
    tts.Volume = 100
    try:
        tts.Speak(text, 0)  # blocking, swallow SPERR_DEVICE_BUSY
    except Exception:
        pass

await asyncio.wait_for(
    loop.run_in_executor(None, _sapi_speak, text),
    timeout=30.0
)
```

Store preference in `C:/Users/KING/AppData/Roaming/Vision/settings.json`:
```json
{"preferred_tts": "local", "tts_voice_idx": 1, "tts_rate": 175}
```

## 3. Message Interruption ("If I send a message it should interrupt")

**Problem:** `asyncio.Lock` + Ollama's 13s generation blocks new messages.
**Solution:** Don't cancel the old task (it holds the lock). Instead:
1. Cancel the speak task
2. Increment a per-session generation counter
3. In-flight token generators check counter and silently drop old tokens
4. Clear session history so new message starts fresh

```python
_session_generation: dict[WebSocket, int] = {}

async def _cancel_session_tasks(target):
    await _cancel_task(_session_speak_task(target))
    _session_histories.pop(target, None)
    current = _session_generation.get(target, 0)
    _session_generation[target] = current + 1
```

In `_broadcasting_gen()`:
```python
my_gen = _session_generation.get(my_target, 0)
async for chunk in text_gen:
    if _session_generation.get(my_target, 0) != my_gen:
        continue  # silently drop — newer message arrived
    yield chunk
```

## 4. Dictation Mode (One-Shot Voice-to-Text)

**Backend:** `async def handle_input` checks `_dictation_mode`. When True:
- Transcribed text sent as `{type: "dictation_result", text: "..."}`
- Auto-resets `_dictation_mode = False` after one utterance

**Frontend:** `toggleDictate()` sends `{type: "dictate"}`, receives `dictation_result`, inserts into `#msgInput`.

## 5. Always-On Listening (Continuous VAD)

Set `continuous_listening = True` at module level. The voice loop starts in `listening` state and stays there. VAD detects speech → transcribes → submits automatically.

Volume broadcasts are throttled to avoid flooding WebSocket:
```python
if now - _volume_broadcast_throttle >= 0.15:
    await broadcast_volume(lvl)
    _volume_broadcast_throttle = now
```

## 6. Visual Orb (Audio Reactive Feedback)

HTML/CSS orb with three states:
- `idle` — dimmed, small
- `listening` — cyan glow, pulse animation
- `hearing` — scales with volume level (`--vol-scale` CSS variable)
- `speaking` — blue glow

Volume messages animate orb:
```javascript
if (d.type === 'volume' && d.level > 0.02) {
    orb.classList.add('hearing');
    orb.style.setProperty('--vol-scale', Math.min(1 + d.level * 0.4, 1.3));
}
```

## 7. Modelfile Stop Token Fix

**Bug:** `PARAMETER stop <|im_start|>` matched the model's first generated token, causing immediate stop.
**Fix:** Rebuild with empty stop or `</s>`:

```dockerfile
FROM ...
TEMPLATE "... <|im_start|>assistant\n"
PARAMETER stop ""
PARAMETER num_ctx 8192
```

`num_ctx 8192` fits in 24GB VRAM (128K context exhausts VRAM on RTX 3090).

## 8. Ollama Model Name Quirks

- `ollama create qikfox/megatron` → `400 Bad Request: invalid model name`
- **Fix:** Create from inside `.ollama/models/` directory, or use a simple name then tag it
- Current default must be set in code: `current_model = "megatron-fixed:latest"`

## 9. Minimal offline voice loop for a FastAPI+WS operator (pyttsx3 worker + Web Speech mic)

Proven pattern from the ULTRON 2.1 build (2026-09-20) — a lighter alternative to the full Vision voice stack (§2-§6) when the operator app is a single-page HUD, not a full chat client. Zero cloud for TTS; mic uses the browser's Web Speech API (Chromium; the one cloud component — Google's recognizer — flag it to the user).

### TTS: dedicated daemon thread, not run_in_executor-per-call

`pyttsx3.init()` per call conflicts with asyncio event loops (the §2 problem). The fix that also avoids SAPI/win32com dependency: one long-lived worker thread owning a single `pyttsx3.init()` engine, fed by a bounded `queue.Queue`:

```python
# core/voice.py
import queue, threading, re
_q: queue.Queue = queue.Queue()

def _worker():
    import pyttsx3
    engine = pyttsx3.init()
    for v in engine.getProperty("voices"):
        if "David" in v.name:          # male persona match
            engine.setProperty("voice", v.id); break
    engine.setProperty("rate", 178)
    while True:
        text = _q.get()
        if text is None: break
        try:
            engine.say(re.sub(r"\[\[ACTION:[^\]]*\]\]", "", text)[:600])
            engine.runAndWait()          # single engine owned by this thread only
        except Exception: pass
        _q.task_done()

def start():
    threading.Thread(target=_worker, daemon=True, name="ultron-tts").start()

def speak(text):
    if _q.qsize() > 4:                    # bound the queue: drop stale, never lag live chat
        while _q.qsize() > 1: _q.get_nowait()
    _q.put(re.sub(r"\[\[ACTION:[^\]]*\]\]", "", text or "").strip())
```

Rules that make it work:
- **One engine, one thread, forever.** `engine.runAndWait()` from multiple threads or per-request `init()` is what causes the 30s cascading timeouts. The engine is created once in the worker and never touched from async code.
- **Strip action directives before enqueueing** — the model's `[[ACTION:{...}]]` protocol markers must never be spoken.
- **Bound the queue (drop oldest beyond ~4).** Speech lags text by seconds; an unbounded queue accumulates stale replies during a fast conversation.
- **Gate speech per-message from the client, not server-global.** WS payload `{text, voice: true}` → server calls `speak(reply)` only when the user's toggle is on. Start the worker in the FastAPI lifespan so it exists before the first voice:true message.
- **Test the loop headlessly first** (connect a raw websockets client, send `{text, voice:true}`, then assert `voice._q.qsize() == 0` after a sleep — queue drained = spoken). Browser audio can't be asserted programmatically.

### Mic: Web Speech API in the HUD, degrade gracefully

```js
if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const recog = new SR();
  recog.lang = 'en-AU'; recog.interimResults = false; recog.continuous = false;
  recog.onresult = e => { const said = e.results[0][0].transcript.trim(); if (said) send(said); };
  recog.onend = recog.onerror = () => resetMicButton();
  micBtn.onclick = () => listening ? recog.stop() : (try recog.start() ...);
} else {
  micBtn.disabled = true;  // graceful: Firefox has no Web Speech input
}
```

- `continuous = false` (push-to-talk) is the right default for an operator: one utterance → one send, no runaway transcription of the TTS output (echo loop).
- Serve the page over plain http://127.0.0.1 — Web Speech works there without the HTTPS setup from §1 (that's only needed for remote access).
- Keep the transcript path identical to typed input: `send(transcript)` → same `{text, voice}` WS payload. Voice input is just another keyboard.

### When to use which voice pattern

| Situation | Pattern |
|---|---|
| Single-page HUD operator, needs TTS+mic fast | §9 (this) — pyttsx3 worker + Web Speech, ~100 LOC total |
| Full chat client with orb, interruption, always-on VAD | §2-§6 Vision stack — SAPI via win32com, generation counters |
| User wants a specific cloned voice (his own) | ElevenLabs via §6 keys wiring — cloud, needs API key |

## Key Files Changed
- `live_chat_app.py` — SAPI TTS, dictation, interrupt logic, generation counter
- `live_chat_ui.html` — Orb visualizer, voice buttons, mode indicator
- `launch_elite_isolated.py` — HTTPS uvicorn config
- `settings.json` — TTS preferences
