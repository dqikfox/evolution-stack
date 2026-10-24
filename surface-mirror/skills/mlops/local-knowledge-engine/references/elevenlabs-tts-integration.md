# ElevenLabs Voice Integration for Local AI Assistants

## When to use

Adding text-to-speech (TTS) output to a local knowledge assistant, RAG pipeline, or command-line AI interface. Specifically when the user wants their personal cloned voice (not a generic robot voice) and expects autonomous credential management.

## Setup

### 1. Extract credentials from 1Password

Use the Service Account method (see `1password-windows-credential-extraction.md`):

```python
import subprocess
import os
from pathlib import Path

os.environ["OP_SERVICE_ACCOUNT_TOKEN"] = Path.home().joinpath(".ultron", ".op_service_account").read_text()

# Extract API key
result = subprocess.run(
    ["op", "item", "get", item_id, "--vault", "credentials", "--reveal"],
    capture_output=True, text=True
)
```

### 2. Cache credentials locally

```python
from pathlib import Path

ULTRON_DIR = Path.home() / ".ultron"
ULTRON_DIR.mkdir(parents=True, exist_ok=True)

# Save extracted creds
(ULTRON_DIR / "elevenlabs_key.txt").write_text(api_key)
(ULTRON_DIR / "elevenlabs_voice.txt").write_text(voice_id)
```

### 3. Install ElevenLabs SDK

```bash
# Into the project's venv, NOT global Python
cd C:\Users\KING\nexus-core-throne
.venv\scripts\python.exe -m pip install elevenlabs
```

**Pitfall:** Installing into Hermes' global Python (or wrong venv) causes import errors. Always install into the active project's venv.

### 4. Speak function

```python
from pathlib import Path
from elevenlabs.client import ElevenLabs
import tempfile
import subprocess

ELEVENLABS_KEY = (Path.home() / ".ultron" / "elevenlabs_key.txt").read_text().strip()
ELEVENLABS_VOICE = (Path.home() / ".ultron" / "elevenlabs_voice.txt").read_text().strip()

def speak(text: str) -> None:
    client = ElevenLabs(api_key=ELEVENLABS_KEY)
    audio = client.generate(text=text, voice=ELEVENLABS_VOICE, model="eleven_multilingual_v2")
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        for chunk in audio:
            f.write(chunk)
        tmp_path = f.name
    subprocess.Popen(["start", "", tmp_path], shell=True)
```

**Pitfall:** The `generate()` method is deprecated in newer SDK versions. Use `client.text_to_speech.convert()` if available:

```python
audio = client.text_to_speech.convert(text=text, voice_id=ELEVENLABS_VOICE, model_id="eleven_multilingual_v2")
```

### 5. Wire into response loop

```python
# After getting LLM response
print(f"Response: {response}")
speak(response[:500])  # ElevenLabs has character limits; truncate if needed
```

## GPU VRAM Management

ElevenLabs is cloud-based (no local GPU needed), but Ollama models consume VRAM. If using voice + local LLM simultaneously:

| Model | VRAM Required | Use for |
|-------|--------------|---------|
| megatron (Qwen3.5 MoE 35B Q4_K_M) | ~21.7GB | Heavy reasoning |
| starscream (Gemma 4B 26B) | ~17GB | General RAG |
| qwen2.5:14b | ~8GB | Fallback |

**If VRAM is 95%+:** Ollama returns empty responses `{"response": "", "done": true}`. Use a smaller model for RAG, or configure `OLLAMA_KEEP_ALIVE=5m` to unload models after timeout.

## End-to-End Test

```powershell
cd C:\Users\KING\nexus-core-throne
.venv\scripts\python.exe -c "
from ultron_voice import speak, ELEVENLABS_KEY, ELEVENLABS_VOICE
print('Key loaded:', bool(ELEVENLABS_KEY))
print('Voice loaded:', bool(ELEVENLABS_VOICE))
speak('Hello, this is my voice.')
"
```

Expected: Windows Media Player (or default audio player) opens and plays the generated speech.

## References

- ElevenLabs API docs: https://elevenlabs.io/docs/api-reference/text-to-speech
- Voice ID is the cloned voice identifier, not the API key.
- `model="eleven_multilingual_v2"` is the recommended model for English with good fidelity.
